# local_agent/drive_sync.py — Google Drive task handler (<200 lines)
# Nhận tasks từ drive_task_queue và thực hiện: upload, move_to_archive, hard_delete

import logging
import mimetypes
from pathlib import Path
from typing import Any

# googleapiclient / google-auth được import LAZY trong từng hàm:
# runner GitHub Actions không cài 2 gói này — nó CHỈ cần download_file (tier requests).

from .config_loader import get
from .cascade_delete import hard_delete_file, move_to_recycle_bin

logger = logging.getLogger(__name__)

# Google Drive API scopes (khớp với token.json và src/drive.py)
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_FILE = Path(__file__).parent.parent / "token.json"
CREDS_FILE = Path(__file__).parent.parent / "credentials.json"

# Tên thư mục archive trên Drive
ARCHIVE_FOLDER_NAME = "_Archive_Trash_90Days"


def _get_drive_service() -> Any:
    """
    Xây dựng Google Drive API service từ token đã lưu.
    Tự động refresh token nếu hết hạn và cập nhật lại vào token.json.
    Raises RuntimeError nếu token không tồn tại hoặc không hợp lệ.
    """
    from googleapiclient.discovery import build  # type: ignore (lazy — cloud không cài)
    from google.oauth2.credentials import Credentials  # type: ignore

    if not TOKEN_FILE.exists():
        raise RuntimeError(f"Drive token không tìm thấy: {TOKEN_FILE}. Chạy lại xác thực OAuth.")

    from google.auth.transport.requests import Request
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            logger.info("Đang refresh Google Drive access token...")
            try:
                creds.refresh(Request())
                TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
                logger.info("Đã cập nhật token.json sau khi refresh thành công.")
            except Exception as e:
                raise RuntimeError(f"Lỗi refresh Google Drive token: {e}. Vui lòng đăng nhập lại.") from e
        else:
            raise RuntimeError("Drive token không hợp lệ và không có refresh_token.")

    return build("drive", "v3", credentials=creds, cache_discovery=False)


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


def ensure_folder_path(service: Any, folder_path: str, root_name: str | None = None) -> str:
    """Tạo folder lồng nhau trên Drive theo folder_path (vd 'a/b/c'). Trả về folder ID cuối."""
    parent_id: str | None = None
    if root_name:
        parent_id = _find_or_create_folder(service, root_name)
    for part in [p for p in (folder_path or "").replace("\\", "/").split("/") if p]:
        parent_id = _find_or_create_folder(service, part, parent_id)
    return parent_id or ""


def upload_file(local_path: str | Path, folder_path: str = "", subject: str = "") -> dict:
    """Upload file local lên Drive vào folder_path (tạo folder lồng nhau nếu thiếu).

    Returns: {drive_file_id, name, size_bytes}
    """
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"File local không tồn tại: {path}")
    service = _get_drive_service()
    drive_root = get("google_drive_root_folder_id", "") or get("drive_root_folder", "")
    full_folder = f"{subject}/{folder_path}" if subject and folder_path else (subject or folder_path)
    parent_id = ensure_folder_path(service, full_folder, drive_root or None) or None

    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    meta: dict[str, Any] = {"name": path.name}
    if parent_id:
        meta["parents"] = [parent_id]
    from googleapiclient.http import MediaFileUpload  # type: ignore (lazy — cloud không cài)
    media = MediaFileUpload(str(path), mimetype=mime, resumable=True)
    created = service.files().create(body=meta, media_body=media, fields="id, name, size").execute()
    drive_file_id = created["id"]
    logger.info("Đã upload Drive: %s -> %s (id=%s)", path.name, full_folder or "root", drive_file_id)

    # BẮT BUỘC gọi API drive.permissions.create gán quyền type='anyone', role='reader'
    web_view_link = ""
    try:
        service.permissions().create(
            fileId=drive_file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()
        # Chỉ lấy và trả về link webViewLink khi đã cấp quyền thành công
        info = service.files().get(fileId=drive_file_id, fields="id, webViewLink").execute()
        web_view_link = info.get("webViewLink", "")
        logger.info("Đã cấp quyền public reader thành công cho file %s (webViewLink=%s)", drive_file_id, web_view_link)
    except Exception as e:
        logger.warning("Lỗi khi cấp quyền public reader cho file %s: %s", drive_file_id, e)

    return {
        "drive_file_id": drive_file_id,
        "name": created.get("name", path.name),
        "size_bytes": int(created.get("size") or path.stat().st_size),
        "webViewLink": web_view_link,
        "web_view_link": web_view_link,
    }


def download_file(drive_file_id: str, dest_path: str | Path) -> Path:
    """Tải file từ Drive về dest_path với cơ chế đa tầng (Public Reader Stream + Authenticated API Fallback).

    Đảm bảo:
    1. Tải bằng HTTP stream trực tiếp qua Google Drive export URL (không bị hạn chế bởi drive.file scope).
    2. Fallback sang Google Drive API service nếu có token hợp lệ.
    3. Ghi vào file tạm (.part) trước, chỉ ghi nhận dest khi tải thành công (>0 byte), không để lại file rác 0-byte nếu lỗi.
    """
    import requests
    import re
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_part = dest.with_suffix(dest.suffix + ".download.part")

    # Tầng 1: Tải trực tiếp qua Google Drive Export/Download URL (file đã được gán Public Reader)
    try:
        session = requests.Session()
        download_url = f"https://drive.google.com/uc?export=download&id={drive_file_id}"
        resp = session.get(download_url, stream=True, timeout=60)

        # Xử lý Google Drive Virus Scan confirmation warning cho file lớn > 25MB
        if resp.status_code == 200 and "confirm=" in resp.text and "drive.google.com" in resp.url:
            match = re.search(r"confirm=([0-9A-Za-z_]+)", resp.text)
            if match:
                confirm_token = match.group(1)
                confirm_url = f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={drive_file_id}"
                resp = session.get(confirm_url, stream=True, timeout=60)

        if resp.status_code == 200:
            with open(temp_part, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)
            if temp_part.exists() and temp_part.stat().st_size > 0:
                if dest.exists():
                    dest.unlink()
                temp_part.replace(dest)
                logger.info("Đã tải Drive file thành công qua Direct Stream: %s -> %s (%d bytes)",
                            drive_file_id, dest, dest.stat().st_size)
                return dest
    except Exception as e:
        logger.debug("Direct stream download từ Drive thất bại, thử fallback qua API: %s", e)
        if temp_part.exists():
            try:
                temp_part.unlink()
            except Exception:
                pass

    # Tầng 2: Fallback sang Google Drive API Service
    try:
        from googleapiclient.http import MediaIoBaseDownload  # type: ignore
        service = _get_drive_service()
        request = service.files().get_media(fileId=drive_file_id)
        with open(temp_part, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        if temp_part.exists() and temp_part.stat().st_size > 0:
            if dest.exists():
                dest.unlink()
            temp_part.replace(dest)
            logger.info("Đã tải Drive file qua API: %s -> %s (%d bytes)",
                        drive_file_id, dest, dest.stat().st_size)
            return dest
        else:
            raise RuntimeError(f"Tải file từ Drive rỗng hoặc 0 bytes: {drive_file_id}")
    except Exception as e:
        if temp_part.exists():
            try:
                temp_part.unlink()
            except Exception:
                pass
        logger.error("Tất cả các phương thức tải file %s đều thất bại: %s", drive_file_id, e)
        raise RuntimeError(f"Không thể tải file {drive_file_id} từ Drive: {e}") from e


def handle_soft_delete_local(task: dict) -> None:
    """Bước 3 Cascade Delete: gửi file local vào Recycle Bin (fallback archive).

    Task format: {action: "soft_delete_local", file_id: "...", local_path: "..."}
    """
    local_path = task.get("local_path", "")
    if not local_path:
        logger.warning("soft_delete_local task thiếu local_path — bỏ qua")
        return
    result = move_to_recycle_bin(local_path)
    if not result.get("success"):
        raise RuntimeError(f"soft_delete_local thất bại: {result.get('error', 'unknown')}")
    logger.info("soft_delete_local OK (%s): %s", result.get("method"), local_path)


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
        "soft_delete_local": handle_soft_delete_local,
    }
    handler = handlers.get(action)
    if handler is None:
        raise ValueError(f"Không có Drive handler cho action: {action}")
    handler(task)
