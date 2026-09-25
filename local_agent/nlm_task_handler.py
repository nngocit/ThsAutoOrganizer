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
from .config_loader import get_config, get

logger = logging.getLogger(__name__)

NLM_CMD = "nlm"

# 1. BỘ LỌC FILE: Danh sách định dạng hỗ trợ NotebookLM
SUPPORTED_EXTS = ['.pdf', '.docx', '.pptx', '.txt', '.md', '.mp3']
SUPPORTED_NLM_EXTENSIONS = set(SUPPORTED_EXTS)


def _resolve_profile_args(owner_email: str) -> list[str]:
    """Xác định cờ --profile tương ứng với owner_email hoặc cảnh báo dùng default session."""
    owner_email = (owner_email or "").strip()
    if not owner_email:
        return []

    cfg = get_config() if callable(get_config) else {}
    profiles = cfg.get("nlm_profiles", {}) if isinstance(cfg, dict) else {}
    profile = profiles.get(owner_email, "")

    if profile:
        logger.info("Đã khớp profile '%s' cho tài khoản %s", profile, owner_email)
        return ["--profile", str(profile)]

    logger.warning("Task thuộc về %s, đang xử lý bằng Local Session mặc định của máy", owner_email)
    return []


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
    base = Path(get("local_base_path", "D:\\ThacSi_HTTT\\Mon_Hoc"))
    for key in ("local_path", "file_path"):
        raw = task.get(key) or ""
        if raw:
            p = Path(raw)
            if p.exists():
                return p.resolve()
            if not p.is_absolute():
                candidate = (base / p).resolve()
                if candidate.exists():
                    return candidate

    # 2. Suy ra từ local_base_path + subject + folder_path + filename
    filename = task.get("filename", "")
    subject = (
        task.get("local_folder_name")
        or task.get("subject")
        or task.get("course_name")
        or ""
    )
    candidate = resolve_local_path(subject, task.get("folder_path", ""), filename)
    if filename and candidate.exists():
        return candidate.resolve()

    # 3. Fallback: tải từ Drive
    drive_file_id = task.get("drive_file_id", "")
    if drive_file_id and filename:
        from .drive_sync import download_file  # lazy import tránh vòng lặp
        dest = _determine_local_dest_path(task) or (Path(tempfile.gettempdir()) / "ths_agent_nlm" / filename)
        logger.info("File local không có — tải fallback từ Drive: %s -> %s", drive_file_id, dest)
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


def _report_local_sync_status(file_id: str, local_path: str, uid: str = "", status: str = "synced") -> bool:
    """Báo cáo trạng thái đồng bộ file local lên Cloudflare Worker & Firestore."""
    if not file_id:
        return False
    try:
        import requests
        worker_url = get("worker_url", "").rstrip("/")
        if not worker_url:
            return False
        headers = {
            "X-Agent-Secret": get("agent_secret", ""),
            "Content-Type": "application/json",
        }
        url = f"{worker_url}/api/files/{file_id}/local-status"
        payload = {
            "local_sync_status": status,
            "local_path": local_path,
        }
        if uid:
            payload["uid"] = uid
        resp = requests.patch(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            logger.info("Đã cập nhật local_sync_status='%s' cho file %s (%s)", status, file_id, local_path)
            return True
        else:
            logger.warning("Cập nhật local_sync_status thất bại: HTTP %s - %s", resp.status_code, resp.text)
    except Exception as e:
        logger.warning("Lỗi kết nối khi cập nhật local_sync_status cho file %s: %s", file_id, e)
    return False


def _async_download_worker(drive_file_id: str, dest_path: Path, file_id: str = "", rel_local_path: str = "", uid: str = "") -> None:
    """Track 2: Tải file từ Drive xuống ổ cứng trong thread chạy ngầm (async/background)."""
    try:
        from .drive_sync import download_file
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("[Track 2 Async] Bắt đầu tải ngầm file từ Drive: %s -> %s", drive_file_id, dest_path)
        download_file(drive_file_id, dest_path)
        logger.info("[Track 2 Async] Tải ngầm hoàn tất: %s", dest_path)
        if dest_path.exists() and dest_path.stat().st_size > 0 and file_id:
            _report_local_sync_status(file_id, rel_local_path or str(dest_path), uid, "synced")
    except Exception as e:
        logger.warning("[Track 2 Async] Tải ngầm file %s thất bại: %s", drive_file_id, e)
        if file_id:
            _report_local_sync_status(file_id, rel_local_path or str(dest_path), uid, "failed")


def _determine_local_dest_path(task: dict) -> Path | None:
    """Xác định đường dẫn local đích để lưu file khi tải về."""
    base = Path(task.get("local_base_path") or get("local_base_path", "D:\\ThacSi_HTTT\\Mon_Hoc"))
    for key in ("local_path", "file_path"):
        raw = task.get(key) or ""
        if raw:
            p = Path(raw)
            if not p.is_absolute():
                return (base / p).resolve()
            return p.resolve()

    filename = task.get("filename", "")
    if filename:
        subject = (
            task.get("local_folder_name")
            or task.get("subject")
            or task.get("course_name")
            or ""
        )
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

    raw_url = (task.get("url") or task.get("web_url") or "").strip()
    is_generic_web = bool(raw_url and "drive.google.com" not in raw_url)

    # 1. BỘ LỌC FILE: Kiểm tra file extension trước tiên (nếu không phải là web url)
    ext = Path(file_name).suffix.lower()
    if not is_generic_web and file_name and ext not in SUPPORTED_EXTS:
        logger.info("Bỏ qua file không thuộc SUPPORTED_EXTS: %s (ext=%s)", file_name, ext)
        return "skipped_ext"

    # 2. GUARD CLAUSE: Bỏ qua nếu file không thuộc môn học cụ thể (course_id rỗng hoặc subject == 'Tài liệu chung')
    course_id = (task.get("course_id") or "").strip() if task.get("course_id") is not None else ""
    subject = (
        task.get("local_folder_name")
        or task.get("subject")
        or task.get("course_name")
        or ""
    ).strip()

    if not course_id or subject == "Tài liệu chung":
        logger.info("Bỏ qua nạp NLM do file không thuộc môn học cụ thể (course_id rỗng)")
        task_id = task.get("id") or task.get("task_id")
        if task_id:
            try:
                import requests
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
    # NẠP TÀI LIỆU VÀO NOTEBOOKLM: Direct File Ingestion (--file)
    # Tuyệt đối KHÔNG truyền link drive.google.com vào cờ --url vì bot protection của Google sẽ chặn
    # và NotebookLM sẽ nạp nội dung trang lỗi Captcha "unusual traffic" thay vì file thật.
    # =========================================================================
    file_id = task.get("file_id", "")
    dest_path = _determine_local_dest_path(task)
    base = Path(get("local_base_path", "D:\\ThacSi_HTTT\\Mon_Hoc"))
    rel_local_path = ""
    if dest_path:
        try:
            rel_local_path = str(dest_path.relative_to(base)).replace("\\", "/")
        except Exception:
            rel_local_path = str(dest_path)

    # Đảm bảo file có mặt trên ổ cứng trước khi nạp vào NotebookLM
    if not dest_path or not dest_path.exists() or dest_path.stat().st_size == 0:
        if drive_file_id and dest_path:
            logger.info("File local chưa có hoặc rỗng — tải từ Drive: %s -> %s", drive_file_id, dest_path)
            from .drive_sync import download_file
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            download_file(drive_file_id, dest_path)

    if dest_path and dest_path.exists() and dest_path.stat().st_size > 0:
        logger.info("[Local Verified] File vật lý đã sẵn sàng trên đĩa: %s (%d bytes)", dest_path, dest_path.stat().st_size)
        if file_id:
            _report_local_sync_status(file_id, rel_local_path, uid, "synced")

    owner_email = (task.get("owner_email") or "").strip()
    profile_args = _resolve_profile_args(owner_email)

    # 1. Trường hợp là URL web công khai thông thường (KHÔNG phải link drive.google.com)
    raw_url = (task.get("url") or task.get("web_url") or "").strip()
    if raw_url and "drive.google.com" not in raw_url:
        logger.info("Nạp NotebookLM bằng Web URL công khai: %s -> notebook %s", raw_url, notebook_id)
        args = ["source", "add", notebook_id, "--url", raw_url,
                "--wait", "--wait-timeout", "600", "--json"] + profile_args
        returncode, stdout, stderr = _run_nlm(args, timeout=660)
        if returncode == 0:
            data = _parse_nlm_json(stdout)
            source_id = data.get("source_id") or data.get("id") or ""
            return source_id
        else:
            logger.warning("NLM source add --url lỗi: %s. Chuyển sang fallback file.", stderr or stdout)

    # 2. Trường hợp là Tệp tin tài liệu: Luôn dùng --file <local_path>
    source_path = dest_path if (dest_path and dest_path.exists() and dest_path.stat().st_size > 0) else _resolve_source_file(task)
    logger.info("Nạp NotebookLM trực tiếp qua tệp tin (--file): %s -> notebook %s", source_path.name, notebook_id)
    args = ["source", "add", notebook_id, "--file", str(source_path.resolve()),
            "--wait", "--wait-timeout", "600", "--json"] + profile_args
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


def handle_course_create(task: dict) -> str:
    r"""Xử lý action='course_create' (Luồng 1: Master Creation Flow).

    1. Chạy CLI: nlm notebook create "<display_name>" -> lấy notebooklm_id.
    2. Dùng os.makedirs tạo thư mục vật lý H:\2026\Thac Sy\Mon_Hoc\<local_folder_name>.
    3. Cập nhật notebooklm_id vào Firestore, chuyển trạng thái thành active.
    """
    display_name = (task.get("display_name") or task.get("name") or "").strip()
    local_folder_name = (task.get("local_folder_name") or "").strip()
    course_id = task.get("course_id", "")
    uid = task.get("uid", "")

    if not display_name:
        raise ValueError("course_create task thiếu display_name")

    if not _nlm_available():
        raise RuntimeError("nlm CLI không tìm thấy. Chạy: pip install notebooklm-mcp-cli")

    owner_email = (task.get("owner_email") or "").strip()
    profile_args = _resolve_profile_args(owner_email)

    # 1. Chạy nlm notebook create "<display_name>"
    ret, stdout, stderr = _run_nlm(["notebook", "create", display_name, "--json"] + profile_args, timeout=60)
    notebooklm_id = ""
    if ret == 0:
        data = _parse_nlm_json(stdout)
        notebooklm_id = data.get("notebook_id") or data.get("id") or ""
        if not notebooklm_id and stdout:
            for token in stdout.split():
                if len(token) > 8 and not token.startswith("{"):
                    notebooklm_id = token.strip()
                    break

    if not notebooklm_id:
        ret2, stdout2, stderr2 = _run_nlm(["notebook", "create", display_name] + profile_args, timeout=60)
        if ret2 == 0 and stdout2:
            for part in stdout2.split():
                if len(part) >= 10:
                    notebooklm_id = part.strip()
                    break

    if not notebooklm_id:
        raise RuntimeError(f"Không lấy được notebooklm_id từ nlm notebook create: {stderr or stdout}")

    logger.info("Đã tạo sổ NotebookLM thành công cho môn '%s': %s", display_name, notebooklm_id)

    # 2. Tạo thư mục vật lý local
    from .config_loader import get
    local_base = Path(task.get("local_base_path") or get("local_base_path", "D:\\ThacSi_HTTT\\Mon_Hoc")).resolve()
    if local_folder_name:
        target_dir = local_base / local_folder_name
        target_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Đã tạo thư mục vật lý local: %s", target_dir)

    # 3. Cập nhật Firestore document của course qua Worker API
    if course_id:
        try:
            from . import api_client
            api_client.update_course_notebooklm(
                course_id=course_id,
                notebooklm_id=notebooklm_id,
                status="active",
                uid=uid,
            )
            logger.info("Đã cập nhật course %s lên Firestore: notebooklm_id=%s, status=active", course_id, notebooklm_id)
        except Exception as e:
            logger.warning("Cập nhật course qua API cảnh báo: %s", e)

    return notebooklm_id
