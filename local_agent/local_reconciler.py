# local_agent/local_reconciler.py — Quét đối soát tệp thực tế trên ổ cứng Local (<150 dòng)
# Đối chiếu giữa ổ cứng vật lý (H:\2026\Thac Sy\Mon_Hoc) và Firestore cloud database.

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from .config_loader import get, load_config

logger = logging.getLogger(__name__)


def scan_local_disk(base_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """Quét toàn bộ tệp tin vật lý trong thư mục base_dir (mặc định local_base_path)."""
    raw_base = base_dir or get("local_base_path", "D:\\ThacSi_HTTT\\Mon_Hoc")
    base = Path(raw_base).resolve()
    if not base.exists():
        logger.warning("Thư mục local_base_path không tồn tại: %s", base)
        return []

    results = []
    for root, _, files in os.walk(base):
        for f in files:
            if f.startswith(".") or f.endswith(".tmp") or f.endswith(".crdownload"):
                continue
            full_path = Path(root) / f
            try:
                stat = full_path.stat()
                if stat.st_size == 0:
                    continue
                rel_path = str(full_path.relative_to(base)).replace("\\", "/")
                folder_name = full_path.parent.name
                results.append({
                    "name": f,
                    "folder": folder_name,
                    "rel_path": rel_path,
                    "full_path": str(full_path),
                    "size_bytes": stat.st_size,
                    "mtime": stat.st_mtime,
                })
            except (OSError, PermissionError) as e:
                logger.debug("Bỏ qua file %s do lỗi quyền/IO: %s", full_path, e)
    return results


def reconcile_with_firestore(uid: str = "", course_id: str = "", base_dir: Path | str | None = None) -> dict[str, Any]:
    """Đối chiếu tệp thực tế trên ổ đĩa với Firestore.
    
    Cập nhật local_sync_status='synced' và local_path chính xác cho mọi tệp có mặt trên đĩa.
    """
    from .nlm_task_handler import _report_local_sync_status

    disk_files = scan_local_disk(base_dir=base_dir)
    logger.info("Đã quét được %d tệp tin vật lý trên ổ đĩa Local", len(disk_files))

    # Xây dựng các index tra cứu nhanh
    by_rel_path = {f["rel_path"].lower(): f for f in disk_files}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for f in disk_files:
        by_name.setdefault(f["name"].lower(), []).append(f)

    # Lấy danh sách files từ Worker API hoặc Firestore REST
    files_to_check = _fetch_firestore_files(uid, course_id)
    logger.info("Tìm thấy %d tài liệu trên Firestore cần đối soát", len(files_to_check))

    matched_count = 0
    updated_count = 0

    for doc in files_to_check:
        file_id = doc.get("id") or doc.get("_id") or ""
        if not file_id:
            continue

        filename = doc.get("filename", "")
        subject = doc.get("subject") or doc.get("local_folder_name") or ""
        current_status = doc.get("local_sync_status")
        current_local_path = doc.get("local_path", "")
        doc_uid = doc.get("uid") or uid

        # Tìm match trên đĩa
        matched_disk_file = None

        # 1. Thử khớp theo current_local_path
        if current_local_path:
            clean_lp = current_local_path.replace("\\", "/").strip("/").lower()
            matched_disk_file = by_rel_path.get(clean_lp)

        # 2. Thử khớp theo subject/filename
        if not matched_disk_file and subject and filename:
            candidate_key = f"{subject}/{filename}".lower()
            matched_disk_file = by_rel_path.get(candidate_key)

        # 3. Thử khớp theo tên file đơn lẻ
        if not matched_disk_file and filename:
            candidates = by_name.get(filename.lower(), [])
            if candidates:
                # Ưu tiên candidate có folder trùng subject nếu có
                matched_disk_file = next(
                    (c for c in candidates if subject and c["folder"].lower() == subject.lower()),
                    candidates[0]
                )

        if matched_disk_file:
            matched_count += 1
            disk_rel_path = matched_disk_file["rel_path"]

            # Cần cập nhật nếu chưa synced hoặc local_path chưa chuẩn
            needs_update = (current_status != "synced") or (current_local_path != disk_rel_path)
            if needs_update:
                ok = _report_local_sync_status(file_id, disk_rel_path, doc_uid, "synced")
                if ok:
                    updated_count += 1
                    logger.info("✓ [ĐỐI SOÁT LOCAL] File '%s' -> synced (%s)", filename, disk_rel_path)

    summary = {
        "status": "success",
        "disk_files_count": len(disk_files),
        "firestore_files_count": len(files_to_check),
        "matched_count": matched_count,
        "updated_count": updated_count,
    }
    logger.info("Hoàn tất đối soát: Matched %d, Updated %d", matched_count, updated_count)
    return summary


def _fetch_firestore_files(uid: str = "", course_id: str = "") -> list[dict[str, Any]]:
    """Lấy danh sách files của user từ Worker API, fallback Firestore REST."""
    import requests

    worker_url = get("worker_url", "").rstrip("/")
    secret = get("agent_secret", "")

    # 1. Gọi Worker API GET /api/files
    if worker_url and secret:
        try:
            headers = {"X-Agent-Secret": secret, "Content-Type": "application/json"}
            url = f"{worker_url}/api/files?limit=200"
            if uid:
                url += f"&uid={uid}"
            if course_id:
                url += f"&course_id={course_id}"
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("files", [])
        except Exception as e:
            logger.debug("Không thể lấy files qua Worker API: %s", e)

    # 2. Fallback: Firestore REST qua Service Account
    try:
        sa_files = list(Path(__file__).parent.parent.glob("firebase/*adminsdk*.json"))
        if sa_files:
            from google.oauth2 import service_account
            from google.auth.transport.requests import AuthorizedSession
            creds = service_account.Credentials.from_service_account_file(
                str(sa_files[0]), scopes=["https://www.googleapis.com/auth/datastore"]
            )
            session = AuthorizedSession(creds)
            project_id = creds.project_id
            target_uids = [uid] if uid else ["105293426482467926778", "xuanngocit@gmail.com"]

            all_docs = []
            for u in target_uids:
                u_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/users/{u}/files?pageSize=100"
                r = session.get(u_url, timeout=10)
                if r.status_code == 200:
                    for d in r.json().get("documents", []):
                        f_id = d["name"].split("/")[-1]
                        fields = d.get("fields", {})
                        all_docs.append({
                            "id": f_id,
                            "uid": u,
                            "filename": fields.get("filename", {}).get("stringValue", ""),
                            "subject": fields.get("subject", {}).get("stringValue", ""),
                            "course_id": fields.get("course_id", {}).get("stringValue", ""),
                            "local_folder_name": fields.get("local_folder_name", {}).get("stringValue", ""),
                            "local_sync_status": fields.get("local_sync_status", {}).get("stringValue", ""),
                            "local_path": fields.get("local_path", {}).get("stringValue", ""),
                            "status": fields.get("status", {}).get("stringValue", ""),
                        })
            return all_docs
    except Exception as e:
        logger.warning("Lỗi fallback Firestore REST: %s", e)

    return []


def handle_reconcile_local(task: dict) -> str:
    """Task handler cho action 'reconcile_local' từ nlm_task_queue."""
    uid = task.get("uid", "")
    course_id = task.get("course_id", "")
    base_dir = task.get("local_base_path") or None
    logger.info("Bắt đầu xử lý tác vụ đối soát local (uid=%s, course_id=%s, base_dir=%s)", uid, course_id, base_dir)
    summary = reconcile_with_firestore(uid=uid, course_id=course_id, base_dir=base_dir)
    return json.dumps(summary)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    res = reconcile_with_firestore()
    print("KẾT QUẢ ĐỐI SOÁT THỰC TẾ:")
    print(json.dumps(res, indent=2, ensure_ascii=False))
