"""Module đồng bộ 2 chiều: Tự động phát hiện và kéo tài liệu từ Google Drive về máy tính."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.classifier import PathClassifier
from src.database import Database, STATUS_UPLOADED
from src.drive import DriveManager
from src.processor import calculate_sha256

logger = logging.getLogger("ThsAutoOrganizer.sync")


def find_or_create_local_subject_dir(root_folder: Path, subject_name: str, classifier: Optional[PathClassifier] = None) -> Path:
    """Xác định thư mục môn học trên máy tính phù hợp với tên môn trên Drive."""
    # 1. Tìm xem thư mục nào trên máy khớp với subject_name
    for sub_dir in root_folder.iterdir():
        if sub_dir.is_dir():
            # Nếu tên thư mục trùng tên môn tiếng Việt hoặc trùng sau khi bỏ dấu/thay _
            if sub_dir.name == subject_name:
                return sub_dir
            if classifier and classifier.subject_map.get(sub_dir.name) == subject_name:
                return sub_dir
            if sub_dir.name.replace("_", " ").lower() == subject_name.replace("_", " ").lower():
                return sub_dir

    # 2. Nếu chưa có, tạo thư mục mới theo tên subject_name
    new_dir = root_folder / subject_name
    new_dir.mkdir(parents=True, exist_ok=True)
    return new_dir


def sync_from_drive_to_local(
    drive_manager: DriveManager,
    database: Database,
    root_folder: Path | str,
    classifier: Optional[PathClassifier] = None,
    user_email: str = "xuanngocit@gmail.com",
) -> List[Dict[str, Any]]:
    """Quét Google Drive và tải các file mới về máy tính cho tài khoản user_email.

    Returns:
        Danh sách các file vừa được tải về thành công.
    """
    if not drive_manager or not drive_manager.is_configured():
        logger.warning("Google Drive chưa cấu hình, không thể đồng bộ về máy.")
        return []

    root_path = Path(root_folder).resolve()
    if not root_path.is_dir():
        root_path.mkdir(parents=True, exist_ok=True)

    logger.info("Đang kiểm tra tài liệu mới trên Google Drive cho tài khoản %s...", user_email)
    materials = drive_manager.list_all_study_materials()
    downloaded_files: List[Dict[str, Any]] = []

    for mat in materials:
        drive_file_id = mat["file_id"]
        file_name = mat["name"]
        subject = mat["subject"]
        doc_type = mat["document_type"]

        # Kiểm tra xem file đã có trong database chưa
        db_rec = database.find_by_drive_file_id(drive_file_id, user_email=user_email)

        # Xác định đường dẫn cục bộ dự kiến
        subject_dir = find_or_create_local_subject_dir(root_path, subject, classifier)
        target_file_path = subject_dir / file_name

        # Nếu file đã tồn tại trên đĩa cứng
        if target_file_path.is_file():
            # Đảm bảo database đã có record
            if not db_rec:
                file_sha256 = calculate_sha256(target_file_path)
                database.insert_record(
                    sha256=file_sha256,
                    path=str(target_file_path),
                    subject=subject,
                    document_type=doc_type,
                    status=STATUS_UPLOADED,
                    drive_file_id=drive_file_id,
                    user_email=user_email,
                )
            continue

        # File có trên Drive nhưng chưa có trên máy -> Tiến hành tải về!
        logger.info("📥 Phát hiện tài liệu mới trên Drive: '%s' (Môn: %s). Đang tải về máy...", file_name, subject)
        try:
            drive_manager.download_file(drive_file_id, target_file_path)
            file_sha256 = calculate_sha256(target_file_path)

            # Ghi nhận ngay vào SQLite là UPLOADED để Watchdog không upload lặp lại
            database.insert_record(
                sha256=file_sha256,
                path=str(target_file_path),
                subject=subject,
                document_type=doc_type,
                status=STATUS_UPLOADED,
                drive_file_id=drive_file_id,
                user_email=user_email,
            )

            downloaded_files.append({
                "file_name": file_name,
                "local_path": str(target_file_path),
                "subject": subject,
                "document_type": doc_type,
                "drive_file_id": drive_file_id,
            })
            logger.info("✅ Đã kéo thành công tài liệu về: '%s'", target_file_path)
        except Exception as exc:
            logger.error("Lỗi khi tải file '%s' từ Drive về: %s", file_name, exc, exc_info=True)

    if downloaded_files:
        logger.info("Đã tải về hoàn tất %d tài liệu mới từ Google Drive!", len(downloaded_files))
    else:
        logger.info("Máy tính đã đồng bộ hoàn toàn với Google Drive, không có tài liệu mới cần tải.")

    return downloaded_files


class AutoDriveSyncWorker:
    """Worker chạy nền tự động quét và kéo tài liệu mới từ Google Drive về máy định kỳ."""

    def __init__(
        self,
        drive_manager: DriveManager,
        database: Database,
        root_folder: Path | str,
        classifier: Optional[PathClassifier] = None,
        interval_seconds: int = 180,
        enabled: bool = True,
        user_email: str = "xuanngocit@gmail.com",
    ) -> None:
        self.drive_manager = drive_manager
        self.database = database
        self.root_folder = Path(root_folder).resolve()
        self.classifier = classifier
        self.interval_seconds = max(30, int(interval_seconds))
        self.enabled = enabled
        self.user_email = user_email

        import threading
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sync_lock = threading.Lock()

        # Trạng thái theo dõi
        self.is_syncing: bool = False
        self.last_sync_time: Optional[float] = None
        self.last_sync_status: str = "Chưa chạy"
        self.recently_downloaded_ids: set[str] = set()

    def start(self) -> None:
        """Bắt đầu luồng kiểm tra tự động nền."""
        if not self.enabled:
            logger.info("Tự động đồng bộ Drive đang tắt trong cấu hình.")
            return

        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        import threading
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="AutoDriveSyncWorker",
        )
        self._thread.start()
        logger.info(
            "🚀 Đã kích hoạt tính năng TỰ ĐỘNG KÉO TÀI LIỆU từ Google Drive (Chu kỳ: %d giây / %.1f phút).",
            self.interval_seconds,
            self.interval_seconds / 60,
        )

    def stop(self) -> None:
        """Dừng luồng nền một cách an toàn."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("Đã dừng luồng tự động đồng bộ Google Drive.")

    def trigger_now(self) -> List[Dict[str, Any]]:
        """Kích hoạt đồng bộ ngay lập tức (dùng khi bấm nút trên giao diện)."""
        return self._do_sync()

    def update_settings(self, enabled: Optional[bool] = None, interval_seconds: Optional[int] = None) -> None:
        """Cập nhật cài đặt chu kỳ và bật/tắt từ Web Dashboard."""
        if interval_seconds is not None:
            self.interval_seconds = max(30, int(interval_seconds))
        if enabled is not None:
            self.enabled = bool(enabled)
            if self.enabled and (not self._thread or not self._thread.is_alive()):
                self.start()

    def _do_sync(self) -> List[Dict[str, Any]]:
        with self._sync_lock:
            if self.is_syncing:
                return []
            self.is_syncing = True

        import time
        self.last_sync_status = "Đang kiểm tra Google Drive..."
        try:
            downloaded = sync_from_drive_to_local(
                drive_manager=self.drive_manager,
                database=self.database,
                root_folder=self.root_folder,
                classifier=self.classifier,
                user_email=self.user_email,
            )
            self.last_sync_time = time.time()
            if downloaded:
                for item in downloaded:
                    if item.get("drive_file_id"):
                        self.recently_downloaded_ids.add(item["drive_file_id"])
                self.last_sync_status = f"Thành công (+{len(downloaded)} tài liệu mới)"
            else:
                self.last_sync_status = "Đã đồng bộ (Không có file mới)"
            return downloaded
        except Exception as exc:
            self.last_sync_time = time.time()
            self.last_sync_status = f"Lỗi: {exc}"
            logger.error("Lỗi tự động kéo tài liệu từ Drive: %s", exc, exc_info=True)
            return []
        finally:
            self.is_syncing = False

    def _run_loop(self) -> None:
        # Chờ 5s lúc khởi động để local scan hoàn tất trước
        if self._stop_event.wait(timeout=5.0):
            return

        while not self._stop_event.is_set():
            if self.enabled and self.drive_manager and self.drive_manager.is_configured():
                try:
                    self._do_sync()
                except Exception as exc:
                    logger.error("Lỗi trong vòng lặp auto sync: %s", exc)

            # Chờ đúng interval_seconds (hoặc thức dậy ngay nếu có lệnh stop)
            if self._stop_event.wait(timeout=self.interval_seconds):
                break

    def get_status_info(self) -> Dict[str, Any]:
        """Trả về thông tin trạng thái phục vụ hiển thị trên Web Studio."""
        import time
        last_str = "Chưa đồng bộ"
        if self.last_sync_time:
            diff = int(time.time() - self.last_sync_time)
            if diff < 60:
                last_str = f"{diff} giây trước"
            elif diff < 3600:
                last_str = f"{diff // 60} phút trước"
            else:
                last_str = f"{diff // 3600} giờ trước"

        return {
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "interval_minutes": round(self.interval_seconds / 60, 1),
            "is_syncing": self.is_syncing,
            "last_sync_time": self.last_sync_time,
            "last_sync_human": last_str,
            "last_sync_status": self.last_sync_status,
            "recent_drive_ids": list(self.recently_downloaded_ids),
        }

