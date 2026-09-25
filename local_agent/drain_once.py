# local_agent/drain_once.py — Chế độ "chạy rồi thoát" cho GitHub Actions / Termux
#
# KHÁC với main.py (chạy vô hạn trên PC):
#   - Chỉ xử lý hàng đợi tới khi rỗng (hoặc hết max-passes) rồi EXIT.
#   - KHÔNG import FileWatcher (watchdog), drive_sync (googleapiclient),
#     local_reconciler (quét ổ đĩa) → môi trường cloud chỉ cần 2 gói:
#     pip install requests notebooklm-mcp-cli
#
# Cách dùng:
#   python -m local_agent.drain_once --max-passes 30
#   python -m local_agent.drain_once --dry-run      # chỉ kiểm tra cấu hình, KHÔNG gọi API

import argparse
import json
import logging
import sys

from .config_loader import load_config, sync_remote_config
from .firestore_poller import FirestorePoller
from .nlm_task_handler import handle_source_add, handle_source_remove, handle_course_create
from .chat_task_handler import handle_chat_query
from .research_task_handler import handle_research_start
from .exam_task_handler import handle_exam_generate

logger = logging.getLogger(__name__)

# Bộ handler chạy được trên cloud (máy tạm, không có ổ đĩa người dùng).
# KHÔNG gồm: artifact_download (cần googleapiclient + token.json để upload Drive)
#            reconcile_local (cần quét ổ đĩa vật lý của PC)
#            source_remove vẫn giữ vì chỉ gọi nlm CLI.
CLOUD_ACTIONS = {
    "source_add": handle_source_add,
    "source_remove": handle_source_remove,
    "course_create": handle_course_create,
    "chat_query": handle_chat_query,
    "research_start": handle_research_start,
    "exam_generate": handle_exam_generate,
}

# Task PC-only: runner cloud PHẢI bỏ qua và GIỮ NGUYÊN pending
# (không được mark failed — nếu không PC sẽ không bao giờ nhặt lại).
FOREIGN_ACTIONS = {"reconcile_local", "artifact_download"}

DEFAULT_QUEUE = "nlm_task_queue"


def build_poller(queue_name: str = DEFAULT_QUEUE) -> FirestorePoller:
    """Tạo poller cho queue NLM với đúng bộ handler chạy được trên cloud."""
    poller = FirestorePoller(queue_name, foreign_actions=FOREIGN_ACTIONS)
    for action, handler in CLOUD_ACTIONS.items():
        poller.register(action, handler)
    return poller


def _config_ok(cfg: dict) -> str:
    """Trả về thông báo lỗi đầu tiên ('' nếu cấu hình hợp lệ)."""
    if not cfg.get("worker_url"):
        return "worker_url trống — kiểm tra config.json hoặc biến môi trường WORKER_URL"
    if not cfg.get("agent_secret"):
        return "agent_secret trống — kiểm tra config.json hoặc biến môi trường AGENT_SECRET"
    return ""


def main(argv: list[str] | None = None) -> int:
    """Chạy drain 1 lần. Exit code: 0 = OK, 1 = có task lỗi, 2 = cấu hình sai."""
    parser = argparse.ArgumentParser(
        description="Drain hàng đợi nlm_task_queue một lần rồi thoát (GitHub Actions / Termux)")
    parser.add_argument("--max-passes", type=int, default=30,
                        help="Số vòng poll tối đa (mặc định 30)")
    parser.add_argument("--idle-sleep", type=float, default=5.0,
                        help="Giây nghỉ giữa 2 vòng (mặc định 5)")
    parser.add_argument("--queue", default=DEFAULT_QUEUE, help="Tên queue Firestore")
    parser.add_argument("--dry-run", action="store_true",
                        help="Chỉ kiểm tra cấu hình rồi thoát, KHÔNG gọi API/không xử lý task")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # config.json bị .gitignore → trên runner phải tạo file rỗng '{}',
    # giá trị thật lấy từ biến môi trường (config_loader ưu tiên env).
    try:
        cfg = load_config()
    except FileNotFoundError:
        logger.error(
            "Không tìm thấy config.json. Trên runner hãy chạy: echo '{}' > config.json "
            "rồi cấu hình WORKER_URL / AGENT_SECRET / LOCAL_BASE_PATH qua biến môi trường."
        )
        return 2

    error = _config_ok(cfg)
    if error:
        logger.error(error)
        return 2

    if args.dry_run:
        logger.info("Dry-run OK: queue=%s, worker=%s, local_base_path=%s",
                    args.queue, cfg.get("worker_url"), cfg.get("local_base_path"))
        return 0

    # Nạp Global Settings từ Firestore (không bắt buộc — lỗi thì dùng local fallback)
    try:
        cfg = sync_remote_config()
    except Exception as exc:  # noqa: BLE001 — mọi lỗi mạng chỉ là cảnh báo
        logger.warning("Không nạp được remote config (dùng fallback local): %s", exc)

    logger.info("Bắt đầu drain: queue=%s, worker=%s, local_base_path=%s",
                args.queue, cfg.get("worker_url"), cfg.get("local_base_path"))

    poller = build_poller(args.queue)
    try:
        summary = poller.run_until_idle(max_passes=args.max_passes,
                                        idle_sleep=args.idle_sleep)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Drain thất bại: %s", exc)
        return 1

    print(json.dumps(summary, ensure_ascii=False))
    if summary.get("foreign"):
        logger.info("Bỏ qua %d task của runner khác (foreign) — giữ nguyên pending",
                    summary["foreign"])
    if summary["failed"] or summary["no_handler"]:
        logger.error("Có %d task lỗi và %d task không có handler",
                     summary["failed"], summary["no_handler"])
        return 1

    logger.info("Hoàn tất drain: %d task đã xử lý (%d vòng, %d bỏ qua)",
                summary["processed"], summary["passes"], summary["skipped"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
