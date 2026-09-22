# local_agent/drive_sync.py — Google Drive task handler (<200 lines)
# Nhận tasks từ drive_task_queue và thực hiện: upload, move_to_archive, hard_delete

import logging
import mimetypes
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build  # type: ignore
from googleapiclient.http import MediaFileUpload  # type: ignore
from google.oauth2.credentials import Credentials  # type: ignore

from .config_loader import get
from .cascade_delete import hard_delete_file

logger = logging.getLogger(__name__)

# Google Drive API scopes
SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_FILE = Path(__file__).parent.parent / "token.json"
CREDS_FILE = Path(__file__).parent.parent / "credentials.json"

# Tên thư mục archive trên Drive
ARCHIVE_FOLDER_NAME = "_Archive_Trash_90Days"


def _get_drive_service() -> Any:
    """
    Xây dựng Google Drive API service từ token đã lưu.
    Raises RuntimeError nếu token không tồn tại hoặc không hợp lệ.
    """
    if not TOKEN_FILE.exists():
        raise RuntimeError(f"Drive token không tìm thấy: {TOKEN_FILE}. Chạy lại xác thực OAuth.")
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    return build("drive", "v3", credentials=creds)


def _find_or_create_folder(service: Any, folder_name: str, parent_id: str | None = None) -> str:
    """
    Tìm hoặc tạo folder trên Drive theo tên. Trả về folder ID.
    """
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    # Tạo mới
    meta: dict[str, Any] = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        meta["parents"] = [parent_id]

    folder = service.files().create(body=meta, fields="id").execute()
    logger.info("Đã tạo Drive folder: %s (id=%s)", folder_name, folder["id"])
    return folder["id"]


def handle_move_to_archive(task: dict) -> None:
    """
    Bước 2 Cascade Delete: Dời file Drive sang _Archive_Trash_90Days/ folder.
    
    Task format: {action: "move_to_archive", drive_file_id: "...", uid: "..."}
    """
    drive_file_id = task.get("drive_file_id", "")
    if not drive_file_id:
        logger.warning("move_to_archive task thiếu drive_file_id — bỏ qua")
        return

    try:
        service = _get_drive_service()
        archive_folder_id = _find_or_create_folder(service, ARCHIVE_FOLDER_NAME)

        # Lấy parents hiện tại để remove
        file_info = service.files().get(fileId=drive_file_id, fields="parents, name").execute()
        parents = file_info.get("parents", [])

        # Dời: add parent mới (archive), remove parents cũ
        service.files().update(
            fileId=drive_file_id,
            addParents=archive_folder_id,
            removeParents=",".join(parents) if parents else None,
            fields="id, parents",
        ).execute()

        logger.info("Đã dời file Drive sang archive: %s", file_info.get("name", drive_file_id))
    except Exception as e:
        raise RuntimeError(f"Drive move_to_archive thất bại: {e}") from e


def handle_hard_delete_drive(task: dict) -> None:
    """
    Bước 4 Cascade Delete (sau 90 ngày): Xóa file Drive vĩnh viễn.
    
    Task format: {action: "hard_delete", drive_file_id: "...", uid: "..."}
    """
    drive_file_id = task.get("drive_file_id", "")
    if not drive_file_id:
        logger.warning("hard_delete task thiếu drive_file_id — bỏ qua")
        return

    try:
        service = _get_drive_service()
        service.files().delete(fileId=drive_file_id).execute()
        logger.info("Đã xóa vĩnh viễn Drive file: %s", drive_file_id)

        # Xóa cả local cache nếu có
        local_path = task.get("local_path", "")
        if local_path:
            result = hard_delete_file(local_path)
            if not result["success"]:
                logger.warning("Local hard delete thất bại: %s", result.get("error", ""))
    except Exception as e:
        raise RuntimeError(f"Drive hard_delete thất bại: {e}") from e


def handle_drive_task(task: dict) -> None:
    """
    Dispatcher: Phân loại và gọi đúng handler theo action.
    Được đăng ký với FirestorePoller cho queue 'drive_task_queue'.
    """
    action = task.get("action", "")
    handlers = {
        "move_to_archive": handle_move_to_archive,
        "hard_delete": handle_hard_delete_drive,
    }
    handler = handlers.get(action)
    if handler is None:
        raise ValueError(f"Không có Drive handler cho action: {action}")
    handler(task)
