# local_agent/nlm_task_handler.py — NotebookLM CLI task handlers (<200 dòng)
# §7 ĐÍNH CHÍNH: `nlm source add <NB_ID> --file <path> --wait --json`,
# `nlm source delete <ID> --confirm` (KHÔNG có `source remove`).

import json
import logging
import subprocess
import shutil
import tempfile
from pathlib import Path

from .cascade_delete import resolve_local_path

logger = logging.getLogger(__name__)

NLM_CMD = "nlm"

SUPPORTED_NLM_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md", ".mp3"}


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


def handle_source_add(task: dict) -> None:
    """Xử lý action='source_add': nlm source add <notebook_id> --file <path> --wait --json.

    Raises RuntimeError nếu thất bại — poller sẽ mark task 'failed' (không treo 'processing').
    """
    if not _nlm_available():
        raise RuntimeError("nlm CLI không tìm thấy. Chạy: pip install notebooklm-mcp-cli")

    notebook_id = task.get("notebook_id", "")
    filename = task.get("filename", "")

    if not notebook_id:
        raise ValueError("source_add task thiếu notebook_id")

    ext = Path(filename or "").suffix.lower()
    if filename and ext not in SUPPORTED_NLM_EXTENSIONS:
        logger.info("Bỏ qua file không hỗ trợ: %s (ext=%s)", filename, ext)
        return  # done nhưng skipped

    source_path = _resolve_source_file(task)

    # §7: notebook_id là ARGUMENT; --wait để chờ NLM xử lý xong source
    args = ["source", "add", notebook_id, "--file", str(source_path),
            "--wait", "--wait-timeout", "600", "--json"]
    returncode, stdout, stderr = _run_nlm(args, timeout=660)

    if returncode != 0:
        raise RuntimeError(f"nlm source add thất bại (code={returncode}): {stderr or stdout}")

    data = _parse_nlm_json(stdout)
    source_id = data.get("source_id") or data.get("id") or ""
    logger.info("NLM source add OK: %s -> notebook %s (source_id=%s)",
                source_path.name, notebook_id, source_id or "?")


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
