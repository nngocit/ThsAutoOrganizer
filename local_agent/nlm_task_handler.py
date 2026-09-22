# local_agent/nlm_task_handler.py — NotebookLM CLI task handlers (<150 lines)
# Gọi nlm CLI subprocess để add/remove sources trong NotebookLM Plus notebook

import logging
import subprocess
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Tên binary CLI (cài qua: pip install notebooklm-mcp-cli)
NLM_CMD = "nlm"

# Extensions được NotebookLM hỗ trợ
SUPPORTED_NLM_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md", ".mp3"}


def _nlm_available() -> bool:
    """Kiểm tra nlm CLI có sẵn trong PATH không."""
    return shutil.which(NLM_CMD) is not None


def _run_nlm(args: list[str], timeout: int = 60) -> tuple[int, str, str]:
    """
    Chạy nlm CLI với args cho trước.
    
    Returns:
        (returncode, stdout, stderr)
    """
    cmd = [NLM_CMD] + args
    logger.debug("NLM CMD: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        logger.warning("nlm command timeout: %s", args)
        return -1, "", "timeout"
    except FileNotFoundError:
        logger.error("nlm CLI không tìm thấy. Chạy: pip install notebooklm-mcp-cli")
        return -2, "", "nlm not found"


def handle_source_add(task: dict) -> None:
    """
    Xử lý task action='source_add'.
    Thêm local file vào NotebookLM notebook.
    
    Task format:
        {action: "source_add", notebook_id: "...", filename: "...", 
         uid: "...", file_id: "..."}
    
    Raises:
        RuntimeError: Nếu nlm CLI không khả dụng hoặc lệnh thất bại.
    """
    if not _nlm_available():
        raise RuntimeError("nlm CLI không tìm thấy. Chạy: pip install notebooklm-mcp-cli")

    notebook_id = task.get("notebook_id", "")
    filename = task.get("filename", "")
    file_path = task.get("file_path", "")

    # Validate file extension
    if filename:
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_NLM_EXTENSIONS:
            logger.info(
                "Bỏ qua file không hỗ trợ: %s (ext=%s). NotebookLM chỉ nhận: %s",
                filename, ext, ", ".join(SUPPORTED_NLM_EXTENSIONS)
            )
            return  # Ghi status 'done' nhưng skipped

    # Nếu có file_path, dùng đường dẫn local
    if file_path and Path(file_path).exists():
        source_target = str(Path(file_path).resolve())
    elif filename:
        source_target = filename
    else:
        raise ValueError("Thiếu thông tin file để thêm vào NLM")

    # Xây dựng lệnh: nlm source add [--notebook <id>] <file>
    args = ["source", "add"]
    if notebook_id:
        args += ["--notebook", notebook_id]
    args.append(source_target)

    returncode, stdout, stderr = _run_nlm(args, timeout=120)

    if returncode != 0:
        error_msg = stderr or stdout or "Unknown NLM error"
        raise RuntimeError(f"nlm source add thất bại (code={returncode}): {error_msg}")

    logger.info("NLM source add thành công: %s → notebook %s", filename, notebook_id or "default")


def handle_source_remove(task: dict) -> None:
    """
    Xử lý task action='source_remove'.
    Gỡ source khỏi NotebookLM notebook theo source_id.
    
    Task format:
        {action: "source_remove", notebook_id: "...", source_id: "..."}
    
    Note: Lỗi ở bước này KHÔNG block cascade delete (Bước 2, 3 vẫn tiếp tục).
    """
    if not _nlm_available():
        logger.warning("nlm CLI không có — bỏ qua source_remove")
        return  # Soft failure — không raise để không block cascade delete

    source_id = task.get("source_id", "")
    notebook_id = task.get("notebook_id", "")

    if not source_id:
        logger.warning("source_remove task thiếu source_id — bỏ qua")
        return

    args = ["source", "remove"]
    if notebook_id:
        args += ["--notebook", notebook_id]
    args.append(source_id)

    returncode, stdout, stderr = _run_nlm(args, timeout=60)

    if returncode == 0:
        logger.info("NLM source remove thành công: %s từ notebook %s", source_id, notebook_id)
    else:
        # Log cảnh báo nhưng không raise — cascade delete vẫn phải tiếp tục
        logger.warning(
            "NLM source remove cảnh báo (code=%d): %s. Cascade delete vẫn tiếp tục.",
            returncode, stderr or stdout
        )
