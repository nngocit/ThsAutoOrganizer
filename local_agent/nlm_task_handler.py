# local_agent/nlm_task_handler.py — NotebookLM CLI task handlers (<200 dòng)
# §7 ĐÍNH CHÍNH: `nlm source add <NB_ID> --file <path> --wait --json`,
# `nlm source delete <ID> --confirm` (KHÔNG có `source remove`).

import json
import logging
import subprocess
import shutil
import tempfile
import threading
from pathlib import Path

from .cascade_delete import resolve_local_path

logger = logging.getLogger(__name__)

NLM_CMD = "nlm"

# 1. BỘ LỌC FILE: Danh sách định dạng hỗ trợ NotebookLM
SUPPORTED_EXTS = ['.pdf', '.docx', '.pptx', '.txt', '.md', '.mp3']
SUPPORTED_NLM_EXTENSIONS = set(SUPPORTED_EXTS)


def _nlm_available() -> bool:
    """Kiểm tra nlm CLI có sẵn trong PATH không."""
    return shutil.which(NLM_CMD) is not None


def _run_nlm(args: list[str], timeout: int = 60) -> tuple[int, str, str]:
    """Chạy nlm CLI. Returns (returncode, stdout, stderr). Luôn encoding utf-8 + timeout."""
    cmd = [NLM_CMD] + args
    logger.debug("NLM CMD: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout, encoding="utf-8")
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        logger.warning("nlm command timeout (%ss): %s", timeout, args)
        return -1, "", f"timeout after {timeout}s"
    except FileNotFoundError:
        logger.error("nlm CLI không tìm thấy. Chạy: pip install notebooklm-mcp-cli")
        return -2, "", "nlm not found"


def _parse_nlm_json(stdout: str) -> dict:
    """Parse JSON từ stdout nlm (có thể lẫn log). Trả {} nếu không parse được."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        return {}


def _resolve_source_file(task: dict) -> Path:
    """Tự resolve đường dẫn file local; fallback tải từ Drive theo drive_file_id.

    Raises ValueError nếu không lấy được file.
    """
    # 1. local_path / file_path trực tiếp trong task
    for key in ("local_path", "file_path"):
        raw = task.get(key) or ""
        if raw and Path(raw).exists():
            return Path(raw).resolve()

    # 2. Suy ra từ local_base_path + subject + folder_path + filename
    filename = task.get("filename", "")
    candidate = resolve_local_path(task.get("subject", ""), task.get("folder_path", ""), filename)
    if filename and candidate.exists():
        return candidate.resolve()

    # 3. Fallback: tải từ Drive
    drive_file_id = task.get("drive_file_id", "")
    if drive_file_id and filename:
        from .drive_sync import download_file  # lazy import tránh vòng lặp
        dest = Path(tempfile.gettempdir()) / "ths_agent_nlm" / filename
        logger.info("File local không có — tải fallback từ Drive: %s", drive_file_id)
        return download_file(drive_file_id, dest).resolve()

    raise ValueError(f"Không resolve được file local (filename={filename!r}, "
                     f"drive_file_id={drive_file_id!r})")


def lookup_notebook_id_from_course(course_id: str, uid: str = "") -> str:
    """Tra cứu Firestore collection 'courses' để lấy notebooklm_id theo course_id.

    Dùng Try/Catch đầy đủ, thử cả Worker API lẫn Firestore REST trực tiếp.
    """
    if not course_id:
        return ""

    # 1. Thử gọi Worker API
    try:
        from .api_client import get_course
        course_data = get_course(course_id, uid=uid)
        nb_id = course_data.get("notebooklm_id") or course_data.get("notebook_id") or ""
        if nb_id:
            logger.info("Đã tìm thấy notebooklm_id từ course %s qua API: %s", course_id, nb_id)
            return nb_id
    except Exception as e:
        logger.debug("Lookup course qua API lỗi (%s): %s", course_id, e)

    # 2. Fallback: truy vấn Firestore REST trực tiếp nếu có service account
    try:
        sa_files = list(Path(__file__).parent.parent.glob("firebase/*adminsdk*.json"))
        if sa_files:
            from google.oauth2 import service_account  # type: ignore
            from google.auth.transport.requests import AuthorizedSession  # type: ignore
            sa_path = sa_files[0]
            creds = service_account.Credentials.from_service_account_file(
                str(sa_path), scopes=["https://www.googleapis.com/auth/datastore"]
            )
            session = AuthorizedSession(creds)
            project_id = creds.project_id

            candidates = []
            if uid:
                candidates.append(f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/users/{uid}/courses/{course_id}")
            candidates.append(f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/courses/{course_id}")

            for url in candidates:
                res = session.get(url, timeout=10)
                if res.status_code == 200:
                    fields = res.json().get("fields", {})
                    nb_id = fields.get("notebooklm_id", {}).get("stringValue") or fields.get("notebook_id", {}).get("stringValue") or ""
                    if nb_id:
                        logger.info("Đã tìm thấy notebooklm_id từ Firestore REST cho course %s: %s", course_id, nb_id)
                        return nb_id
    except Exception as e:
        logger.debug("Lookup course qua Firestore REST lỗi (%s): %s", course_id, e)

    return ""


def _resolve_notebook_id(subject: str) -> str:
    """Tự động tìm Notebook trên Google NotebookLM theo tên môn học (subject)."""
    if not _nlm_available() or not subject:
        return ""
    try:
        import re
        rc, stdout, stderr = _run_nlm(["notebook", "list"], timeout=30)
        if rc == 0:
            data = _parse_nlm_json(stdout)
            notebooks = data if isinstance(data, list) else (data.get("notebooks", []) if isinstance(data, dict) else [])
            if not notebooks:
                try:
                    notebooks = json.loads(stdout)
                except Exception:
                    pass
            s_clean = re.sub(r"[^a-zA-Z0-9]", "", subject).lower()
            if isinstance(notebooks, list):
                for nb in notebooks:
                    if isinstance(nb, dict):
                        title = nb.get("title") or nb.get("name") or ""
                        t_clean = re.sub(r"[^a-zA-Z0-9]", "", title).lower()
                        if s_clean and (s_clean == t_clean or s_clean in t_clean or t_clean in s_clean):
                            nb_id = nb.get("id") or ""
                            logger.info("Tự động nhận diện Notebook cho môn %s: '%s' (id=%s)", subject, title, nb_id)
                            return nb_id
    except Exception as e:
        logger.warning("Lỗi tự động tra cứu notebook cho môn %s: %s", subject, e)
    return ""


def _async_download_worker(drive_file_id: str, dest_path: Path) -> None:
    """Track 2: Tải file từ Drive xuống ổ cứng trong thread chạy ngầm (async/background)."""
    try:
        from .drive_sync import download_file
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("[Track 2 Async] Bắt đầu tải ngầm file từ Drive: %s -> %s", drive_file_id, dest_path)
        download_file(drive_file_id, dest_path)
        logger.info("[Track 2 Async] Tải ngầm hoàn tất: %s", dest_path)
    except Exception as e:
        logger.warning("[Track 2 Async] Tải ngầm file %s thất bại: %s", drive_file_id, e)


def _determine_local_dest_path(task: dict) -> Path | None:
    """Xác định đường dẫn local đích để lưu file khi tải về."""
    for key in ("local_path", "file_path"):
        raw = task.get(key) or ""
        if raw:
            return Path(raw).resolve()

    filename = task.get("filename", "")
    if filename:
        subject = task.get("subject", "")
        folder_path = task.get("folder_path", "")
        return resolve_local_path(subject, folder_path, filename).resolve()
    return None


def handle_source_add(task: dict) -> str:
    """Xử lý action='source_add' theo mô hình Đa luồng (Dual-Track Injection).

    Track 1 (Ưu tiên): Nạp NotebookLM bằng Drive URL ngay lập tức:
        nlm source add <notebook_id> --url "<Drive_URL>" --wait --json.
        Trả về source_id để cập nhật status 'synced' lên Firestore cho UI báo thành công liền.
    Track 2 (Chạy ngầm/Async): Tải file vật lý từ Drive xuống ổ cứng trong background thread,
        TUYỆT ĐỐI không block Track 1.

    Returns: source_id (str) khi sync thành công, 'skipped_ext' khi bỏ qua định dạng file.
    Raises RuntimeError nếu thất bại — poller sẽ mark task 'failed' (không treo 'processing').
    """
    filename = task.get("filename", "") or ""
    local_path = task.get("local_path", "") or task.get("file_path", "") or ""
    file_name = filename or Path(local_path).name

    # 1. BỘ LỌC FILE: Kiểm tra file extension trước tiên
    ext = Path(file_name).suffix.lower()
    if file_name and ext not in SUPPORTED_EXTS:
        logger.info("Bỏ qua file không thuộc SUPPORTED_EXTS: %s (ext=%s)", file_name, ext)
        return "skipped_ext"

    # 2. GUARD CLAUSE: Bỏ qua nếu file không thuộc môn học cụ thể (course_id rỗng hoặc subject == 'Tài liệu chung')
    course_id = (task.get("course_id") or "").strip() if task.get("course_id") is not None else ""
    subject = (task.get("subject") or "").strip() if task.get("subject") is not None else ""

    if not course_id or subject == "Tài liệu chung":
        logger.info("Bỏ qua nạp NLM do file không thuộc môn học cụ thể (course_id rỗng)")
        task_id = task.get("id") or task.get("task_id")
        if task_id:
            try:
                import requests
                from .config_loader import get
                worker_url = get("worker_url", "").rstrip("/")
                if worker_url:
                    headers = {"X-Agent-Secret": get("agent_secret", ""), "Content-Type": "application/json"}
                    url = f"{worker_url}/api/tasks/nlm_task_queue/{task_id}"
                    requests.patch(url, json={"status": "skipped_no_course", "result": "skipped_no_course"}, headers=headers, timeout=15)
            except Exception as e:
                logger.warning("Không thể cập nhật task status skipped_no_course: %s", e)
        return "skipped_no_course"

    if not _nlm_available():
        raise RuntimeError("nlm CLI không tìm thấy. Chạy: pip install notebooklm-mcp-cli")

    notebook_id = task.get("notebook_id", "")
    uid = task.get("uid", "")
    drive_file_id = task.get("drive_file_id", "")

    # 3. AUTO-LOOKUP NOTEBOOK_ID: nếu thiếu notebook_id nhưng có course_id -> chọc Firestore courses
    if not notebook_id and course_id:
        try:
            nb_from_course = lookup_notebook_id_from_course(course_id, uid)
            if nb_from_course:
                notebook_id = nb_from_course
                task["notebook_id"] = notebook_id
                logger.info("Auto-lookup notebook_id từ Firestore course %s thành công: %s", course_id, notebook_id)
        except Exception as e:
            logger.warning("Lỗi khi auto-lookup notebook_id từ course %s: %s", course_id, e)

    # Fallback tra cứu Notebook theo tên môn học (subject) nếu vẫn chưa có
    if not notebook_id and subject:
        try:
            notebook_id = _resolve_notebook_id(subject)
            if notebook_id:
                task["notebook_id"] = notebook_id
        except Exception as e:
            logger.warning("Lỗi khi tra cứu notebook theo subject %s: %s", subject, e)

    if not notebook_id:
        msg = f"source_add task thiếu notebook_id (course_id={course_id!r}, subject={subject!r})"
        try:
            from .api_client import send_log
            send_log(level="ERROR", module="nlm_task_handler", action="source_add",
                     subject=subject, file_name=file_name, message=msg, context=task, uid=uid)
        except Exception:
            pass
        raise ValueError(msg)

    # =========================================================================
    # TRACK 2 (CHẠY NGẦM / ASYNC): Tải file vật lý từ Drive xuống ổ cứng (Local Path)
    # TUYỆT ĐỐI KHÔNG block quá trình của Track 1
    # =========================================================================
    dest_path = _determine_local_dest_path(task)
    if drive_file_id and dest_path and not dest_path.exists():
        threading.Thread(
            target=_async_download_worker,
            args=(drive_file_id, dest_path),
            name=f"track2-bg-dl-{drive_file_id[:8]}",
            daemon=True,
        ).start()
        logger.info("[Track 2 Async] Đã kích hoạt tải ngầm file %s -> %s (non-blocking)", drive_file_id, dest_path)

    # =========================================================================
    # TRACK 1 (ƯU TIÊN): Nạp NotebookLM bằng Drive URL ngay lập tức
    # =========================================================================
    drive_url = (
        task.get("drive_view_link")
        or task.get("webViewLink")
        or task.get("drive_url")
        or task.get("url")
        or ""
    )
    if not drive_url and drive_file_id:
        drive_url = f"https://drive.google.com/file/d/{drive_file_id}/view"

    if drive_url:
        logger.info("[Track 1 Fast] Nạp NotebookLM bằng Drive URL: %s -> notebook %s", drive_url, notebook_id)
        args = ["source", "add", notebook_id, "--url", drive_url,
                "--wait", "--wait-timeout", "600", "--json"]
        returncode, stdout, stderr = _run_nlm(args, timeout=660)

        if returncode == 0:
            data = _parse_nlm_json(stdout)
            source_id = data.get("source_id") or data.get("id") or ""
            logger.info("[Track 1 Fast] NLM source add URL OK: %s -> notebook %s (source_id=%s)",
                        drive_url, notebook_id, source_id or "?")
            return source_id
        else:
            logger.warning("[Track 1 Fast] nlm source add --url gặp lỗi (code=%d): %s. Thử fallback qua file cục bộ.",
                           returncode, stderr or stdout)

    # Fallback Track 1b: nạp bằng file local nếu không có Drive URL hoặc nạp URL không thành công
    source_path = _resolve_source_file(task)
    args = ["source", "add", notebook_id, "--file", str(source_path),
            "--wait", "--wait-timeout", "600", "--json"]
    returncode, stdout, stderr = _run_nlm(args, timeout=660)

    if returncode != 0:
        msg = f"nlm source add thất bại (code={returncode}): {stderr or stdout}"
        try:
            from .api_client import send_log
            send_log(level="ERROR", module="nlm_task_handler", action="source_add",
                     subject=subject, file_name=file_name, message=msg, error_detail=stderr or stdout,
                     context=task, uid=uid)
        except Exception:
            pass
        raise RuntimeError(msg)

    data = _parse_nlm_json(stdout)
    source_id = data.get("source_id") or data.get("id") or ""
    logger.info("NLM source add OK (file): %s -> notebook %s (source_id=%s)",
                source_path.name, notebook_id, source_id or "?")
    return source_id


def handle_source_remove(task: dict) -> None:
    """Xử lý action='source_remove': nlm source delete <source_id> --confirm --json.

    KHÔNG raise khi lỗi — để cascade delete (bước 2, 3) tiếp tục.
    """
    source_id = task.get("source_id", "") or task.get("notebooklm_source_id", "")
    if not source_id:
        logger.warning("source_remove task thiếu source_id — bỏ qua")
        return
    if not _nlm_available():
        logger.warning("nlm CLI không có — bỏ qua source_remove %s", source_id)
        return

    args = ["source", "delete", source_id, "--confirm", "--json"]
    returncode, stdout, stderr = _run_nlm(args, timeout=60)

    if returncode == 0:
        logger.info("NLM source delete OK: %s", source_id)
    else:
        logger.warning("NLM source delete lỗi (code=%d): %s. Cascade vẫn tiếp tục.",
                       returncode, stderr or stdout)
