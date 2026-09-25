# local_agent/main.py — Entry point cho Python Local Agent (<80 lines)
# Khởi động pollers, đăng ký handlers, xử lý signal shutdown

import logging
import signal
import sys

from .config_loader import load_config, get, sync_remote_config
from .firestore_poller import FirestorePoller
from .nlm_task_handler import handle_source_add, handle_source_remove, handle_course_create
from .chat_task_handler import handle_chat_query
from .research_task_handler import handle_research_start
from .artifact_task_handler import handle_artifact_download
from .exam_task_handler import handle_exam_generate
from .drive_sync import handle_drive_task
from .file_watcher import FileWatcher
from .local_reconciler import handle_reconcile_local, reconcile_with_firestore
import threading

# Ép stdout/stderr về UTF-8 để log tiếng Việt không lỗi khi redirect sang file (Windows cp1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Thiết lập logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

_pollers: list[FirestorePoller] = []
_watcher: FileWatcher | None = None


def _shutdown_handler(signum, frame):
    """Xử lý Ctrl+C và SIGTERM — dừng tất cả pollers + watcher gracefully."""
    logger.info("Nhận signal %s — đang dừng agent...", signal.Signals(signum).name)
    for p in _pollers:
        p.stop()
    if _watcher:
        _watcher.stop()
    logger.info("Agent đã dừng.")
    sys.exit(0)


def main():
    """Khởi động Python Local Agent."""
    # Load config
    try:
        cfg = load_config()
    except FileNotFoundError as e:
        logger.error("Không tìm thấy config.json: %s", e)
        sys.exit(1)

    worker_url = cfg.get("worker_url", "")
    if not worker_url:
        logger.error("worker_url chưa được cấu hình trong config.json")
        sys.exit(1)
    if not cfg.get("agent_secret"):
        logger.warning("agent_secret trống — task queue API sẽ bị từ chối")

    # Kéo cấu hình Global Settings từ Firestore (bảng system_config)
    try:
        cfg = sync_remote_config()
        logger.info("Đã đồng bộ Global Settings từ Cloud Firestore (local_base_path=%s, drive_root=%s)",
                    cfg.get("local_base_path"), cfg.get("google_drive_root_folder_id"))
    except Exception as e:
        logger.warning("Không thể nạp remote config (dùng local fallback): %s", e)

    logger.info("ThsAutoOrganizer Local Agent khởi động")
    logger.info("Worker URL: %s", worker_url)
    logger.info("Poll interval: %ss", cfg.get("poll_interval_seconds", 10))

    # --- NLM Task Queue Poller ---
    nlm_poller = FirestorePoller("nlm_task_queue")
    nlm_poller.register("course_create", handle_course_create)
    nlm_poller.register("source_add", handle_source_add)
    nlm_poller.register("source_remove", handle_source_remove)
    nlm_poller.register("chat_query", handle_chat_query)
    nlm_poller.register("research_start", handle_research_start)
    nlm_poller.register("artifact_download", handle_artifact_download)
    nlm_poller.register("exam_generate", handle_exam_generate)
    nlm_poller.register("reconcile_local", handle_reconcile_local)
    _pollers.append(nlm_poller)

    # --- Drive Task Queue Poller ---
    drive_poller = FirestorePoller("drive_task_queue")
    drive_poller.register("move_to_archive", handle_drive_task)
    drive_poller.register("soft_delete_local", handle_drive_task)
    drive_poller.register("hard_delete", handle_drive_task)
    _pollers.append(drive_poller)

    # --- File Watcher (Local Inflow) ---
    global _watcher
    if cfg.get("file_watcher_enabled", True):
        _watcher = FileWatcher()
    else:
        logger.info("FileWatcher bị tắt trong config (file_watcher_enabled=false)")

    # Đăng ký signal handlers
    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    # Khởi động tất cả pollers + watcher
    for p in _pollers:
        p.start()
    if _watcher:
        _watcher.start()

    # Tự động đối soát đĩa Local trên nền background ngay khi khởi động
    threading.Thread(
        target=reconcile_with_firestore,
        name="bg-disk-reconcile-startup",
        daemon=True,
    ).start()

    logger.info("Agent đang chạy. Nhấn Ctrl+C để dừng.")

    # Giữ main thread sống
    signal.pause() if sys.platform != "win32" else _windows_wait()


def _windows_wait():
    """Chờ vô thời hạn trên Windows (signal.pause() không hỗ trợ)."""
    import time
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
