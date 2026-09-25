import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse, unquote
import requests

from .base import (
    COLOR_GREEN,
    COLOR_ORANGE,
    COLOR_RED,
    COLOR_RESET,
    COLOR_YELLOW,
    EventBus,
    PluginBase,
)

DEFAULT_BASE_PATH = r"H:\2026\Thac Sy\Mon_Hoc"


class LocalStoragePlugin(PluginBase):
    """
    Plugin Lưu trữ Vật lý: Lắng nghe ON_COURSE_CREATE để tạo thư mục,
    ON_SOURCE_ADD để tải file trực tiếp về ổ đĩa trên luồng phụ (Non-blocking),
    và quản lý vòng đời dữ liệu (ARCHIVE, RESTORE, HARD_DELETE).
    """

    def __init__(self, event_bus: EventBus, base_path: str = DEFAULT_BASE_PATH) -> None:
        super().__init__(event_bus, name="STORAGE", color=COLOR_YELLOW)
        self.base_path = Path(base_path)

        # Đăng ký lắng nghe sự kiện từ EventBus
        self.event_bus.on("ON_COURSE_CREATE", self.on_course_create)
        self.event_bus.on("ON_SOURCE_ADD", self.on_source_add)
        self.event_bus.on("ON_COURSE_ARCHIVE", self.on_course_archive)
        self.event_bus.on("ON_COURSE_RESTORE", self.on_course_restore)
        self.event_bus.on("ON_COURSE_HARD_DELETE", self.on_course_hard_delete)

    def _extract_folder_name(self, payload: Dict[str, Any]) -> str:
        """Trích xuất tên thư mục cục bộ an toàn từ payload."""
        if not isinstance(payload, dict):
            return ""
        return (
            payload.get("local_folder_name")
            or payload.get("folder_name")
            or payload.get("display_name")
            or payload.get("name")
            or ""
        ).strip()

    def on_course_create(self, payload: Dict[str, Any]) -> None:
        r"""
        Xử lý sự kiện ON_COURSE_CREATE:
        Dùng os.makedirs tạo thư mục cục bộ H:\2026\Thac Sy\Mon_Hoc\<local_folder_name>.
        """
        folder_name = self._extract_folder_name(payload)

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

    def on_course_archive(self, payload: Dict[str, Any]) -> None:
        r"""
        Xử lý sự kiện ON_COURSE_ARCHIVE:
        KHÔNG XÓA. Dùng os.rename di chuyển thư mục vào H:\2026\Thac Sy\Mon_Hoc\_Archived\<local_folder_name>.
        """
        folder_name = self._extract_folder_name(payload)
        if not folder_name:
            self.log("Bỏ qua ON_COURSE_ARCHIVE vì thiếu tên thư mục.", level=logging.WARNING)
            return

        source_dir = self.base_path / folder_name
        archive_root = self.base_path / "_Archived"
        target_dir = archive_root / folder_name

        try:
            if not source_dir.exists():
                self.log(f"Thư mục nguồn '{source_dir}' không tồn tại, bỏ qua di chuyển.", level=logging.WARNING)
                return

            os.makedirs(archive_root, exist_ok=True)

            if target_dir.exists():
                # Xử lý trường hợp thư mục đích trong _Archived đã tồn tại trước đó
                shutil.rmtree(target_dir)

            os.rename(str(source_dir), str(target_dir))
            prefix = f"{COLOR_ORANGE}[ARCHIVE]{COLOR_RESET}"
            self.logger.info(f"{self.color}[{self.name}]{COLOR_RESET} {prefix} Đã di chuyển vào lưu trữ: '{source_dir}' -> '{target_dir}'")
        except Exception as e:
            self.log(f"✗ Lỗi ngoại lệ khi lưu trữ thư mục '{source_dir}': {e}", level=logging.ERROR)

    def on_course_restore(self, payload: Dict[str, Any]) -> None:
        r"""
        Xử lý sự kiện ON_COURSE_RESTORE:
        Di chuyển thư mục từ _Archived trở lại vị trí gốc.
        """
        folder_name = self._extract_folder_name(payload)
        if not folder_name:
            self.log("Bỏ qua ON_COURSE_RESTORE vì thiếu tên thư mục.", level=logging.WARNING)
            return

        source_dir = self.base_path / "_Archived" / folder_name
        target_dir = self.base_path / folder_name

        try:
            if not source_dir.exists():
                self.log(f"Thư mục lưu trữ '{source_dir}' không tồn tại, không thể khôi phục.", level=logging.WARNING)
                return

            os.makedirs(self.base_path, exist_ok=True)

            if target_dir.exists():
                shutil.rmtree(target_dir)

            os.rename(str(source_dir), str(target_dir))
            prefix = f"{COLOR_GREEN}[RESTORE]{COLOR_RESET}"
            self.logger.info(f"{self.color}[{self.name}]{COLOR_RESET} {prefix} Đã khôi phục thư mục: '{source_dir}' -> '{target_dir}'")
        except Exception as e:
            self.log(f"✗ Lỗi ngoại lệ khi khôi phục thư mục '{source_dir}': {e}", level=logging.ERROR)

    def on_course_hard_delete(self, payload: Dict[str, Any]) -> None:
        r"""
        Xử lý sự kiện ON_COURSE_HARD_DELETE:
        Dùng shutil.rmtree xóa sạch cây thư mục tương ứng BÊN TRONG thư mục _Archived.
        """
        folder_name = self._extract_folder_name(payload)
        if not folder_name:
            self.log("Bỏ qua ON_COURSE_HARD_DELETE vì thiếu tên thư mục.", level=logging.WARNING)
            return

        target_dir = self.base_path / "_Archived" / folder_name

        try:
            if not target_dir.exists():
                self.log(f"Thư mục cần xóa '{target_dir}' không tồn tại trong _Archived.", level=logging.WARNING)
                return

            shutil.rmtree(target_dir)
            prefix = f"{COLOR_RED}[PURGE]{COLOR_RESET}"
            self.logger.info(f"{self.color}[{self.name}]{COLOR_RESET} {prefix} Đã xóa vĩnh viễn thư mục: '{target_dir}'")
        except Exception as e:
            self.log(f"✗ Lỗi ngoại lệ khi xóa vĩnh viễn thư mục '{target_dir}': {e}", level=logging.ERROR)

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
