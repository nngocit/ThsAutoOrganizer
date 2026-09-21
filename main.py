"""ThacSi HTTT Auto Organizer - Main Entry Point.

Khởi tạo cấu hình, cơ sở dữ liệu SQLite, hệ thống ghi log,
quét file sẵn có khi khởi động và theo dõi file mới bằng Watchdog + Queue Worker.
"""

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import signal
import sys
import threading
import time
from typing import Any, Dict, Optional, Set

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from src.classifier import PathClassifier
from src.database import Database
from src.drive import DriveManager
from src.processor import FileProcessor, is_file_stable

# Logger chính của ứng dụng
logger = logging.getLogger("ThsAutoOrganizer")


def load_config(config_path: Path | str = "config.json") -> Dict[str, Any]:
    """Đọc cấu hình từ file config.json với các giá trị mặc định an toàn."""
    default_config: Dict[str, Any] = {
        "root_folder": "D:\\ThacSi_HTTT",
        "database": "data\\files.db",
        "google_drive_root_folder_id": "",
        "create_drive_subfolders": True,
        "process_existing_files_on_start": True,
        "min_file_size_bytes": 1000,
        "stable_file_wait_seconds": 3,
        "log_level": "INFO",
        "supported_extensions": [".pdf", ".docx", ".pptx", ".txt", ".md"],
    }

    path = Path(config_path).resolve()
    if not path.is_file():
        logger.warning("Không tìm thấy file config '%s'. Sử dụng cấu hình mặc định.", path)
        return default_config

    try:
        with open(path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
            default_config.update(user_config)
            logger.info("Đã tải cấu hình từ '%s'", path)
            return default_config
    except Exception as exc:
        logger.error("Lỗi khi đọc file config '%s': %s. Dùng cấu hình mặc định.", path, exc)
        return default_config


def setup_logging(log_file: Path | str = "logs/app.log", log_level: str = "INFO") -> None:
    """Thiết lập logging song song: console và file với định dạng chuẩn."""
    # Đảm bảo Windows console in tiếng Việt không bị lỗi charmap UnicodeEncodeError
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    log_path = Path(log_file).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-5s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File Handler (quay vòng tối đa 10MB x 5 file)
    file_handler = RotatingFileHandler(
        str(log_path),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(numeric_level)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(numeric_level)

    # Xóa handler cũ nếu có
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


class WatchdogHandler(FileSystemEventHandler):
    """Bắt sự kiện từ Watchdog và đưa đường dẫn file vào hàng đợi xử lý."""

    def __init__(
        self,
        task_queue: queue.Queue,
        processor: FileProcessor,
        debounce_seconds: float = 2.0,
    ) -> None:
        super().__init__()
        self.task_queue = task_queue
        self.processor = processor
        self.debounce_seconds = debounce_seconds
        self._recently_queued: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _enqueue_if_valid(self, file_path_str: str) -> None:
        path = Path(file_path_str)
        if not path.is_file():
            return

        if not self.processor.should_process_file(path):
            return

        resolved_str = str(path.resolve())
        now = time.time()

        with self._lock:
            last_time = self._recently_queued.get(resolved_str, 0)
            if now - last_time < self.debounce_seconds:
                return  # Tránh enqueue lặp liên tục khi file đang được ghi
            self._recently_queued[resolved_str] = now

        self.task_queue.put(path)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue_if_valid(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue_if_valid(event.src_path)


def worker_loop(
    task_queue: queue.Queue,
    processor: FileProcessor,
    stable_wait_seconds: float,
    stop_event: threading.Event,
) -> None:
    """Luồng worker lấy file từ hàng đợi, chờ ổn định và tiến hành xử lý theo từng user."""
    logger.info("Worker thread đã sẵn sàng nhận việc.")
    while not stop_event.is_set():
        try:
            item = task_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        if item is None:
            # Sentinel để dừng luồng
            task_queue.task_done()
            break

        if isinstance(item, tuple):
            file_path, user_email = item
        else:
            file_path, user_email = item, "default@user"

        file_path = Path(file_path)
        try:
            logger.debug("Worker nhận file: %s (User: %s)", file_path, user_email)
            # Kiểm tra file đã sao chép/ghi hoàn tất hay chưa
            if not is_file_stable(file_path, wait_seconds=stable_wait_seconds):
                logger.warning("File '%s' chưa ổn định hoặc bị khóa, bỏ qua lượt này.", file_path)
            else:
                processor.process_file(file_path, user_email=user_email)
        except Exception as exc:
            logger.error("Lỗi không kiểm soát trong worker khi xử lý '%s': %s", file_path, exc, exc_info=True)
        finally:
            task_queue.task_done()

    logger.info("Worker thread kết thúc an toàn.")


def scan_existing_files(
    root_folder: Path,
    processor: FileProcessor,
    task_queue: queue.Queue,
    user_email: str = "default@user",
) -> int:
    """Quét toàn bộ thư mục root_folder để tìm và xử lý các file đã có từ trước cho tài khoản user."""
    target_path = Path(root_folder).resolve()
    if not target_path.is_dir():
        logger.warning("Thư mục root '%s' chưa tồn tại trên máy.", target_path)
        return 0

    count = 0
    for path in target_path.rglob("*"):
        if path.is_file() and processor.should_process_file(path):
            task_queue.put((path, user_email))
            count += 1

    if count > 0:
        logger.info("Đã phát hiện %d file trong '%s' (User: %s). Đã đưa vào hàng đợi.", count, target_path, user_email)
    else:
        logger.info("Không có file nào có sẵn cần xử lý trong thư mục '%s'.", target_path)
    return count


def main() -> None:
    """Điểm khởi chạy ứng dụng chính."""
    config = load_config("config.json")
    setup_logging("logs/app.log", config.get("log_level", "INFO"))

    logger.info("==================================================")
    logger.info("  ThacSi HTTT Auto Organizer - Hệ thống tự động   ")
    logger.info("==================================================")

    root_folder = Path(config["root_folder"]).resolve()
    db_path = Path(config["database"]).resolve()

    logger.info("Thư mục nguồn (Source of Truth): %s", root_folder)
    logger.info("Cơ sở dữ liệu SQLite: %s", db_path)

    # Đảm bảo thư mục root tồn tại để theo dõi
    if not root_folder.exists():
        try:
            root_folder.mkdir(parents=True, exist_ok=True)
            logger.info("Đã tạo thư mục root: %s", root_folder)
        except Exception as exc:
            logger.warning("Không thể tự động tạo thư mục '%s': %s", root_folder, exc)

    # 1. Khởi tạo Database
    database = Database(db_path=db_path)
    database.initialize()

    # 2. Khởi tạo Classifier
    classifier = PathClassifier(
        root_folder=root_folder,
        allow_direct_subject_files=config.get("allow_direct_subject_files", True),
    )

    # 3. Khởi tạo Google Drive Manager
    drive_manager = DriveManager(
        credentials_file="credentials.json",
        token_file="token.json",
        root_folder_id=config.get("google_drive_root_folder_id", ""),
    )

    if drive_manager.is_configured():
        logger.info("[OK] Đã tìm thấy cấu hình Google Drive credentials/token.")
    else:
        logger.warning(
            "[WAITING] Chưa có file credentials.json hoặc token.json! "
            "Chương trình vẫn chạy bình thường: file sẽ được phân loại, băm SHA-256, "
            "trích xuất nội dung và lưu SQLite. Hãy tải credentials.json từ Google Cloud Console."
        )

    # 4. Khởi tạo FileProcessor
    processor = FileProcessor(
        classifier=classifier,
        database=database,
        drive_manager=drive_manager,
        min_file_size_bytes=int(config.get("min_file_size_bytes", 1000)),
        supported_extensions=config.get("supported_extensions"),
        extract_content=True,
    )

    # 5. Khởi tạo Hàng đợi & Worker Thread
    task_queue: queue.Queue = queue.Queue()
    stop_event = threading.Event()
    stable_wait = float(config.get("stable_file_wait_seconds", 3.0))

    worker = threading.Thread(
        target=worker_loop,
        args=(task_queue, processor, stable_wait, stop_event),
        daemon=True,
        name="FileProcessorWorker",
    )
    worker.start()

    # 6. Quét file có sẵn nếu được cấu hình
    if config.get("process_existing_files_on_start", False):
        logger.info("Đang quét các file đã tồn tại trong thư mục root...")
        scan_existing_files(root_folder, processor, task_queue)
    else:
        logger.info("Chế độ chờ đăng nhập: Chưa quét tự động. Hãy đăng nhập tài khoản và bấm Quét từ Web Studio.")

    # 7. Khởi động Watchdog Observer
    event_handler = WatchdogHandler(task_queue, processor)
    observer = Observer()

    if root_folder.is_dir():
        observer.schedule(event_handler, str(root_folder), recursive=True)
        observer.start()
        logger.info("Watchdog đã bắt đầu theo dõi đệ quy tại: %s", root_folder)
    else:
        logger.error("Thư mục root '%s' không thể theo dõi vì không tồn tại.", root_folder)

    # 8. Khởi động Auto Drive Sync Worker (Tự động kéo tài liệu từ Drive định kỳ)
    from src.sync import AutoDriveSyncWorker

    auto_sync_interval = int(config.get("drive_sync_interval_minutes", 3)) * 60
    auto_sync_enabled = bool(config.get("auto_sync_drive", True))
    auto_sync_worker = AutoDriveSyncWorker(
        drive_manager=drive_manager,
        database=database,
        root_folder=root_folder,
        classifier=classifier,
        interval_seconds=auto_sync_interval,
        enabled=auto_sync_enabled,
    )
    if auto_sync_enabled and drive_manager.is_configured():
        auto_sync_worker.start()

    # 9. Khởi động Web Dashboard Server
    web_server = None
    if config.get("enable_web_ui", True):
        from src.web_server import start_web_server

        def trigger_rescan(target_folder: Optional[str] = None, user_email: str = "default@user") -> int:
            folder = Path(target_folder).resolve() if target_folder else root_folder
            logger.info("Quét thư mục máy tính '%s' cho tài khoản: %s", folder, user_email)
            return scan_existing_files(folder, processor, task_queue, user_email=user_email)

        web_port = int(config.get("web_port", 8080))
        try:
            web_server = start_web_server(
                port=web_port,
                database=database,
                drive_manager=drive_manager,
                config_path="config.json",
                scan_callback=trigger_rescan,
                classifier=classifier,
                auto_sync_worker=auto_sync_worker,
            )
            logger.info("👉 Mở trình duyệt truy cập Web Dashboard: http://localhost:%d", web_port)
        except Exception as exc:
            logger.warning("Không thể khởi động Web Dashboard trên port %d: %s", web_port, exc)

    # 10. Xử lý tắt chương trình nhẹ nhàng (Graceful Shutdown)
    def shutdown_signal_handler(signum: int, frame: Any) -> None:
        logger.info("Nhận tín hiệu dừng chương trình. Đang đóng các tiến trình...")
        stop_event.set()
        auto_sync_worker.stop()
        if observer.is_alive():
            observer.stop()
        task_queue.put(None)
        if web_server:
            try:
                web_server.shutdown()
            except Exception:
                pass

    signal.signal(signal.SIGINT, shutdown_signal_handler)
    signal.signal(signal.SIGTERM, shutdown_signal_handler)

    logger.info("Hệ thống đang hoạt động. Nhấn Ctrl+C để dừng.")

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown_signal_handler(signal.SIGINT, None)

    if observer.is_alive():
        observer.join()
    worker.join(timeout=5.0)
    logger.info("Hệ thống đã dừng hoàn toàn.")


if __name__ == "__main__":
    main()
