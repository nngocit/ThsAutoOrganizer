"""Module điều phối quy trình xử lý tài liệu (Pipeline Orchestrator).

Luồng xử lý:
File -> Validate -> Classify -> Extract text -> SHA-256 -> SQLite Check -> Upload Drive -> Lưu SQLite
"""

from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from src.classifier import PathClassifier, ClassifierError
from src.database import (
    Database,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_UPLOADED,
    STATUS_DUPLICATE,
    STATUS_ERROR,
)
from src.drive import DriveManager, CredentialsNotFoundError, DriveError
from src.extractors import extract_text, ExtractionError

logger = logging.getLogger("ThsAutoOrganizer.processor")

DEFAULT_SUPPORTED_EXTENSIONS = [".pdf", ".docx", ".pptx", ".txt", ".md"]


@dataclass
class ProcessingResult:
    """Kết quả xử lý một file."""
    file_path: str
    sha256: Optional[str]
    subject: Optional[str]
    document_type: Optional[str]
    status: str
    drive_file_id: Optional[str] = None
    error: Optional[str] = None
    extracted_text_len: int = 0


def calculate_sha256(file_path: Path, chunk_size: int = 65536) -> str:
    """Tính hash SHA-256 theo khối (chunk) để không gây tràn RAM với file lớn."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def is_file_stable(
    file_path: Path | str,
    wait_seconds: float = 3.0,
    check_interval: float = 1.0,
    max_wait_seconds: float = 60.0,
) -> bool:
    """Kiểm tra file đã sao chép/ghi hoàn tất hay chưa dựa vào kích thước file không đổi.

    Đồng thời thử mở file ở chế độ đọc để đảm bảo không bị khóa bởi tiến trình khác.
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        return False

    start_time = time.time()
    last_size = -1
    stable_since = None

    while time.time() - start_time < max_wait_seconds:
        try:
            current_size = path.stat().st_size
        except OSError:
            # File có thể đang bị hệ điều hành khóa tạm thời
            time.sleep(check_interval)
            continue

        if current_size == last_size and current_size > 0:
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= wait_seconds:
                # Thử mở file xem còn bị write-lock hay không
                try:
                    with open(path, "rb"):
                        return True
                except (OSError, PermissionError):
                    # Vẫn đang bị khóa
                    pass
        else:
            last_size = current_size
            stable_since = None

        time.sleep(check_interval)

    logger.warning("File '%s' không ổn định sau %.1fs chờ đợi.", path, max_wait_seconds)
    return False


class FileProcessor:
    """Bộ điều phối xử lý tập tin theo pipeline chuẩn."""

    def __init__(
        self,
        classifier: PathClassifier,
        database: Database,
        drive_manager: Optional[DriveManager] = None,
        min_file_size_bytes: int = 1000,
        supported_extensions: Optional[List[str]] = None,
        extract_content: bool = True,
    ) -> None:
        self.classifier = classifier
        self.database = database
        self.drive_manager = drive_manager
        self.min_file_size_bytes = min_file_size_bytes
        self.supported_extensions = [
            ext.lower() for ext in (supported_extensions or DEFAULT_SUPPORTED_EXTENSIONS)
        ]
        self.extract_content = extract_content

    def should_process_file(self, file_path: Path | str) -> bool:
        """Kiểm tra sơ bộ file có đủ điều kiện xử lý hay không."""
        path = Path(file_path).resolve()
        name = path.name

        # Bỏ qua các file tạm của Office và hệ thống
        if (
            name.startswith("~$")
            or name.startswith(".~")
            or name.startswith(".tmp")
            or name.endswith(".tmp")
            or name.endswith(".crdownload")
            or name.endswith(".part")
            or name.startswith(".git")
        ):
            return False

        ext = path.suffix.lower()
        if ext not in self.supported_extensions:
            return False

        return True

    def process_file(self, file_path: Path | str) -> ProcessingResult:
        """Thực thi toàn bộ pipeline cho một file."""
        path = Path(file_path).resolve()
        logger.info("Detected: %s", path.name)

        if not path.is_file():
            err_msg = f"File không tồn tại hoặc đã bị xóa: '{path}'"
            logger.warning(err_msg)
            return ProcessingResult(
                file_path=str(path),
                sha256=None,
                subject=None,
                document_type=None,
                status=STATUS_ERROR,
                error=err_msg,
            )

        # 1. Kiểm tra kích thước tối thiểu
        file_size = path.stat().st_size
        if file_size < self.min_file_size_bytes:
            err_msg = (
                f"Kích thước file {file_size} bytes nhỏ hơn ngưỡng tối thiểu "
                f"{self.min_file_size_bytes} bytes."
            )
            logger.warning(err_msg)
            return ProcessingResult(
                file_path=str(path),
                sha256=None,
                subject=None,
                document_type=None,
                status=STATUS_ERROR,
                error=err_msg,
            )

        # 2. Phân loại Môn học & Loại tài liệu
        try:
            classification = self.classifier.classify(path)
            subject = classification.subject
            document_type = classification.document_type
            logger.info("Subject: %s", subject)
            logger.info("Type: %s", document_type)
        except ClassifierError as exc:
            err_msg = f"Lỗi phân loại thư mục: {exc}"
            logger.error(err_msg)
            return ProcessingResult(
                file_path=str(path),
                sha256=None,
                subject=None,
                document_type=None,
                status=STATUS_ERROR,
                error=err_msg,
            )

        # 3. Tính hash SHA-256
        try:
            file_sha256 = calculate_sha256(path)
            logger.info("SHA256: %s", file_sha256)
        except Exception as exc:
            err_msg = f"Lỗi khi tính SHA-256 cho file '{path}': {exc}"
            logger.error(err_msg)
            return ProcessingResult(
                file_path=str(path),
                sha256=None,
                subject=subject,
                document_type=document_type,
                status=STATUS_ERROR,
                error=err_msg,
            )

        # 4. Kiểm tra trùng lặp trong SQLite
        existing = self.database.find_by_sha256(file_sha256)
        if existing and existing.get("status") == STATUS_UPLOADED:
            logger.info("Duplicate detected by SHA256")
            logger.info("Skip upload (Đã tồn tại trong database với Drive ID: %s)", existing.get("drive_file_id"))
            # Ghi nhận bản ghi DUPLICATE trong SQLite để theo dõi lịch sử
            self.database.insert_record(
                sha256=file_sha256,
                path=str(path),
                subject=subject,
                document_type=document_type,
                status=STATUS_DUPLICATE,
                drive_file_id=existing.get("drive_file_id"),
            )
            return ProcessingResult(
                file_path=str(path),
                sha256=file_sha256,
                subject=subject,
                document_type=document_type,
                status=STATUS_DUPLICATE,
                drive_file_id=existing.get("drive_file_id"),
            )

        # 5. Trích xuất văn bản (Extract text)
        extracted_text_len = 0
        if self.extract_content:
            try:
                extracted = extract_text(path)
                extracted_text_len = len(extracted)
                logger.info("Trích xuất nội dung thành công (%d ký tự).", extracted_text_len)
            except ExtractionError as exc:
                err_msg = f"Lỗi trích xuất nội dung: {exc}"
                logger.error(err_msg)
                rec_id = self.database.insert_record(
                    sha256=file_sha256,
                    path=str(path),
                    subject=subject,
                    document_type=document_type,
                    status=STATUS_ERROR,
                    error=err_msg,
                )
                return ProcessingResult(
                    file_path=str(path),
                    sha256=file_sha256,
                    subject=subject,
                    document_type=document_type,
                    status=STATUS_ERROR,
                    error=err_msg,
                )

        # 6. Tạo bản ghi PENDING trong SQLite
        record_id = self.database.insert_record(
            sha256=file_sha256,
            path=str(path),
            subject=subject,
            document_type=document_type,
            status=STATUS_PENDING,
        )

        # 7. Upload lên Google Drive
        self.database.update_status(record_id, status=STATUS_PROCESSING)

        if not self.drive_manager:
            msg = "Drive manager chưa được cấu hình. File chỉ lưu tại SQLite."
            logger.warning(msg)
            self.database.update_status(record_id, status=STATUS_ERROR, error=msg)
            return ProcessingResult(
                file_path=str(path),
                sha256=file_sha256,
                subject=subject,
                document_type=document_type,
                status=STATUS_ERROR,
                error=msg,
                extracted_text_len=extracted_text_len,
            )

        try:
            logger.info("Uploading to Google Drive...")
            target_folder_id = self.drive_manager.resolve_folder_hierarchy(
                subject=subject,
                document_type=document_type,
            )
            drive_file_id = self.drive_manager.upload_file(
                file_path=path,
                parent_folder_id=target_folder_id,
            )
            logger.info("Upload successful")
            logger.info("Drive file id: %s", drive_file_id)
            logger.info("Completed")

            self.database.update_status(
                record_id=record_id,
                status=STATUS_UPLOADED,
                drive_file_id=drive_file_id,
            )
            return ProcessingResult(
                file_path=str(path),
                sha256=file_sha256,
                subject=subject,
                document_type=document_type,
                status=STATUS_UPLOADED,
                drive_file_id=drive_file_id,
                extracted_text_len=extracted_text_len,
            )
        except CredentialsNotFoundError as exc:
            err_msg = f"[WAITING] Google OAuth credentials chưa có: {exc}"
            logger.error(err_msg)
            self.database.update_status(record_id, status=STATUS_ERROR, error=str(exc))
            return ProcessingResult(
                file_path=str(path),
                sha256=file_sha256,
                subject=subject,
                document_type=document_type,
                status=STATUS_ERROR,
                error=str(exc),
                extracted_text_len=extracted_text_len,
            )
        except (DriveError, Exception) as exc:
            err_msg = f"Lỗi upload Google Drive: {exc}"
            logger.error(err_msg)
            self.database.update_status(record_id, status=STATUS_ERROR, error=err_msg)
            return ProcessingResult(
                file_path=str(path),
                sha256=file_sha256,
                subject=subject,
                document_type=document_type,
                status=STATUS_ERROR,
                error=err_msg,
                extracted_text_len=extracted_text_len,
            )
