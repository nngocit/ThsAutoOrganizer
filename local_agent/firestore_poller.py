# local_agent/firestore_poller.py — Poll task queues từ Worker API (<150 lines)
# Gọi GET /api/tasks/:queue mỗi poll_interval_seconds giây
# Dispatch task tới handler đã đăng ký

import time
import logging
import threading
from typing import Callable
import requests

from .config_loader import get

logger = logging.getLogger(__name__)

# Type alias cho handler function — return str (kết quả) hoặc None
TaskHandler = Callable[[dict], str | None]


class FirestorePoller:
    """
    Poll Cloudflare Worker task queue API định kỳ.
    
    Mỗi queue có một set handlers đăng ký theo action name.
    Agent chạy mỗi queue trong một thread daemon riêng.
    """

    def __init__(self, queue_name: str, interval: float | None = None):
        self.queue_name = queue_name
        self.interval = interval or float(get("poll_interval_seconds", 10))
        self._handlers: dict[str, list[TaskHandler]] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self._session = requests.Session()
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            retries = Retry(total=2, backoff_factor=1, status_forcelist=[502, 503, 504])
            adapter = HTTPAdapter(max_retries=retries, pool_connections=5, pool_maxsize=10)
            self._session.mount("https://", adapter)
        except Exception:
            pass

    def register(self, action: str, handler: TaskHandler) -> None:
        """Đăng ký handler cho action type."""
        if action not in self._handlers:
            self._handlers[action] = []
        self._handlers[action].append(handler)
        logger.debug("Registered handler for %s:%s", self.queue_name, action)

    def _auth_headers(self) -> dict[str, str]:
        return {
            "X-Agent-Secret": get("agent_secret", ""),
            "Content-Type": "application/json",
        }

    def _get_pending_tasks(self) -> list[dict]:
        """Lấy danh sách pending tasks từ Worker API."""
        worker_url = get("worker_url", "").rstrip("/")
        limit = get("task_queue_limit", 10)
        url = f"{worker_url}/api/tasks/{self.queue_name}?limit={limit}"
        try:
            resp = self._session.get(url, headers=self._auth_headers(), timeout=30)
            resp.raise_for_status()
            return resp.json().get("tasks", [])
        except requests.RequestException as e:
            logger.warning("[%s] Không thể lấy tasks: %s", self.queue_name, e)
            return []

    def _mark_task(self, task_id: str, status: str, error: str = "", result: str = "") -> None:
        """Báo cáo kết quả xử lý task về Worker API."""
        worker_url = get("worker_url", "").rstrip("/")
        url = f"{worker_url}/api/tasks/{self.queue_name}/{task_id}"
        payload: dict = {"status": status}
        if error:
            payload["error"] = error
        if result:
            payload["result"] = result
        try:
            self._session.patch(url, json=payload, headers=self._auth_headers(), timeout=30)
        except requests.RequestException as e:
            logger.warning("[%s] Không thể mark task %s: %s", self.queue_name, task_id, e)

    def _process_task(self, task: dict) -> str:
        """Xử lý một task: tìm handler phù hợp và chạy.

        Returns:
            Trạng thái đã báo về Worker: 'done' | 'skipped_ext' |
            'skipped_no_course' | 'failed' | 'no_handler'.
        """
        task_id = task.get("id", "unknown")
        action = task.get("action", "")

        if action not in self._handlers:
            logger.warning("[%s] Không có handler cho action '%s'", self.queue_name, action)
            self._mark_task(task_id, "failed", error=f"No handler for action: {action}")
            return "no_handler"

        # Mark processing trước khi chạy
        self._mark_task(task_id, "processing")
        try:
            result: str | None = None
            for handler in self._handlers[action]:
                r = handler(task)
                if isinstance(r, str) and r:
                    result = r  # giữ kết quả cuối cùng không rỗng (vd: source_id hoặc skipped_ext)
            
            if result == "skipped_ext":
                self._mark_task(task_id, "skipped_ext", result="skipped_ext")
                logger.info("[%s] Task %s (%s) bỏ qua (skipped_ext)", self.queue_name, task_id, action)
                return "skipped_ext"
            elif result == "skipped_no_course":
                self._mark_task(task_id, "skipped_no_course", result="skipped_no_course")
                logger.info("[%s] Task %s (%s) bỏ qua (skipped_no_course)", self.queue_name, task_id, action)
                return "skipped_no_course"
            else:
                self._mark_task(task_id, "done", result=result or "")
                logger.info("[%s] Task %s (%s) hoàn tất", self.queue_name, task_id, action)
                return "done"
        except Exception as exc:
            logger.exception("[%s] Task %s (%s) thất bại: %s", self.queue_name, task_id, action, exc)
            self._mark_task(task_id, "failed", error=str(exc))
            return "failed"

    # ---------- Chế độ "chạy rồi thoát" (drain) cho GitHub Actions / Termux ----------

    def fetch_pending(self) -> list[dict]:
        """Public wrapper: lấy danh sách task đang pending của queue này."""
        return self._get_pending_tasks()

    def run_once(self) -> dict[str, int]:
        """Xử lý đúng MỘT vòng: nhặt toàn bộ task pending hiện có rồi trả về thống kê.

        Returns:
            {"processed": n, "done": n, "failed": n, "skipped": n, "no_handler": n}
        """
        summary = {"processed": 0, "done": 0, "failed": 0, "skipped": 0, "no_handler": 0}
        for task in self._get_pending_tasks():
            status = self._process_task(task)
            summary["processed"] += 1
            if status == "done":
                summary["done"] += 1
            elif status == "failed":
                summary["failed"] += 1
            elif status == "no_handler":
                summary["no_handler"] += 1
            else:
                summary["skipped"] += 1
        return summary

    def run_until_idle(self, max_passes: int = 30, idle_sleep: float = 5.0) -> dict[str, int]:
        """Chạy nhiều vòng cho tới khi hàng đợi rỗng (luôn hữu hạn vòng).

        Dùng cho môi trường "chạy rồi thoát" (GitHub Actions / Termux) — KHÁC với
        start() vốn chạy thread nền vô hạn cho PC.

        Args:
            max_passes: số vòng tối đa (chặn treo vô hạn).
            idle_sleep: giây nghỉ giữa 2 vòng để không dồn dập API.
        """
        total = {"processed": 0, "done": 0, "failed": 0, "skipped": 0,
                 "no_handler": 0, "passes": 0}
        for _ in range(max(1, int(max_passes))):
            one = self.run_once()
            total["passes"] += 1
            for key in ("processed", "done", "failed", "skipped", "no_handler"):
                total[key] += one[key]
            if one["processed"] == 0:
                break
            if idle_sleep > 0:
                time.sleep(idle_sleep)
        return total

    def _poll_loop(self) -> None:
        """Vòng lặp poll chính — chạy trong thread daemon."""
        logger.info("[%s] Bắt đầu polling mỗi %.0fs", self.queue_name, self.interval)
        while self._running:
            tasks = self._get_pending_tasks()
            for task in tasks:
                if not self._running:
                    break
                self._process_task(task)
            time.sleep(self.interval)
        logger.info("[%s] Polling dừng", self.queue_name)

    def start(self) -> None:
        """Khởi động thread polling."""
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            name=f"poller-{self.queue_name}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Dừng thread polling."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
