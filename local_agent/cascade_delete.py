# local_agent/cascade_delete.py — Windows Recycle Bin + Archive fallback (<150 lines)
# Xử lý việc dời file về Recycle Bin hoặc _Archive_Trash_90Days/

import logging
import shutil
from pathlib import Path
from datetime import datetime

from .config_loader import get

logger = logging.getLogger(__name__)


def _safe_move_to_archive(source_path: Path, archive_base: Path) -> Path:
    """
    Dời file vào _Archive_Trash_90Days/ với timestamp trong tên để tránh xung đột.
    
    Args:
        source_path: Đường dẫn file nguồn.
        archive_base: Thư mục _Archive_Trash_90Days/.
    
    Returns:
        Đường dẫn file sau khi dời.
    """
    archive_base.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = source_path.stem
    suffix = source_path.suffix
    dest = archive_base / f"{stem}__{timestamp}{suffix}"

    # Tránh overwrite nếu tên trùng
    counter = 1
    while dest.exists():
        dest = archive_base / f"{stem}__{timestamp}_{counter}{suffix}"
        counter += 1

    shutil.move(str(source_path), str(dest))
    logger.info("Đã dời file sang archive: %s → %s", source_path.name, dest)
    return dest


def move_to_recycle_bin(file_path: str | Path) -> dict:
    """
    Dời file vào Recycle Bin Windows.
    Fallback: dời vào _Archive_Trash_90Days/ nếu send2trash không khả dụng.
    
    Args:
        file_path: Đường dẫn file cần xóa.
    
    Returns:
        {success: bool, method: "recycle_bin" | "archive", dest?: str, error?: str}
    """
    path = Path(file_path)

    if not path.exists():
        logger.warning("File không tồn tại, bỏ qua: %s", path)
        return {"success": True, "method": "skipped", "reason": "file_not_found"}

    # Thử dùng send2trash (Windows Recycle Bin)
    try:
        import send2trash  # type: ignore
        send2trash.send2trash(str(path.resolve()))
        logger.info("Đã gửi vào Recycle Bin: %s", path.name)
        return {"success": True, "method": "recycle_bin"}
    except ImportError:
        logger.warning("send2trash không cài đặt, dùng fallback archive")
    except Exception as e:
        logger.warning("send2trash thất bại: %s, dùng fallback archive", e)

    # Fallback: dời vào _Archive_Trash_90Days/
    try:
        archive_folder_name = get("drive_archive_folder", "_Archive_Trash_90Days")
        # Tìm thư mục môn học chứa file này (leo lên 1-2 cấp)
        parent = path.parent
        archive_base = parent / archive_folder_name

        # Nếu file đang trong thư mục con, archive cũng nằm cùng cấp với thư mục con
        dest = _safe_move_to_archive(path, archive_base)
        return {"success": True, "method": "archive", "dest": str(dest)}
    except Exception as e:
        logger.error("Không thể dời file sang archive: %s — %s", path, e)
        return {"success": False, "method": "failed", "error": str(e)}


def resolve_local_path(subject: str, folder_path: str, filename: str) -> Path:
    """Suy ra đường dẫn local tuyệt đối: <local_base_path>/<subject>/<folder_path>/<filename>.

    folder_path có thể rỗng hoặc lồng nhau (vd '03_Tai_Lieu_Tham_Khao/01_Bai_Bao_Khoa_Hoc').
    """
    base = Path(get("local_base_path", "."))
    parts = [p for p in (folder_path or "").replace("\\", "/").split("/") if p]
    return base.joinpath(subject, *parts, filename) if subject else base.joinpath(*parts, filename)


def hard_delete_file(file_path: str | Path) -> dict:
    """
    Xóa file vĩnh viễn (sau 90 ngày, được cron cấp phép).
    
    Args:
        file_path: Đường dẫn file cần xóa vĩnh viễn.
    
    Returns:
        {success: bool, error?: str}
    """
    path = Path(file_path)

    if not path.exists():
        logger.warning("Hard delete: file không tồn tại: %s", path)
        return {"success": True, "reason": "already_deleted"}

    try:
        path.unlink()
        logger.info("Đã xóa vĩnh viễn: %s", path.name)
        return {"success": True}
    except PermissionError as e:
        logger.error("Không có quyền xóa file: %s — %s", path, e)
        return {"success": False, "error": f"PermissionError: {e}"}
    except Exception as e:
        logger.error("Hard delete thất bại: %s — %s", path, e)
        return {"success": False, "error": str(e)}
