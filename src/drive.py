"""Module tích hợp Google Drive API v3 chính thức.

Chịu trách nhiệm:
- OAuth Desktop App (credentials.json -> token.json)
- Tìm hoặc tạo folder trên Drive (chống tạo trùng, cache folder ID)
- Upload file với cơ chế Retry 3 lần
"""

import logging
import mimetypes
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ThsAutoOrganizer.drive")

# Scopes yêu cầu để tạo folder và upload tài liệu học tập
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


class DriveError(Exception):
    """Lỗi chung của module Google Drive."""
    pass


class CredentialsNotFoundError(DriveError):
    """Chưa tìm thấy file credentials.json từ Google Cloud Console."""
    pass


class DriveManager:
    """Quản lý kết nối và tác vụ trên Google Drive."""

    def __init__(
        self,
        credentials_file: Path | str = "credentials.json",
        token_file: Path | str = "token.json",
        root_folder_id: Optional[str] = None,
        credentials: Optional[Any] = None,
    ) -> None:
        self.credentials_file = Path(credentials_file).resolve()
        self.token_file = Path(token_file).resolve()
        self.root_folder_id = root_folder_id.strip() if root_folder_id else None
        self._credentials = credentials
        self._service: Optional[Any] = None
        # Cache bộ nhớ: (folder_name, parent_id) -> folder_id
        self._folder_cache: Dict[Tuple[str, Optional[str]], str] = {}

    @classmethod
    def from_credentials(cls, credentials: Any, root_folder_id: Optional[str] = None) -> "DriveManager":
        """Khởi tạo DriveManager trực tiếp từ đối tượng Google Credentials của user."""
        manager = cls(root_folder_id=root_folder_id, credentials=credentials)
        return manager

    @classmethod
    def from_token_dict(
        cls,
        token_info: Dict[str, Any],
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        root_folder_id: Optional[str] = None,
        credentials_file: Optional[Path | str] = None,
    ) -> "DriveManager":
        """Khởi tạo DriveManager từ token dictionary lưu trong database của user."""
        if (not client_id or not client_secret) and credentials_file:
            cf = Path(credentials_file)
            if cf.is_file():
                try:
                    import json
                    with open(cf, "r", encoding="utf-8") as f:
                        cdata = json.load(f)
                    cinfo = cdata.get("installed", {}) or cdata.get("web", {})
                    client_id = client_id or cinfo.get("client_id")
                    client_secret = client_secret or cinfo.get("client_secret")
                except Exception:
                    pass

        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=token_info.get("access_token"),
            refresh_token=token_info.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        return cls.from_credentials(creds, root_folder_id=root_folder_id)

    def is_configured(self) -> bool:
        """Kiểm tra xem credentials.json, token.json hoặc user credentials đã sẵn sàng chưa."""
        if self._credentials is not None:
            return True
        return self.credentials_file.is_file() or self.token_file.is_file()

    def get_service(self) -> Any:
        """Lấy hoặc khởi tạo Drive API service thông qua OAuth 2.0."""
        if self._service is not None:
            return self._service

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        if self._credentials is not None:
            if self._credentials.expired and self._credentials.refresh_token:
                try:
                    self._credentials.refresh(Request())
                except Exception as exc:
                    logger.warning("Lỗi khi refresh token của user: %s", exc)
            self._service = build("drive", "v3", credentials=self._credentials, cache_discovery=False)
            return self._service

        creds = None

        if self.token_file.is_file():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
            except Exception as exc:
                logger.warning("Không thể đọc token.json: %s. Sẽ thử tạo mới.", exc)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    logger.info("Đang refresh token Google Drive OAuth...")
                    creds.refresh(Request())
                except Exception as exc:
                    logger.warning("Lỗi refresh token: %s. Cần xác thực lại.", exc)
                    creds = None

            if not creds:
                if not self.credentials_file.is_file():
                    raise CredentialsNotFoundError(
                        f"Không tìm thấy '{self.credentials_file}'. "
                        "Vui lòng tải credentials.json (OAuth Client - Desktop App) "
                        "từ Google Cloud Console và đặt vào thư mục gốc của project."
                    )

                logger.info("Bắt đầu quy trình xác thực OAuth 2.0 qua trình duyệt...")
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_file), SCOPES)
                creds = flow.run_local_server(port=0)

            # Lưu token cho các lần chạy tiếp theo
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, "w", encoding="utf-8") as token:
                token.write(creds.to_json())
            logger.info("Đã lưu token Google Drive vào '%s'", self.token_file)

        self._service = build("drive", "v3", credentials=creds)
        logger.info("Khởi tạo Google Drive API v3 service thành công.")
        return self._service

    def _execute_with_retry(self, request: Any, max_retries: int = 3, initial_delay: float = 2.0) -> Any:
        """Thực thi một Google API request kèm cơ chế retry có backoff."""
        from googleapiclient.errors import HttpError

        delay = initial_delay
        last_exception = None

        for attempt in range(1, max_retries + 1):
            try:
                return request.execute()
            except (HttpError, OSError, TimeoutError) as exc:
                last_exception = exc
                if attempt == max_retries:
                    logger.error("Drive API thất bại sau %d lần thử: %s", max_retries, exc)
                    raise DriveError(f"Drive API call thất bại sau {max_retries} lần thử: {exc}") from exc
                logger.warning(
                    "Drive API gặp lỗi ở lần thử %d/%d (%s). Thử lại sau %.1fs...",
                    attempt,
                    max_retries,
                    exc,
                    delay,
                )
                time.sleep(delay)
                delay *= 2.0

        raise DriveError(f"Drive API call thất bại: {last_exception}")

    def find_or_create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> str:
        """Tìm folder theo tên và parent_id. Nếu chưa có -> tạo mới.

        Tận dụng cache để không query nhiều lần.
        """
        cache_key = (folder_name, parent_id)
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        service = self.get_service()

        # Xây dựng câu truy vấn an toàn
        safe_name = folder_name.replace("'", "\\'")
        query_parts = [
            f"name = '{safe_name}'",
            f"mimeType = '{FOLDER_MIME_TYPE}'",
            "trashed = false",
        ]
        if parent_id:
            query_parts.append(f"'{parent_id}' in parents")
        else:
            query_parts.append("'root' in parents")

        query = " and ".join(query_parts)

        request = service.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name)",
            pageSize=5,
        )
        response = self._execute_with_retry(request)
        files = response.get("files", [])

        if files:
            folder_id = files[0]["id"]
            logger.debug("Tái sử dụng folder Drive: '%s' (id: %s)", folder_name, folder_id)
        else:
            # Tạo folder mới
            file_metadata = {
                "name": folder_name,
                "mimeType": FOLDER_MIME_TYPE,
            }
            if parent_id:
                file_metadata["parents"] = [parent_id]

            create_request = service.files().create(
                body=file_metadata,
                fields="id",
            )
            created_folder = self._execute_with_retry(create_request)
            folder_id = created_folder.get("id")
            logger.info("Đã tạo mới folder Drive: '%s' (id: %s)", folder_name, folder_id)

        self._folder_cache[cache_key] = folder_id
        return folder_id

    def resolve_folder_hierarchy(
        self,
        subject: str,
        document_type: str,
        root_name: str = "ThacSi_HTTT",
    ) -> str:
        """Tạo hoặc tìm cây thư mục chuẩn:

        root_folder (hoặc ThacSi_HTTT)
        └── <subject> (ví dụ: 'Triết học')
            └── <document_type> (ví dụ: 'Slide')

        Returns:
            ID của thư mục đích (document_type).
        """
        # 1. Xác định Root Folder ID
        if self.root_folder_id:
            effective_root_id = self.root_folder_id
        else:
            effective_root_id = self.find_or_create_folder(root_name, parent_id=None)

        # 2. Xác định Subject Folder ID
        subject_folder_id = self.find_or_create_folder(subject, parent_id=effective_root_id)

        # 3. Xác định Document Type Folder ID
        type_folder_id = self.find_or_create_folder(document_type, parent_id=subject_folder_id)

        return type_folder_id

    def upload_file(
        self,
        file_path: Path | str,
        parent_folder_id: str,
        custom_name: Optional[str] = None,
    ) -> str:
        """Upload file lên thư mục Google Drive chỉ định.

        Args:
            file_path: Đường dẫn file cục bộ.
            parent_folder_id: ID của thư mục cha trên Drive.
            custom_name: Tùy chọn đặt tên file trên Drive nếu khác tên gốc.

        Returns:
            drive_file_id của file sau khi upload thành công.
        """
        from googleapiclient.http import MediaFileUpload

        path = Path(file_path).resolve()
        if not path.is_file():
            raise DriveError(f"File cục bộ không tồn tại: '{path}'")

        service = self.get_service()
        file_name = custom_name or path.name

        mime_type, _ = mimetypes.guess_type(str(path))
        if not mime_type:
            mime_type = "application/octet-stream"

        file_metadata = {
            "name": file_name,
            "parents": [parent_folder_id],
        }

        media = MediaFileUpload(
            str(path),
            mimetype=mime_type,
            resumable=True,
        )

        request = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink",
        )

        logger.info("Đang upload '%s' lên Google Drive (folder id: %s)...", file_name, parent_folder_id)
        result = self._execute_with_retry(request, max_retries=3)
        drive_file_id = result.get("id")

        logger.info("Upload thành công '%s' (Drive ID: %s)", file_name, drive_file_id)
        return drive_file_id

    def download_file(self, drive_file_id: str, destination_path: Path | str) -> Path:
        """Tải một file từ Google Drive về máy tính."""
        from googleapiclient.http import MediaIoBaseDownload

        dest = Path(destination_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)

        service = self.get_service()
        request = service.files().get_media(fileId=drive_file_id)

        with open(dest, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug("Download %s: %d%%", dest.name, int(status.progress() * 100))

        logger.info("Đã tải thành công file từ Drive về máy: '%s'", dest)
        return dest

    def list_files_in_folder(self, folder_id: str) -> List[Dict[str, Any]]:
        """Lấy danh sách các file và subfolder trong một folder trên Drive."""
        service = self.get_service()
        query = f"'{folder_id}' in parents and trashed = false"
        request = service.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name, mimeType, size, md5Checksum, modifiedTime)",
            pageSize=100,
        )
        response = self._execute_with_retry(request)
        return response.get("files", [])

    def list_all_study_materials(self, root_name: str = "ThacSi_HTTT") -> List[Dict[str, Any]]:
        """Duyệt toàn bộ cây thư mục ThacSi_HTTT trên Google Drive để tìm tài liệu học tập.

        Cấu trúc:
        ThacSi_HTTT / <Tên môn> / <Tên loại> / <File>
        hoặc ThacSi_HTTT / <Tên môn> / <File>

        Returns:
            Danh sách dict gồm {file_id, name, subject, document_type, size}
        """
        root_id = self.root_folder_id or self.find_or_create_folder(root_name, parent_id=None)
        items_under_root = self.list_files_in_folder(root_id)

        materials: List[Dict[str, Any]] = []

        for item in items_under_root:
            if item.get("mimeType") == FOLDER_MIME_TYPE:
                subject_name = item["name"]
                subject_id = item["id"]
                sub_items = self.list_files_in_folder(subject_id)

                for sub in sub_items:
                    if sub.get("mimeType") == FOLDER_MIME_TYPE:
                        type_name = sub["name"]
                        type_id = sub["id"]
                        files_in_type = self.list_files_in_folder(type_id)
                        for f in files_in_type:
                            if f.get("mimeType") != FOLDER_MIME_TYPE:
                                materials.append({
                                    "file_id": f["id"],
                                    "name": f["name"],
                                    "subject": subject_name,
                                    "document_type": type_name,
                                    "size": int(f.get("size", 0)),
                                })
                    else:
                        materials.append({
                            "file_id": sub["id"],
                            "name": sub["name"],
                            "subject": subject_name,
                            "document_type": "Tài liệu tham khảo",
                            "size": int(sub.get("size", 0)),
                        })

        return materials
