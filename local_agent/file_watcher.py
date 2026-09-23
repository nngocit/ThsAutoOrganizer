# local_agent/file_watcher.py — Local Inflow bằng watchdog (<230 dòng)
# Quét file mới/sửa trong local_base_path -> upload Drive -> api_client.register_file.
# NO-LOOP GUARD (§1): bỏ qua NO_LOOP_FOLDERS, ~$*, .tmp, <1000 bytes, duplicate sha256.
# Watcher CHỈ đăng ký file vào Worker; Worker quyết định queue source_add.

import hashlib
import logging
import threading
import time
from pathlib import Path

from . import api_client
from .config_loader import get
from .constants import FOLDER_MAP, SUPPORTED_EXTENSIONS, is_no_loop_path

logger = logging.getLogger(__name__)

MIN_SIZE_BYTES = 1000
SETTLE_SECONDS = 2.0          # chờ file ghi xong trước khi xử lý


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _split_rel(path: Path, base: Path) -> tuple[str, str, str]:
    """Tách path tương đối -> (subject, folder_path, filename). subject = thư mục cấp 1."""
    rel = path.relative_to(base)
    parts = rel.parts
    if len(parts) < 2:
        return "", "", rel.name
    return parts[0], "/".join(parts[1:-1]), parts[-1]


def _infer_document_type(folder_path: str) -> str:
    """Suy document_type từ folder_path theo FOLDER_MAP; mặc định giao_trinh."""
    norm = folder_path.replace("\\", "/")
    for doc_type, folder in FOLDER_MAP.items():
        if folder in norm:
            return doc_type
    return "giao_trinh"


class _DispatchHandler:
    """Nhận event watchdog rồi đẩy vào hàng đợi nội bộ của watcher."""

    def __init__(self, watcher: "FileWatcher"):
        self._watcher = watcher

    def dispatch(self, event) -> None:
        if getattr(event, "is_directory", False):
            return
        if getattr(event, "event_type", "") in ("created", "modified", "moved"):
            self._watcher.enqueue(Path(event.src_path))


class FileWatcher:
    """Watchdog song song: start() chạy nền, stop() dừng gọn."""

    def __init__(self, base_path: str | Path | None = None):
        self.base_path = Path(base_path or get("local_base_path", "."))
        self._pending: dict[str, float] = {}     # path -> lần cuối thấy event
        self._seen_hashes: set[str] = set()      # sha256 đã xử lý trong phiên
        self._lock = threading.Lock()
        self._running = False
        self._observer = None
        self._worker: threading.Thread | None = None

    # ---------- Lọc (NO-LOOP GUARD lớp 3) ----------
    def should_ignore(self, path: Path) -> str:
        """Trả lý do bỏ qua ('' = chấp nhận)."""
        name = path.name
        if name.startswith("~$"):
            return "office lock file (~$*)"
        if name.endswith(".tmp"):
            return "temp file (.tmp)"
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return f"extension không hỗ trợ ({path.suffix})"
        try:
            rel = str(path.relative_to(self.base_path)).replace("\\", "/")
        except ValueError:
            return "ngoài base_path"
        if is_no_loop_path(rel):
            return "NO-LOOP folder (output/archive)"
        try:
            if path.stat().st_size < MIN_SIZE_BYTES:
                return f"<{MIN_SIZE_BYTES} bytes"
        except OSError:
            return "không đọc được file"
        return ""

    # ---------- Hàng đợi nội bộ (chống event trùng + chờ file settle) ----------
    def enqueue(self, path: Path) -> None:
        with self._lock:
            self._pending[str(path)] = time.time()

    def _process_loop(self) -> None:
        while self._running:
            time.sleep(1.0)
            now = time.time()
            with self._lock:
                ready = [p for p, ts in self._pending.items() if now - ts >= SETTLE_SECONDS]
                for p in ready:
                    del self._pending[p]
            for raw in ready:
                try:
                    self.process_file(Path(raw))
                except Exception:
                    logger.exception("FileWatcher lỗi xử lý %s", raw)

    def process_file(self, path: Path) -> None:
        """Pipeline 1 file: lọc -> sha256 -> check_hash -> upload Drive -> register."""
        reason = self.should_ignore(path)
        if reason:
            logger.debug("Bỏ qua %s: %s", path.name, reason)
            return

        digest = _sha256(path)
        if digest in self._seen_hashes:
            logger.debug("Bỏ qua %s: duplicate sha256 (session cache)", path.name)
            return

        dup = api_client.check_hash(digest)
        if dup.get("duplicate"):
            logger.info("Bỏ qua %s: duplicate trên server (file_id=%s)",
                        path.name, dup.get("file_id"))
            self._seen_hashes.add(digest)
            return

        subject, folder_path, filename = _split_rel(path, self.base_path)
        if not subject:
            logger.debug("Bỏ qua %s: không xác định được subject", path)
            return

        from .drive_sync import upload_file  # lazy import
        uploaded = upload_file(path, folder_path, subject)

        api_client.register_file(
            filename=filename, subject=subject,
            document_type=_infer_document_type(folder_path),
            folder_path=folder_path, sha256=digest,
            drive_file_id=uploaded["drive_file_id"],
            drive_view_link=uploaded.get("webViewLink") or uploaded.get("web_view_link", ""),
            size_bytes=uploaded["size_bytes"], local_path=str(path.resolve()),
        )
        self._seen_hashes.add(digest)
        logger.info("Đã đăng ký file mới: %s/%s", subject, filename)

    # ---------- Lifecycle ----------
    def start(self) -> None:
        """Khởi động observer + worker thread (không chặn main thread)."""
        if not self.base_path.exists():
            logger.warning("FileWatcher: base_path không tồn tại: %s — watcher tắt", self.base_path)
            return
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        dispatcher = _DispatchHandler(self)
        adapter = FileSystemEventHandler()
        adapter.on_any_event = dispatcher.dispatch  # type: ignore[method-assign]

        self._running = True
        self._observer = Observer()
        self._observer.schedule(adapter, str(self.base_path), recursive=True)
        self._observer.daemon = True
        self._observer.start()
        self._worker = threading.Thread(target=self._process_loop,
                                        name="file-watcher", daemon=True)
        self._worker.start()
        logger.info("FileWatcher đang theo dõi: %s", self.base_path)

    def stop(self) -> None:
        """Dừng observer + worker."""
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
        if self._worker:
            self._worker.join(timeout=5)
        logger.info("FileWatcher đã dừng")
