# local_agent/api_client.py — HTTP client tới Cloudflare Worker (<200 dòng)
# Auth: X-Agent-Secret (route agent). Mọi method trả dict JSON hoặc raise RuntimeError.

import json
import logging
from typing import Any

import requests

from .config_loader import get

logger = logging.getLogger(__name__)

TIMEOUT = 30


def _headers() -> dict[str, str]:
    return {"X-Agent-Secret": get("agent_secret", ""), "Content-Type": "application/json"}


def _url(path: str) -> str:
    return f"{get('worker_url', '').rstrip('/')}{path}"


def _request(method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    """Gọi Worker API. Raise RuntimeError nếu HTTP/JSON lỗi."""
    try:
        resp = requests.request(method, _url(path), json=body, headers=_headers(), timeout=TIMEOUT)
    except requests.RequestException as e:
        raise RuntimeError(f"Worker API {method} {path} không kết nối được: {e}") from e
    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text[:500]}
    if resp.status_code >= 400:
        raise RuntimeError(f"Worker API {method} {path} -> {resp.status_code}: {json.dumps(data)[:300]}")
    return data


def _post(path: str, body: dict) -> dict[str, Any]:
    return _request("POST", path, body)


def check_hash(sha256: str, uid: str = "") -> dict[str, Any]:
    """POST /api/files/check-hash -> {duplicate, file_id?, drive_file_id?, filename?}."""
    target_uid = uid or get("uid", "") or get("root_account_email", "")
    body: dict[str, Any] = {"sha256": sha256}
    if target_uid:
        body["uid"] = target_uid
    return _post("/api/files/check-hash", body)


def register_file(*, filename: str, subject: str, document_type: str, sha256: str,
                  drive_file_id: str, size_bytes: int, local_path: str,
                  folder_path: str = "", course_id: str = "", uid: str = "",
                  drive_view_link: str = "") -> dict[str, Any]:
    """POST /api/files/register — Local watcher đăng ký file đã upload Drive."""
    target_uid = uid or get("uid", "") or get("root_account_email", "")
    payload: dict[str, Any] = {
        "filename": filename, "subject": subject, "document_type": document_type,
        "folder_path": folder_path, "sha256": sha256, "drive_file_id": drive_file_id,
        "size_bytes": size_bytes, "local_path": local_path, "course_id": course_id,
        "drive_view_link": drive_view_link, "webViewLink": drive_view_link,
    }
    if target_uid:
        payload["uid"] = target_uid
    return _post("/api/files/register", payload)


def agent_reply(session_id: str, *, job_id: str, message_id: str, content: str,
                citations: list | None = None, citation_style: str = "",
                model: str = "notebooklm", uid: str = "") -> dict[str, Any]:
    """POST /api/chat/sessions/:id/agent-reply — append message assistant."""
    body: dict[str, Any] = {
        "job_id": job_id, "message_id": message_id, "content": content,
        "citations": citations or [], "citation_style": citation_style, "model": model,
    }
    if uid:
        body["uid"] = uid
    return _post(f"/api/chat/sessions/{session_id}/agent-reply", body)


def agent_fail(session_id: str, *, job_id: str, message_id: str, error: str,
               uid: str = "") -> dict[str, Any]:
    """POST /api/chat/sessions/:id/agent-fail — đánh dấu message failed."""
    body: dict[str, Any] = {"job_id": job_id, "message_id": message_id, "error": error[:1000]}
    if uid:
        body["uid"] = uid
    return _post(f"/api/chat/sessions/{session_id}/agent-fail", body)


def patch_research(job_id: str, *, status: str | None = None, progress: str = "",
                   error: str = "", sources_found: int | None = None,
                   uid: str = "") -> dict[str, Any]:
    """PATCH /api/ai/research/:jobId — cập nhật tiến độ Deep Research."""
    body: dict[str, Any] = {}
    if status:
        body["status"] = status
    if progress:
        body["progress"] = progress
    if error:
        body["error"] = error[:1000]
    if sources_found is not None:
        body["sources_found"] = sources_found
    if uid:
        body["uid"] = uid
    return _request("PATCH", f"/api/ai/research/{job_id}", body)


def post_research_sources(job_id: str, sources: list[dict], uid: str = "") -> dict[str, Any]:
    """POST /api/ai/research/:jobId/sources — đăng ký nguồn unverified_web."""
    body: dict[str, Any] = {"sources": sources}
    if uid:
        body["uid"] = uid
    return _post(f"/api/ai/research/{job_id}/sources", body)


def artifact_complete(*, uid: str, course_id: str, filename: str, local_path: str,
                      drive_file_id: str, sha256: str, size_bytes: int,
                      artifact_name: str = "") -> dict[str, Any]:
    """POST /api/ai/artifact/complete — tạo file doc ket_qua (is_output, NO-LOOP)."""
    return _post("/api/ai/artifact/complete", {
        "uid": uid, "course_id": course_id, "filename": filename, "local_path": local_path,
        "drive_file_id": drive_file_id, "sha256": sha256, "size_bytes": size_bytes,
        "artifact_name": artifact_name,
    })


def post_exam_set(*, uid: str, course_id: str, title: str, flashcards: list,
                  essays: list, source_job_id: str = "") -> dict[str, Any]:
    """POST /api/exam/sets — lưu đề ôn thi (50 flashcard + 5 tự luận)."""
    return _post("/api/exam/sets", {
        "uid": uid, "course_id": course_id, "title": title,
        "flashcards": flashcards, "essays": essays, "source_job_id": source_job_id,
    })


def format_citations(sources: list[dict], style: str = "auto") -> dict[str, Any]:
    """POST /api/ai/citations/format -> {style, references, reference_block, inline_markers}."""
    return _post("/api/ai/citations/format", {"sources": sources, "style": style, "inline": True})


def list_courses(uid: str = "") -> dict[str, Any]:
    """GET /api/courses — lấy danh sách toàn bộ courses của user."""
    target_uid = uid or get("uid", "") or get("root_account_email", "")
    query = f"?uid={target_uid}" if target_uid else ""
    return _request("GET", f"/api/courses{query}")


def get_course(course_id: str, uid: str = "") -> dict[str, Any]:
    """GET /api/courses/:courseId — lấy thông tin course (kèm notebooklm_id)."""
    target_uid = uid or get("uid", "") or get("root_account_email", "")
    query = f"?uid={target_uid}" if target_uid else ""
    return _request("GET", f"/api/courses/{course_id}{query}")


def update_course_notebooklm(course_id: str, notebooklm_id: str, status: str = "active", uid: str = "") -> dict[str, Any]:
    """PUT /api/courses/:courseId/notebooklm — cập nhật notebooklm_id cho course."""
    target_uid = uid or get("uid", "") or get("root_account_email", "")
    query = f"?uid={target_uid}" if target_uid else ""
    payload = {
        "notebooklm_id": notebooklm_id,
        "status": status,
    }
    if target_uid:
        payload["uid"] = target_uid
    return _request("PUT", f"/api/courses/{course_id}/notebooklm{query}", payload)



def get_system_config(uid: str = "") -> dict[str, Any]:
    """GET /api/settings/config — nạp cấu hình hệ thống từ Firestore."""
    target_uid = uid or get("uid", "") or get("root_account_email", "")
    query = f"?uid={target_uid}" if target_uid else ""
    return _request("GET", f"/api/settings/config{query}")


def update_system_config(config_data: dict, uid: str = "") -> dict[str, Any]:
    """PUT /api/settings/config — cập nhật cấu hình hệ thống lên Firestore."""
    target_uid = uid or get("uid", "") or get("root_account_email", "")
    query = f"?uid={target_uid}" if target_uid else ""
    return _request("PUT", f"/api/settings/config{query}", config_data)


def send_log(*, level: str = "ERROR", module: str = "", message: str = "",
             error_detail: str = "", action: str = "", subject: str = "",
             file_name: str = "", context: dict | None = None, uid: str = "") -> dict[str, Any]:
    """POST /api/logs — đẩy log lỗi / sự cố từ Local Agent lên Cloud."""
    target_uid = uid or get("uid", "") or get("root_account_email", "")
    payload: dict[str, Any] = {
        "level": level,
        "source": "local_agent",
        "module": module,
        "message": message,
        "error_detail": error_detail,
        "action": action,
        "subject": subject,
        "file_name": file_name,
        "context": context or {},
    }
    if target_uid:
        payload["uid"] = target_uid
    try:
        return _post("/api/logs", payload)
    except Exception as e:
        logger.warning("Không thể gửi log lên Worker API: %s", e)
        return {"error": str(e)}
