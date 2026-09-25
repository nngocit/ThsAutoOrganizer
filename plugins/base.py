# plugins/base.py — EventBus & PluginBase cho kiến trúc Event-Driven (<120 dòng)
import logging
import threading
from typing import Any, Callable, Dict, List, Optional

# ANSI Color Codes
COLOR_RESET = "\033[0m"
COLOR_BLUE = "\033[94m"     # [POLLER]
COLOR_PURPLE = "\033[95m"   # [AI_CLI]
COLOR_YELLOW = "\033[93m"   # [STORAGE]
COLOR_GREEN = "\033[92m"    # [BUS] / [RESTORE]
COLOR_RED = "\033[91m"      # [PURGE]
COLOR_ORANGE = "\033[38;5;208m"  # [ARCHIVE]
COLOR_CYAN = "\033[96m"


class EventBus:
    """Pub/Sub Event Bus điều phối sự kiện giữa các plugin độc lập (Thread-safe)."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[..., Any]]] = {}
        self._lock = threading.RLock()
        self._logger = logging.getLogger("EventBus")

    def on(self, event_name: str, handler: Callable[..., Any]) -> None:
        """Đăng ký lắng nghe một sự kiện (Subscribe)."""
        with self._lock:
            if event_name not in self._subscribers:
                self._subscribers[event_name] = []
            if handler not in self._subscribers[event_name]:
                self._subscribers[event_name].append(handler)

    def subscribe(self, event_name: str, handler: Callable[..., Any]) -> None:
        """Alias cho phương thức `on`."""
        self.on(event_name, handler)

    def off(self, event_name: str, handler: Callable[..., Any]) -> None:
        """Hủy đăng ký lắng nghe sự kiện (Unsubscribe)."""
        with self._lock:
            if event_name in self._subscribers and handler in self._subscribers[event_name]:
                self._subscribers[event_name].remove(handler)

    def emit(self, event_name: str, payload: Any = None) -> None:
        """Phát một sự kiện tới tất cả các subscriber đã đăng ký (Publish)."""
        with self._lock:
            handlers = list(self._subscribers.get(event_name, []))

        for handler in handlers:
            try:
                handler(payload)
            except Exception as e:
                self._logger.error(
                    f"{COLOR_RED}[EVENT_BUS ERROR]{COLOR_RESET} Lỗi xử lý sự kiện '{event_name}' bởi {handler.__name__}: {e}",
                    exc_info=True
                )


class PluginBase:
    """Lớp cơ sở (Abstract Base) cho tất cả các Plugin trong hệ thống."""

    def __init__(self, event_bus: EventBus, name: str = "PLUGIN", color: str = COLOR_BLUE) -> None:
        self.event_bus: EventBus = event_bus
        self.name: str = name
        self.color: str = color
        self.logger = logging.getLogger(f"plugins.{name.lower()}")
        self._is_running: bool = False

    def log(self, message: str, level: int = logging.INFO) -> None:
        """Ghi log kèm tiền tố màu nhận diện của Plugin."""
        prefix = f"{self.color}[{self.name}]{COLOR_RESET}"
        self.logger.log(level, f"{prefix} {message}")

    def start(self) -> None:
        """Khởi động Plugin."""
        self._is_running = True
        self.log("Đã khởi động.")

    def stop(self) -> None:
        """Dừng Plugin."""
        self._is_running = False
        self.log("Đã dừng.")
