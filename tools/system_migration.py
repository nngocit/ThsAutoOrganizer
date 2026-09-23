#!/usr/bin/env python3
# tools/system_migration.py — System Maintenance: Migration & Reconciliation Tool
# Chạy độc lập:
#   1. LOCAL TO DRIVE MIGRATION (Đẩy dữ liệu cũ từ máy lên Google Drive & nạp NLM)
#   2. DRIVE TO LOCAL RECONCILIATION (Đồng bộ cấu trúc chuẩn từ Drive về máy)

import argparse
import hashlib
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Đảm bảo import được local_agent & src từ root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Thiết lập encoding UTF-8 cho Windows console nếu khả dụng
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from local_agent.config_loader import get, sync_remote_config
from local_agent.constants import (
    FOLDER_MAP,
    NO_LOOP_FOLDERS,
    SUPPORTED_EXTENSIONS,
    is_no_loop_path,
)
from local_agent.drive_sync import _get_drive_service, download_file
from local_agent import api_client

# Cấu hình logging chuyên nghiệp
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("migration_tool")

MIN_FILE_SIZE = 1000  # Bỏ qua file < 1KB theo đặc tả NO-LOOP


def _sha256(path: Path) -> str:
    """Tính mã băm SHA-256 của file local."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _split_rel_path(path: Path, base: Path) -> Tuple[str, str, str]:
    """Tách đường dẫn tương đối thành (subject, folder_path, filename).
    Ví dụ:
      base: H:/Mon_Hoc
      path: H:/Mon_Hoc/Triet Hoc/01_Giao_Trinh/sach.pdf
      -> subject='Triet Hoc', folder_path='01_Giao_Trinh', filename='sach.pdf'
    """
    rel = path.relative_to(base)
    parts = rel.parts
    if len(parts) == 1:
        return "Tài liệu chung", "", parts[0]
    subject = parts[0]
    folder_path = "/".join(parts[1:-1]) if len(parts) > 2 else ""
    filename = parts[-1]
    return subject, folder_path, filename


def _infer_document_type(folder_path: str) -> str:
    """Suy luận document_type từ folder_path."""
    norm = (folder_path or "").replace("\\", "/")
    for doc_type, folder in FOLDER_MAP.items():
        if folder in norm or doc_type in norm.lower():
            return doc_type
    if "giao_trinh" in norm.lower() or "giáo trình" in norm.lower():
        return "giao_trinh"
    if "slide" in norm.lower():
        return "slide"
    if "bai_bao" in norm.lower() or "bài báo" in norm.lower():
        return "bai_bao"
    if "on_thi" in norm.lower() or "ôn thi" in norm.lower():
        return "giao_trinh"
    return "giao_trinh"


def get_drive_root_folder_id(service: Any, configured_id: str = "") -> str:
    """Tìm hoặc xác định Drive Root ID. Nếu rỗng, tự động tìm kiếm thư mục 'ThacSi_HTTT' hoặc '02_Mon_Hoc'."""
    if configured_id:
        return configured_id

    # Tìm trong system_config từ Cloud
    remote_cfg = get("google_drive_root_folder_id", "")
    if remote_cfg:
        return remote_cfg

    # Tìm kiếm trên Drive các folder tiềm năng
    logger.info("Đang tự động tìm kiếm thư mục gốc học tập trên Google Drive...")
    candidates = ["ThacSi_HTTT", "02_Mon_Hoc", "Mon_Hoc"]
    for name in candidates:
        q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        try:
            res = service.files().list(q=q, fields="files(id, name)").execute()
            files = res.get("files", [])
            if files:
                found_id = files[0]["id"]
                logger.info("✓ Đã tìm thấy thư mục gốc '%s' trên Drive: ID = %s", name, found_id)
                return found_id
        except Exception as e:
            logger.warning("Lỗi tìm kiếm thư mục '%s': %s", name, e)

    return ""


def get_courses_map() -> Dict[str, Dict[str, Any]]:
    """Lấy danh sách các môn học để map folder -> course_id."""
    course_map: Dict[str, Dict[str, Any]] = {}
    try:
        data = api_client.list_courses()
        courses = data.get("courses", [])
        for c in courses:
            cid = c.get("id") or c.get("_id")
            cname = c.get("name") or c.get("folder_name") or ""
            if cid:
                course_map[cid] = c
                if cname:
                    course_map[cname.lower()] = c
                    course_map[cname] = c
                    # Format không dấu hoặc chuẩn hóa
                    c_clean = cname.replace(" ", "_").lower()
                    course_map[c_clean] = c
    except Exception as e:
        logger.debug("Không thể lấy danh sách courses từ API: %s", e)
    return course_map


def resolve_course_for_subject(subject: str, courses_map: Dict[str, Dict[str, Any]]) -> Tuple[str, str]:
    """Trả về (course_id, notebooklm_id) tương ứng cho subject."""
    if not subject or subject == "Tài liệu chung":
        return "", ""

    # Tra cứu trực tiếp
    if subject in courses_map:
        c = courses_map[subject]
        return c.get("id", ""), c.get("notebooklm_id") or c.get("notebook_id") or ""
    if subject.lower() in courses_map:
        c = courses_map[subject.lower()]
        return c.get("id", ""), c.get("notebooklm_id") or c.get("notebook_id") or ""

    sub_norm = subject.replace("_", " ").lower()
    for key, c in courses_map.items():
        if key.replace("_", " ").lower() == sub_norm:
            return c.get("id", ""), c.get("notebooklm_id") or c.get("notebook_id") or ""

    return "", ""


# =====================================================================
# MENU 1: LOCAL TO DRIVE MIGRATION
# =====================================================================

def migrate_local_to_drive(
    local_base_path: Path,
    drive_root_id: str,
    dry_run: bool = False,
) -> None:
    """Quét toàn bộ thư mục local_base_path, tạo cây thư mục trên Drive,
    upload các file chưa có, gán quyền Public Reader và đăng ký Firestore/NLM.
    """
    print("\n" + "=" * 70)
    print(">>> BẮT ĐẦU: LOCAL TO DRIVE MIGRATION (Đẩy dữ liệu cũ lên mây)")
    print(f"Thư mục nguồn Local : {local_base_path}")
    print(f"Thư mục đích Drive  : {drive_root_id or '[Root mặc định của Drive]'}")
    print(f"Chế độ Dry-Run      : {'BẬT (Không thay đổi dữ liệu)' if dry_run else 'TẮT (Thực thi thực tế)'}")
    print("=" * 70 + "\n")

    if not local_base_path.exists():
        logger.error("Thư mục local không tồn tại: %s", local_base_path)
        return

    service = _get_drive_service()
    courses_map = get_courses_map()

    # Cache folder ID trên Drive: relative_dir_str -> drive_folder_id
    folder_cache: Dict[str, str] = {"": drive_root_id}

    def get_or_create_drive_folder(rel_folder: str) -> str:
        """Đảm bảo cây thư mục rel_folder tồn tại trên Drive dưới drive_root_id."""
        rel_folder = rel_folder.replace("\\", "/").strip("/")
        if not rel_folder:
            return drive_root_id

        if rel_folder in folder_cache:
            return folder_cache[rel_folder]

        # Tạo từng cấp từ trên xuống dưới
        parts = rel_folder.split("/")
        current_path = ""
        parent_id = drive_root_id

        for part in parts:
            current_path = f"{current_path}/{part}" if current_path else part
            if current_path in folder_cache:
                parent_id = folder_cache[current_path]
                continue

            # Kiểm tra folder đã tồn tại trên Drive chưa
            escaped_name = part.replace("'", "\\'")
            q = f"name='{escaped_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_id:
                q += f" and '{parent_id}' in parents"

            res = service.files().list(q=q, fields="files(id, name)").execute()
            files = res.get("files", [])

            if files:
                folder_id = files[0]["id"]
            else:
                if dry_run:
                    logger.info("[DRY-RUN] Sẽ tạo folder trên Drive: '%s' (parent=%s)", part, parent_id)
                    folder_id = f"dry_run_{current_path}"
                else:
                    meta = {
                        "name": part,
                        "mimeType": "application/vnd.google-apps.folder",
                    }
                    if parent_id:
                        meta["parents"] = [parent_id]
                    created = service.files().create(body=meta, fields="id").execute()
                    folder_id = created["id"]
                    logger.info("📁 Đã tạo Drive folder: '%s' -> ID: %s", current_path, folder_id)

            folder_cache[current_path] = folder_id
            parent_id = folder_id

        return folder_cache[rel_folder]

    # Thu thập toàn bộ file hợp lệ
    logger.info("Đang quét toàn bộ cây thư mục Local...")
    all_files: List[Path] = []
    for root, dirs, files in os.walk(local_base_path):
        # Lọc bỏ các thư mục NO-LOOP trong os.walk
        dirs[:] = [d for d in dirs if d not in NO_LOOP_FOLDERS and not d.startswith(".")]
        for f in files:
            p = Path(root) / f
            # Lọc sơ bộ
            if f.startswith("~$") or f.endswith(".tmp") or f.startswith("."):
                continue
            if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                if p.stat().st_size < MIN_FILE_SIZE:
                    continue
            except OSError:
                continue
            if is_no_loop_path(str(p.relative_to(local_base_path))):
                continue
            all_files.append(p)

    logger.info("Tìm thấy %d file hợp lệ để kiểm tra đồng bộ.", len(all_files))

    stats = {
        "total": len(all_files),
        "already_synced": 0,
        "uploaded": 0,
        "registered": 0,
        "skipped_nlm": 0,
        "failed": 0,
    }

    from googleapiclient.http import MediaFileUpload
    import mimetypes

    for idx, file_path in enumerate(all_files, 1):
        rel_path = file_path.relative_to(local_base_path)
        subject, folder_path, filename = _split_rel_path(file_path, local_base_path)
        rel_folder = f"{subject}/{folder_path}".strip("/") if folder_path else subject

        prefix = f"[{idx}/{len(all_files)}]"

        try:
            # 1. Tính mã băm SHA-256
            digest = _sha256(file_path)

            # 2. Đảm bảo thư mục cha trên Drive tồn tại
            target_drive_folder_id = get_or_create_drive_folder(rel_folder)

            # 3. Kiểm tra xem file đã có trên Drive chưa
            drive_file_id = ""
            web_view_link = ""

            escaped_fn = filename.replace("'", "\\'")
            q = f"name='{escaped_fn}' and trashed=false and mimeType!='application/vnd.google-apps.folder'"
            if target_drive_folder_id and not target_drive_folder_id.startswith("dry_run"):
                q += f" and '{target_drive_folder_id}' in parents"

            drive_matches = service.files().list(q=q, fields="files(id, name, webViewLink, size)").execute().get("files", [])

            if drive_matches:
                drive_file_id = drive_matches[0]["id"]
                web_view_link = drive_matches[0].get("webViewLink", "")
                stats["already_synced"] += 1
                logger.info("%s ⏩ Đã có trên Drive: %s (id=%s)", prefix, rel_path, drive_file_id)
            else:
                # Cần upload
                if dry_run:
                    logger.info("%s [DRY-RUN] Sẽ upload file: %s -> Drive folder '%s'", prefix, filename, rel_folder)
                    stats["uploaded"] += 1
                    continue

                mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                meta: Dict[str, Any] = {"name": filename}
                if target_drive_folder_id:
                    meta["parents"] = [target_drive_folder_id]

                media = MediaFileUpload(str(file_path), mimetype=mime, resumable=True)
                created = service.files().create(body=meta, media_body=media, fields="id, name, size").execute()
                drive_file_id = created["id"]
                stats["uploaded"] += 1
                logger.info("%s ☁️ Đã upload Drive thành công: %s (id=%s)", prefix, filename, drive_file_id)

                # BẮT BUỘC gán quyền Public Reader
                try:
                    service.permissions().create(
                        fileId=drive_file_id,
                        body={"type": "anyone", "role": "reader"},
                    ).execute()
                    info = service.files().get(fileId=drive_file_id, fields="id, webViewLink").execute()
                    web_view_link = info.get("webViewLink", "")
                    logger.info("%s 🔓 Đã cấp quyền Public Reader thành công cho %s", prefix, filename)
                except Exception as perm_err:
                    logger.warning("%s Lỗi cấp quyền Public Reader: %s", prefix, perm_err)

            # 4. Đăng ký file vào Firestore & bắn task NLM
            if not dry_run and drive_file_id:
                course_id, notebooklm_id = resolve_course_for_subject(subject, courses_map)
                doc_type = _infer_document_type(folder_path)

                reg_res = api_client.register_file(
                    filename=filename,
                    subject=subject,
                    document_type=doc_type,
                    folder_path=folder_path,
                    sha256=digest,
                    drive_file_id=drive_file_id,
                    drive_view_link=web_view_link,
                    size_bytes=file_path.stat().st_size,
                    local_path=str(file_path.resolve()),
                    course_id=course_id,
                )
                stats["registered"] += 1

                if subject == "Tài liệu chung" or not course_id:
                    stats["skipped_nlm"] += 1
                    logger.info("%s 📝 Đã đăng ký Firestore (Bỏ qua nạp NLM: file không thuộc môn học)", prefix)
                else:
                    logger.info("%s 🚀 Đã đăng ký Firestore & hàng đợi NLM thành công (Course: %s)", prefix, subject)

        except Exception as e:
            stats["failed"] += 1
            logger.error("%s ❌ Lỗi xử lý %s: %s", prefix, rel_path, e)

    print("\n" + "=" * 70)
    print(">>> BÁO CÁO TỔNG KẾT LOCAL TO DRIVE MIGRATION:")
    print(f" - Tổng số file được duyệt     : {stats['total']}")
    print(f" - File đã có sẵn trên Drive   : {stats['already_synced']}")
    print(f" - File đã upload mới lên Drive: {stats['uploaded']}")
    print(f" - File đã đăng ký Firestore   : {stats['registered']}")
    print(f" - Bỏ qua nạp NLM (Chung)      : {stats['skipped_nlm']}")
    print(f" - Lỗi trong quá trình xử lý   : {stats['failed']}")
    print("=" * 70 + "\n")


# =====================================================================
# MENU 2: DRIVE TO LOCAL RECONCILIATION
# =====================================================================

def reconcile_drive_to_local(
    local_base_path: Path,
    drive_root_id: str,
    dry_run: bool = False,
) -> None:
    """Lấy Google Drive làm Single Source of Truth, quét toàn bộ cây thư mục
    dưới drive_root_id, tạo cấu trúc tương ứng xuống local_base_path và tải
    các file còn thiếu về máy (tránh tải lại file đã có khớp kích thước).
    """
    print("\n" + "=" * 70)
    print(">>> BẮT ĐẦU: DRIVE TO LOCAL RECONCILIATION (Đồng bộ mây về máy)")
    print(f"Thư mục gốc Drive   : {drive_root_id or '[Root mặc định của Drive]'}")
    print(f"Thư mục đích Local  : {local_base_path}")
    print(f"Chế độ Dry-Run      : {'BẬT (Không tải file thật)' if dry_run else 'TẮT (Thực thi thực tế)'}")
    print("=" * 70 + "\n")

    if not dry_run:
        local_base_path.mkdir(parents=True, exist_ok=True)

    service = _get_drive_service()

    stats = {
        "folders_created": 0,
        "files_checked": 0,
        "files_downloaded": 0,
        "files_already_matched": 0,
        "failed": 0,
    }

    # Queue duyệt DFS / BFS: List of (drive_folder_id, rel_folder_path)
    queue: List[Tuple[str, Path]] = [(drive_root_id, Path(""))]
    visited_folders: Set[str] = set()

    while queue:
        current_folder_id, rel_folder = queue.pop(0)
        if current_folder_id in visited_folders:
            continue
        visited_folders.add(current_folder_id)

        # Tạo thư mục local tương ứng
        target_local_dir = local_base_path / rel_folder
        if not dry_run and not target_local_dir.exists():
            target_local_dir.mkdir(parents=True, exist_ok=True)
            stats["folders_created"] += 1
            logger.info("📁 Đã tạo thư mục cục bộ: %s", target_local_dir)

        # Lấy toàn bộ items trong current_folder_id
        page_token = None
        while True:
            q = f"trashed=false"
            if current_folder_id:
                q += f" and '{current_folder_id}' in parents"

            try:
                res = service.files().list(
                    q=q,
                    fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                    pageSize=200,
                    pageToken=page_token,
                ).execute()
            except Exception as e:
                logger.error("Lỗi liệt kê Drive folder '%s' (%s): %s", rel_folder, current_folder_id, e)
                stats["failed"] += 1
                break

            items = res.get("files", [])
            for item in items:
                name = item.get("name", "")
                mime = item.get("mimeType", "")
                item_id = item.get("id", "")

                # Bỏ qua folder hoặc file archive nếu có
                if name in NO_LOOP_FOLDERS or name.startswith("."):
                    continue

                if mime == "application/vnd.google-apps.folder":
                    # Là thư mục con -> thêm vào queue
                    sub_rel = rel_folder / name if str(rel_folder) else Path(name)
                    queue.append((item_id, sub_rel))
                else:
                    # Là file
                    stats["files_checked"] += 1
                    target_file = target_local_dir / name
                    drive_size = int(item.get("size") or 0)

                    # Kiểm tra xem file đã có tại local chưa
                    if target_file.exists():
                        try:
                            local_size = target_file.stat().st_size
                            if local_size == drive_size and drive_size > 0:
                                stats["files_already_matched"] += 1
                                logger.info("✓ Khớp file local: %s (size=%d bytes) — Bỏ qua tải.", target_file.relative_to(local_base_path), local_size)
                                continue
                        except OSError:
                            pass

                    # Tải file từ Drive về máy
                    if dry_run:
                        logger.info("[DRY-RUN] Sẽ tải file từ Drive: %s -> %s (%d bytes)", name, target_file, drive_size)
                        stats["files_downloaded"] += 1
                    else:
                        try:
                            logger.info("⬇️ Đang tải từ Drive: %s -> %s (%d bytes)...", name, target_file, drive_size)
                            download_file(item_id, target_file)
                            stats["files_downloaded"] += 1
                            logger.info("✓ Tải thành công: %s", target_file.name)
                        except Exception as dl_err:
                            stats["failed"] += 1
                            logger.error("❌ Lỗi tải file %s (id=%s): %s", name, item_id, dl_err)

            page_token = res.get("nextPageToken")
            if not page_token:
                break

    print("\n" + "=" * 70)
    print(">>> BÁO CÁO TỔNG KẾT DRIVE TO LOCAL RECONCILIATION:")
    print(f" - Thư mục con đã tạo tại máy : {stats['folders_created']}")
    print(f" - Tổng số file Drive quét    : {stats['files_checked']}")
    print(f" - File đã khớp sẵn (Bỏ qua) : {stats['files_already_matched']}")
    print(f" - File tải mới về máy        : {stats['files_downloaded']}")
    print(f" - Lỗi trong quá trình tải    : {stats['failed']}")
    print("=" * 70 + "\n")


# =====================================================================
# MENU CHÍNH VÀ INTERFACE
# =====================================================================

def interactive_menu():
    """Hiển thị giao diện menu tương tác người dùng."""
    # Tự động đồng bộ config từ Cloud
    sync_remote_config()

    local_path_str = get("local_base_path", "") or get("root_folder", r"H:\2026\Thac Sy\Mon_Hoc")
    local_path = Path(local_path_str)

    service = _get_drive_service()
    drive_root_id = get_drive_root_folder_id(service, get("google_drive_root_folder_id", ""))

    while True:
        print("\n" + "=" * 70)
        print("     ThsAutoOrganizer — System Migration & Reconciliation Tool")
        print("=" * 70)
        print(f"📂 Thư mục Local hiện tại : {local_path}")
        print(f"☁️ Google Drive Root ID   : {drive_root_id or '[Chưa cấu hình root ID]'}")
        print("-" * 70)
        print("  [1] LOCAL TO DRIVE MIGRATION (Đẩy dữ liệu cũ từ máy lên Google Drive)")
        print("  [2] DRIVE TO LOCAL RECONCILIATION (Đồng bộ cấu trúc chuẩn từ Drive về máy)")
        print("  [3] Chạy thử nghiệm Local to Drive (DRY-RUN - Xem trước không ghi)")
        print("  [4] Chạy thử nghiệm Drive to Local (DRY-RUN - Xem trước không tải)")
        print("  [5] Thay đổi đường dẫn Local / Drive Root ID")
        print("  [0] Thoát chương trình")
        print("=" * 70)

        choice = input("Nhập lựa chọn của bạn [0-5]: ").strip()

        if choice == "1":
            confirm = input(f"Xác nhận quét và đẩy file từ '{local_path}' lên Drive? [Y/n]: ").strip().lower()
            if confirm in ("", "y", "yes"):
                migrate_local_to_drive(local_path, drive_root_id, dry_run=False)
        elif choice == "2":
            confirm = input(f"Xác nhận lấy Drive làm gốc và tải cấu trúc về '{local_path}'? [Y/n]: ").strip().lower()
            if confirm in ("", "y", "yes"):
                reconcile_drive_to_local(local_path, drive_root_id, dry_run=False)
        elif choice == "3":
            migrate_local_to_drive(local_path, drive_root_id, dry_run=True)
        elif choice == "4":
            reconcile_drive_to_local(local_path, drive_root_id, dry_run=True)
        elif choice == "5":
            new_local = input(f"Nhập đường dẫn Local mới [{local_path}]: ").strip()
            if new_local:
                local_path = Path(new_local)
            new_drive = input(f"Nhập Google Drive Root ID mới [{drive_root_id}]: ").strip()
            if new_drive:
                drive_root_id = new_drive
            print("✓ Đã cập nhật cấu hình cho phiên làm việc hiện tại.")
        elif choice == "0":
            print("\nĐã thoát công cụ Migration. Hẹn gặp lại!")
            break
        else:
            print("Lựa chọn không hợp lệ, vui lòng chọn lại từ 0 đến 5.")


def main():
    parser = argparse.ArgumentParser(
        description="ThsAutoOrganizer — System Migration & Reconciliation CLI Tool"
    )
    parser.add_argument(
        "--mode",
        choices=["1", "2"],
        help="Chế độ chạy: 1 = Local to Drive, 2 = Drive to Local",
    )
    parser.add_argument(
        "--local-path",
        help="Đường dẫn thư mục Local (mặc định lấy từ system_config / config.json)",
    )
    parser.add_argument(
        "--drive-root",
        help="Google Drive Root Folder ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chạy ở chế độ mô phỏng, không ghi dữ liệu thực tế",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Tự động xác nhận thực hiện không cần hỏi lại",
    )

    args = parser.parse_args()

    # Nếu không truyền tham số mode -> hiển thị Menu tương tác
    if not args.mode:
        interactive_menu()
        return

    # Chế độ dòng lệnh tự động (Non-interactive CLI)
    sync_remote_config()

    local_path_str = args.local_path or get("local_base_path", "") or get("root_folder", r"H:\2026\Thac Sy\Mon_Hoc")
    local_path = Path(local_path_str)

    service = _get_drive_service()
    drive_root_id = args.drive_root or get_drive_root_folder_id(service, get("google_drive_root_folder_id", ""))

    if args.mode == "1":
        migrate_local_to_drive(local_path, drive_root_id, dry_run=args.dry_run)
    elif args.mode == "2":
        reconcile_drive_to_local(local_path, drive_root_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
