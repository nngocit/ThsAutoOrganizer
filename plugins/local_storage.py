# plugins/local_storage.py — Plugin Quản lý Lưu trữ Vật lý Cục bộ (<140 dòng)
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse, unquote
import requests

from .base import COLOR_YELLOW, EventBus, PluginBase

DEFAULT_BASE_PATH = r"H:\2026\Thac Sy\Mon_Hoc"


class LocalStoragePlugin(PluginBase):
    """
    Plugin Lưu trữ Vật lý: Lắng nghe ON_COURSE_CREATE để tạo thư mục,
    và ON_SOURCE_ADD để tải file trực tiếp về ổ đĩa trên luồng phụ (Non-blocking).
    """

    def __init__(self, event_bus: EventBus, base_path: str = DEFAULT_BASE_PATH) -> None:
        super().__init__(event_bus, name="STORAGE", color=COLOR_YELLOW)
        self.base_path = Path(base_path)

        # Đăng ký lắng nghe sự kiện từ EventBus
        self.event_bus.on("ON_COURSE_CREATE", self.on_course_create)
        self.event_bus.on("ON_SOURCE_ADD", self.on_source_add)

    def on_course_create(self, payload: Dict[str, Any]) -> None:
        r"""
        Xử lý sự kiện ON_COURSE_CREATE:
        Dùng os.makedirs tạo thư mục cục bộ H:\2026\Thac Sy\Mon_Hoc\<local_folder_name>.
        """
        if not isinstance(payload, dict):
            return

        folder_name = (
            payload.get("local_folder_name")
            or payload.get("folder_name")
            or payload.get("display_name")
            or payload.get("name")
            or ""
        ).strip()

        if not folder_name:
            self.log("Bỏ qua ON_COURSE_CREATE vì không tìm thấy tên thư mục cục bộ.", level=logging.WARNING)
            return

        target_dir = self.base_path / folder_name
        self.log(f"Đang tạo thư mục vật lý cục bộ: '{target_dir}'...")
        try:
            os.makedirs(target_dir, exist_ok=True)
            self.log(f"✓ Đã tạo (hoặc sẵn sàng) thư mục: {target_dir}")
        except Exception as e:
            self.log(f"✗ Lỗi khi tạo thư mục '{target_dir}': {e}", level=logging.ERROR)

    def on_source_add(self, payload: Dict[str, Any]) -> None:
        """
        Xử lý sự kiện ON_SOURCE_ADD:
        Tải file từ file_url về thư mục vật lý tương ứng trên luồng phụ (Daemon Thread).
        """
        if not isinstance(payload, dict):
            return

        file_url = payload.get("file_url") or payload.get("url")
        folder_name = payload.get("local_folder_name") or payload.get("folder_name") or ""
        filename = payload.get("filename")

        if not file_url:
            self.log("Bỏ qua ON_SOURCE_ADD vì thiếu file_url.", level=logging.WARNING)
            return

        # Khởi chạy tải file trên luồng phụ để không làm nghẽn EventBus
        thread = threading.Thread(
            target=self._download_worker,
            args=(file_url, folder_name, filename, payload),
            daemon=True,
            name="StorageDownloadThread"
        )
        thread.start()

    def _resolve_filename(self, file_url: str, filename: Optional[str]) -> str:
        """Xác định tên tệp tin an toàn từ payload hoặc URL."""
        if filename:
            return filename
        path = unquote(urlparse(file_url).path)
        base = os.path.basename(path)
        return base if base else "downloaded_document.pdf"

    def _download_worker(
        self,
        file_url: str,
        folder_name: str,
        filename: Optional[str],
        payload: Dict[str, Any]
    ) -> None:
        """Thực hiện tải file và lưu trữ an toàn."""
        target_name = self._resolve_filename(file_url, filename)
        target_dir = (self.base_path / folder_name) if folder_name else self.base_path
        target_path = target_dir / target_name

        self.log(f"Bắt đầu tải file: '{target_name}' từ URL về '{target_dir}'...")
        try:
            os.makedirs(target_dir, exist_ok=True)

            with requests.get(file_url, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                with open(target_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)

            size_bytes = os.path.getsize(target_path)
            self.log(f"✓ Đã tải xong file: '{target_path.name}' ({size_bytes} bytes)")
        except requests.RequestException as e:
            self.log(f"✗ Lỗi mạng khi tải file từ '{file_url}': {e}", level=logging.ERROR)
        except Exception as e:
            self.log(f"✗ Ngoại lệ khi lưu file vật lý '{target_path}': {e}", level=logging.ERROR)
