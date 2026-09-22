# local_agent/main.py — Entry point cho Python Local Agent (<80 lines)
# Khởi động pollers, đăng ký handlers, xử lý signal shutdown

import logging
import signal
import sys

from .config_loader import load_config, get
from .firestore_poller import FirestorePoller
from .nlm_task_handler import handle_source_add, handle_source_remove
from .drive_sync import handle_drive_task

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


def _shutdown_handler(signum, frame):
    """Xử lý Ctrl+C và SIGTERM — dừng tất cả pollers gracefully."""
    logger.info("Nhận signal %s — đang dừng agent...", signal.Signals(signum).name)
    for p in _pollers:
        p.stop()
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

    logger.info("ThsAutoOrganizer Local Agent khởi động")
    logger.info("Worker URL: %s", worker_url)
    logger.info("Poll interval: %ss", cfg.get("poll_interval_seconds", 10))

    # --- NLM Task Queue Poller ---
    nlm_poller = FirestorePoller("nlm_task_queue")
    nlm_poller.register("source_add", handle_source_add)
    nlm_poller.register("source_remove", handle_source_remove)
    _pollers.append(nlm_poller)

    # --- Drive Task Queue Poller ---
    drive_poller = FirestorePoller("drive_task_queue")
    drive_poller.register("move_to_archive", handle_drive_task)
    drive_poller.register("hard_delete", handle_drive_task)
    _pollers.append(drive_poller)

    # Đăng ký signal handlers
    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    # Khởi động tất cả pollers
    for p in _pollers:
        p.start()

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
