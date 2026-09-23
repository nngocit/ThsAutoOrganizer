# local_agent/artifact_task_handler.py — Artifacts Downloader (<150 dòng)
# §7: KHÔNG có `nlm artifact download` — dùng `nlm download slide-deck` (pptx)
# hoặc `nlm download all`. Kết quả: Drive + local 04_Ket_Qua_Xuat_Ban + artifact_complete.

import hashlib
import logging
import tempfile
from pathlib import Path

from . import api_client
from .cascade_delete import resolve_local_path
from .constants import OUTPUT_FOLDER
from .nlm_task_handler import _nlm_available, _parse_nlm_json, _run_nlm

logger = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT = 300


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_artifact(notebook_id: str, fmt: str, dest: Path) -> Path:
    """Tải artifact theo format. Trả về file local đã tải. Raise nếu lỗi."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "pptx":
        # §7: nlm download slide-deck <NB_ID> --format pptx --output "<path>.pptx"
        rc, stdout, stderr = _run_nlm(
            ["download", "slide-deck", notebook_id, "--format", "pptx",
             "--output", str(dest)], timeout=DOWNLOAD_TIMEOUT)
        if rc != 0:
            raise RuntimeError(f"nlm download slide-deck lỗi (code={rc}): {stderr or stdout}")
        if not dest.exists():
            raise RuntimeError(f"slide-deck xong nhưng không thấy file: {dest}")
        return dest

    # Format khác: nlm download all -> chọn file đúng extension
    tmp = Path(tempfile.mkdtemp(prefix="ths_artifact_"))
    rc, stdout, stderr = _run_nlm(
        ["download", "all", notebook_id, "--output-dir", str(tmp),
         "--slide-format", "pptx", "--interactive-format", "json",
         "--skip-existing", "--json"], timeout=DOWNLOAD_TIMEOUT)
    if rc != 0:
        raise RuntimeError(f"nlm download all lỗi (code={rc}): {stderr or stdout}")
    _parse_nlm_json(stdout)  # log parse, không bắt buộc
    ext = ".md" if fmt in ("md", "markdown") else f".{fmt}"
    matches = sorted(tmp.rglob(f"*{ext}"))
    if not matches:
        raise RuntimeError(f"download all xong nhưng không có file *{ext} trong {tmp}")
    dest.write_bytes(matches[0].read_bytes())
    return dest


def handle_artifact_download(task: dict) -> None:
    """Xử lý action='artifact_download' (§2). Lỗi -> raise (poller mark failed)."""
    if not _nlm_available():
        raise RuntimeError("nlm CLI không tìm thấy")

    uid = task.get("uid", "")
    course_id = task.get("course_id", "")
    notebook_id = task.get("notebook_id", "")
    fmt = (task.get("format") or "pptx").lower().lstrip(".")
    target_folder = task.get("target_folder") or OUTPUT_FOLDER
    artifact_name = task.get("artifact_name") or "artifact"

    if not (uid and course_id and notebook_id):
        raise ValueError("artifact_download thiếu uid/course_id/notebook_id")

    subject = task.get("subject") or course_id
    filename = f"{artifact_name}.{fmt}"
    dest = resolve_local_path(subject, target_folder, filename)

    # Tránh ghi đè: thêm hậu tố số nếu file đã tồn tại
    counter = 1
    while dest.exists():
        dest = dest.with_name(f"{artifact_name}_{counter}.{fmt}")
        counter += 1
    filename = dest.name

    _download_artifact(notebook_id, fmt, dest)
    logger.info("Artifact đã tải: %s (%d bytes)", dest, dest.stat().st_size)

    from .drive_sync import upload_file  # lazy import
    uploaded = upload_file(dest, target_folder, subject)

    api_client.artifact_complete(
        uid=uid, course_id=course_id, filename=filename,
        local_path=str(dest.resolve()), drive_file_id=uploaded["drive_file_id"],
        sha256=_sha256_file(dest), size_bytes=dest.stat().st_size,
        artifact_name=artifact_name)
    logger.info("artifact_complete OK: %s -> %s/%s", filename, subject, target_folder)
