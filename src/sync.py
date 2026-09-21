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
) -> List[Dict[str, Any]]:
    """Quét Google Drive và tải các file mới về máy tính.

    Returns:
        Danh sách các file vừa được tải về thành công.
    """
    if not drive_manager or not drive_manager.is_configured():
        logger.warning("Google Drive chưa cấu hình, không thể đồng bộ về máy.")
        return []

    root_path = Path(root_folder).resolve()
    if not root_path.is_dir():
        root_path.mkdir(parents=True, exist_ok=True)

    logger.info("Đang kiểm tra tài liệu mới trên Google Drive...")
    materials = drive_manager.list_all_study_materials()
    downloaded_files: List[Dict[str, Any]] = []

    for mat in materials:
        drive_file_id = mat["file_id"]
        file_name = mat["name"]
        subject = mat["subject"]
        doc_type = mat["document_type"]

        # Kiểm tra xem file đã có trong database chưa
        db_rec = database.find_by_drive_file_id(drive_file_id)

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
