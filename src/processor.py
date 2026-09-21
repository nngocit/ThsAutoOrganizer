"""Module điều phối quy trình xử lý tài liệu (Pipeline Orchestrator).

Luồng xử lý:
File -> Validate -> Classify -> Extract text -> SHA-256 -> SQLite Check -> Upload Drive -> Lưu SQLite
"""

from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from src.classifier import PathClassifier, ClassifierError
from src.database import (
    Database,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_UPLOADED,
    STATUS_SAVED_LOCAL,
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

    def _get_drive_manager_for_user(self, user_email: str) -> Optional[DriveManager]:
        """Lấy DriveManager phù hợp với tài khoản người dùng."""
        clean_email = (user_email or "").strip().lower()
        if clean_email in ["xuanngocit@gmail.com", "default@user"]:
            if self.drive_manager:
                if hasattr(self.drive_manager, "is_configured"):
                    if self.drive_manager.is_configured():
                        return self.drive_manager
                else:
                    return self.drive_manager
            return None

        # Kiểm tra xem user khác có access_token riêng trong database hay không
        if self.database:
            db_user = self.database.get_user_by_email(clean_email)
            if db_user and db_user.get("access_token"):
                try:
                    client_id = None
                    client_secret = None
                    cred_file = Path("credentials.json")
                    if cred_file.is_file():
                        import json
                        with open(cred_file, "r", encoding="utf-8") as f:
                            cdata = json.load(f)
                        cinfo = cdata.get("installed", {}) or cdata.get("web", {})
                        client_id = cinfo.get("client_id")
                        client_secret = cinfo.get("client_secret")

                    token_dict = {
                        "access_token": db_user["access_token"],
                        "refresh_token": db_user.get("refresh_token"),
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                    return DriveManager.from_token_dict(
                        token_info=token_dict,
                        client_id=client_id,
                        client_secret=client_secret,
                        root_folder_id=db_user.get("drive_root_folder_id") or "",
                    )
                except Exception as exc:
                    logger.warning("Không thể tạo DriveManager riêng cho %s: %s", user_email, exc)

        # Tuyệt đối không dùng chung Google Drive của xuanngocit cho tài khoản khác
        return None

    def _get_user_storage_folder(self, user_email: str) -> Path:
        """Trả về thư mục lưu trữ tương ứng với user."""
        clean_email = (user_email or "").strip().lower()
        root_path = Path(self.classifier.root_folder).resolve()
        if not clean_email or clean_email in ["xuanngocit@gmail.com", "default@user"]:
            return root_path

        if self.database:
            db_user = self.database.get_user_by_email(clean_email)
            if db_user and db_user.get("local_folder"):
                return Path(db_user["local_folder"]).resolve()

        safe_name = clean_email.replace("@", "_at_").replace(".", "_")
        user_dir = root_path.parent / "Users_Storage" / safe_name
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _infer_classification_from_filename(self, path: Path) -> Tuple[str, str]:
        """Tự động suy luận Môn học và Loại tài liệu thông minh khi file không nằm trong cấu trúc thư mục chuẩn."""
        fn_lower = path.name.lower()
        parent_name = path.parent.name.lower()
        combined = f"{parent_name} {fn_lower}"

        # 1. Nhận diện Môn học
        subject = "Tài liệu chung"
        if any(k in combined for k in ["triết", "triet", "mac", "lenin"]):
            subject = "Triết học"
        elif any(k in combined for k in ["toán", "toan", "dữ liệu", "du_lieu", "data"]):
            subject = "Toán khoa học dữ liệu"
        elif any(k in combined for k in ["cơ sở dữ liệu", "co_so_du_lieu", "csdl", "database", "sql"]):
            subject = "Cơ sở dữ liệu"
        elif any(k in combined for k in ["nghiên cứu", "nghien_cuu", "phương pháp nghiên cứu", "ppnc"]):
            subject = "Phương pháp nghiên cứu"
        elif any(k in combined for k in ["ghi chú", "ghi_chu", "note", "phuong_phap_ghi_chu"]):
            subject = "Phương pháp ghi chú"
        elif parent_name not in ["new folder", "thư mục mới", "downloads", "desktop", "", "users_storage"]:
            # Dùng tên thư mục nếu có ý nghĩa
            subject = path.parent.name

        # 2. Nhận diện Loại tài liệu
        doc_type = "Tài liệu tham khảo"
        ext = path.suffix.lower()
        if any(k in fn_lower for k in ["giao-trinh", "giao_trinh", "giaotrinh", "giáo trình", "textbook", "sach", "book"]):
            doc_type = "Giáo trình"
        elif any(k in fn_lower for k in ["ôn", "on ", "on_", "on-", "đề cương", "de cuong", "decuong", "đề thi", "thi", "exam"]):
            doc_type = "Ôn thi"
        elif ext in [".pptx", ".ppt"] or any(k in fn_lower for k in ["slide", "bài giảng", "bai giang", "baigiang", "lecture"]):
            doc_type = "Slide"
        elif ext in [".png", ".jpg", ".jpeg", ".webp"]:
            doc_type = "Tài liệu tham khảo"

        return subject, doc_type

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

    def process_file(self, file_path: Path | str, user_email: str = "default@user") -> ProcessingResult:
        """Thực thi toàn bộ pipeline cho một file gắn với tài khoản người dùng."""
        path = Path(file_path).resolve()
        logger.info("Detected: %s (User: %s)", path.name, user_email)

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
        user_root = self._get_user_storage_folder(user_email)
        subject = None
        document_type = None
        try:
            classification = self.classifier.classify(path, root_folder=user_root)
            subject = classification.subject
            document_type = classification.document_type
        except ClassifierError as exc:
            logger.info(
                "Thư mục file '%s' không theo cấu trúc chuẩn môn học (%s). Tự động phân loại thông minh theo tên file.",
                path.name,
                exc,
            )
            subject, document_type = self._infer_classification_from_filename(path)

        logger.info("Subject: %s", subject)
        logger.info("Type: %s", document_type)

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
        # 4a. Nếu chính file này (cùng đường dẫn) đã được xử lý và upload thành công trước đó:
        existing_path_rec = self.database.find_by_path(str(path), user_email=user_email)
        if existing_path_rec:
            if existing_path_rec.get("sha256") == file_sha256 and existing_path_rec.get("status") in [STATUS_UPLOADED, STATUS_SAVED_LOCAL]:
                logger.info("File '%s' đã tồn tại và đã xử lý từ trước (SHA256: %s). Skip upload.", path.name, file_sha256[:10])
                return ProcessingResult(
                    file_path=str(path),
                    sha256=file_sha256,
                    subject=subject,
                    document_type=document_type,
                    status=STATUS_DUPLICATE,
                    drive_file_id=existing_path_rec.get("drive_file_id"),
                )

        # 4b. Nếu file ở đường dẫn khác nhưng nội dung trùng SHA-256:
        existing_sha = self.database.find_by_sha256(file_sha256, user_email=user_email)
        if existing_sha and existing_sha.get("status") in [STATUS_UPLOADED, STATUS_SAVED_LOCAL]:
            logger.info("Duplicate detected by SHA256 (trùng nội dung với: %s)", existing_sha.get("path"))
            logger.info("Skip upload (Drive ID: %s)", existing_sha.get("drive_file_id"))
            
            # Chỉ ghi nhận 1 lần DUPLICATE cho đường dẫn này nếu chưa có
            if not existing_path_rec:
                self.database.insert_record(
                    sha256=file_sha256,
                    path=str(path),
                    subject=subject,
                    document_type=document_type,
                    status=STATUS_DUPLICATE,
                    drive_file_id=existing_sha.get("drive_file_id"),
                    user_email=user_email,
                )
            return ProcessingResult(
                file_path=str(path),
                sha256=file_sha256,
                subject=subject,
                document_type=document_type,
                status=STATUS_DUPLICATE,
                drive_file_id=existing_sha.get("drive_file_id"),
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
                    user_email=user_email,
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
            user_email=user_email,
        )

        # 7. Upload lên Google Drive (theo tài khoản người dùng tương ứng)
        self.database.update_status(record_id, status=STATUS_PROCESSING)

        user_dm = self._get_drive_manager_for_user(user_email)
        if not user_dm:
            msg = f"Tài khoản '{user_email}' chưa kết nối Google Drive riêng. File đã được lưu an toàn tại máy."
            logger.info(msg)
            self.database.update_status(record_id, status=STATUS_SAVED_LOCAL)
            return ProcessingResult(
                file_path=str(path),
                sha256=file_sha256,
                subject=subject,
                document_type=document_type,
                status=STATUS_SAVED_LOCAL,
                drive_file_id=None,
                extracted_text_len=extracted_text_len,
            )

        try:
            logger.info("Uploading to Google Drive cho user %s...", user_email)
            target_folder_id = user_dm.resolve_folder_hierarchy(
                subject=subject,
                document_type=document_type,
            )
            drive_file_id = user_dm.upload_file(
                file_path=path,
                parent_folder_id=target_folder_id,
            )
            logger.info("Upload successful (User: %s, Drive ID: %s)", user_email, drive_file_id)

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
