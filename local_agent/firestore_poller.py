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

# Type alias cho handler function
TaskHandler = Callable[[dict], None]


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
            resp = requests.get(url, headers=self._auth_headers(), timeout=15)
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
            requests.patch(url, json=payload, headers=self._auth_headers(), timeout=15)
        except requests.RequestException as e:
            logger.warning("[%s] Không thể mark task %s: %s", self.queue_name, task_id, e)

    def _process_task(self, task: dict) -> None:
        """Xử lý một task: tìm handler phù hợp và chạy."""
        task_id = task.get("id", "unknown")
        action = task.get("action", "")

        if action not in self._handlers:
            logger.warning("[%s] Không có handler cho action '%s'", self.queue_name, action)
            self._mark_task(task_id, "failed", error=f"No handler for action: {action}")
            return

        # Mark processing trước khi chạy
        self._mark_task(task_id, "processing")
        try:
            for handler in self._handlers[action]:
                handler(task)
            self._mark_task(task_id, "done")
            logger.info("[%s] Task %s (%s) hoàn tất", self.queue_name, task_id, action)
        except Exception as exc:
            logger.exception("[%s] Task %s (%s) thất bại: %s", self.queue_name, task_id, action, exc)
            self._mark_task(task_id, "failed", error=str(exc))

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
