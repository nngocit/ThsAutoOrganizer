# plugins/firestore_poller.py — Plugin Lắng nghe và Phát lệnh từ Firestore Queue (<140 dòng)
import logging
import threading
import time
from typing import Any, Dict, Optional

from .base import COLOR_BLUE, EventBus, PluginBase


class FirestorePollerPlugin(PluginBase):
    """
    Plugin lắng nghe Firestore: Quét nlm_task_queue, cập nhật status 'processing',
    phát sự kiện ON_COURSE_CREATE / ON_SOURCE_ADD và nhận TASK_COMPLETED.
    """

    def __init__(
        self,
        event_bus: EventBus,
        db: Any = None,
        poll_interval: float = 5.0
    ) -> None:
        super().__init__(event_bus, name="POLLER", color=COLOR_BLUE)
        self.db = db
        self.poll_interval = poll_interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Đăng ký lắng nghe sự kiện hoàn thành task từ EventBus
        self.event_bus.on("TASK_COMPLETED", self.on_task_completed)

    def start(self) -> None:
        """Bắt đầu vòng lặp polling trên thread nền (daemon)."""
        super().start()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="FirestorePollerThread"
        )
        self._thread.start()

    def stop(self) -> None:
        """Dừng vòng lặp polling."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        super().stop()

    def _poll_loop(self) -> None:
        """Vòng lặp định kỳ quét task pending từ Firestore."""
        self.log(f"Bắt đầu chu kỳ quét nlm_task_queue (chu kỳ: {self.poll_interval}s)...")
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception as e:
                self.log(f"Lỗi trong vòng lặp polling: {e}", level=logging.ERROR)
            self._stop_event.wait(self.poll_interval)

    def poll_once(self) -> None:
        """Thực hiện một lần quét pending tasks."""
        if not self.db:
            return

        try:
            tasks_ref = self.db.collection("nlm_task_queue")
            # Truy vấn các task có status == 'pending'
            try:
                query = tasks_ref.where("status", "==", "pending")
                docs = query.stream()
            except TypeError:
                from google.cloud.firestore_v1.base_query import FieldFilter
                query = tasks_ref.where(filter=FieldFilter("status", "==", "pending"))
                docs = query.stream()

            for doc in docs:
                task_data = doc.to_dict() or {}
                task_id = doc.id
                task_payload: Dict[str, Any] = dict(task_data)
                task_payload["id"] = task_id
                action = task_payload.get("action")

                if action == "course_create":
                    self._update_task_status(task_id, "processing")
                    self.log(f"Phát hiện task 'course_create' [{task_id}] -> Gửi ON_COURSE_CREATE")
                    self.event_bus.emit("ON_COURSE_CREATE", task_payload)

                elif action == "source_add":
                    self._update_task_status(task_id, "processing")
                    self.log(f"Phát hiện task 'source_add' [{task_id}] -> Gửi ON_SOURCE_ADD")
                    self.event_bus.emit("ON_SOURCE_ADD", task_payload)

        except Exception as e:
            self.log(f"Lỗi khi đọc Firestore queue: {e}", level=logging.WARNING)

    def _update_task_status(self, task_id: str, status: str, result_data: Optional[Dict[str, Any]] = None) -> None:
        """Cập nhật trạng thái của task trong collection nlm_task_queue."""
        if not self.db or not task_id:
            return
        try:
            doc_ref = self.db.collection("nlm_task_queue").document(task_id)
            update_payload: Dict[str, Any] = {
                "status": status,
                "updated_at": time.time(),
            }
            if result_data:
                update_payload.update(result_data)
            doc_ref.update(update_payload)
            self.log(f"Cập nhật task [{task_id}] -> status='{status}'")
        except Exception as e:
            self.log(f"Không thể cập nhật task [{task_id}] lên Firestore: {e}", level=logging.ERROR)

    def on_task_completed(self, payload: Dict[str, Any]) -> None:
        """Xử lý sự kiện TASK_COMPLETED từ EventBus để cập nhật status 'completed'."""
        if not isinstance(payload, dict):
            return
        task_id = payload.get("task_id") or payload.get("id")
        if not task_id:
            self.log("Bỏ qua TASK_COMPLETED do thiếu task_id trong payload.", level=logging.WARNING)
            return

        plugin_source = payload.get("plugin", "unknown")
        result = payload.get("result", {})
        self.log(f"Nhận TASK_COMPLETED từ [{plugin_source}] cho task [{task_id}] -> Lưu status='completed'")
        self._update_task_status(task_id, "completed", {"completed_by": plugin_source, "result": result})
