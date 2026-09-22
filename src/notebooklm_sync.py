"""Module đồng bộ dữ liệu ngầm với Google NotebookLM qua CLI / MCP.

Hỗ trợ tự động ánh xạ môn học <-> sổ tay NotebookLM, nạp tệp nền không gây nghẽn
(Non-blocking ThreadPool), và truy vấn có trích dẫn (Citations).
"""

from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
import re
import subprocess
from typing import Any, Dict, List, Optional

from src.database import Database

logger = logging.getLogger("ThsAutoOrganizer.notebooklm_sync")

# Các phần mở rộng tệp tài liệu được Google NotebookLM hỗ trợ
SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".txt",
    ".md",
    ".pptx",
    ".ppt",
    ".mp3",
}


class NotebookLMSyncManager:
    """Quản lý tương tác với NotebookLM CLI/MCP Server."""

    def __init__(
        self,
        database: Database,
        executable: str = "nlm",
        max_workers: int = 2,
    ) -> None:
        self.database = database
        self.executable = executable
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="nlm_sync")

    def _run_cli(self, args: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
        """Thực thi lệnh CLI an toàn với UTF-8 và timeout."""
        cmd = [self.executable] + args
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

    def check_cli_status(self) -> Dict[str, Any]:
        """Kiểm tra tình trạng cài đặt và phiên đăng nhập của NotebookLM CLI."""
        try:
            res = self._run_cli(["--version"], timeout=5)
            installed = res.returncode == 0
            version = res.stdout.strip() if installed else ""
        except FileNotFoundError:
            return {
                "installed": False,
                "version": "",
                "authenticated": False,
                "error": "CLI chưa được cài đặt. Hãy chạy 'pip install notebooklm-mcp-cli' hoặc cài đặt qua uv.",
            }
        except Exception as e:
            return {
                "installed": False,
                "version": "",
                "authenticated": False,
                "error": str(e),
            }

        # Kiểm tra trạng thái đăng nhập
        authenticated = False
        try:
            auth_res = self._run_cli(["notebook", "list"], timeout=10)
            authenticated = auth_res.returncode == 0
        except Exception:
            authenticated = False

        return {
            "installed": installed,
            "version": version,
            "authenticated": authenticated,
            "error": None if authenticated else "Chưa đăng nhập. Hãy mở terminal và chạy lệnh 'nlm login'.",
        }

    def ensure_notebook_for_course(self, course_name: str, course_id: int) -> Optional[str]:
        """Lấy ID sổ tay tương ứng với môn học.

        Nếu chưa có trong CSDL, tìm kiếm trên NotebookLM hoặc tạo mới rồi lưu cache vào CSDL.
        """
        cached_id = self.database.get_subject_notebooklm_id(course_id)
        if cached_id:
            return cached_id

        # Kiểm tra danh sách sổ tay hiện có trên NotebookLM
        try:
            list_res = self._run_cli(["notebook", "list"], timeout=15)
            if list_res.returncode == 0:
                stdout = list_res.stdout
                # Tìm kiếm theo tên môn học (match JSON hoặc văn bản dạng 'ID - Name')
                try:
                    data = json.loads(stdout)
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get("name", "").strip().lower() == course_name.strip().lower():
                                nb_id = item.get("id")
                                if nb_id:
                                    self.database.update_subject_notebooklm_id(course_id, nb_id)
                                    return nb_id
                except Exception:
                    pass

                for line in stdout.splitlines():
                    if course_name.strip().lower() in line.lower():
                        match = re.search(r"([a-zA-Z0-9_\-]{8,})", line)
                        if match:
                            nb_id = match.group(1)
                            self.database.update_subject_notebooklm_id(course_id, nb_id)
                            return nb_id
        except Exception as e:
            logger.warning(f"Không thể liệt kê sổ tay NotebookLM: {e}")

        # Chưa có -> Tạo mới sổ tay trên NotebookLM
        try:
            create_res = self._run_cli(["notebook", "create", course_name], timeout=20)
            if create_res.returncode == 0:
                match = re.search(r"(?:ID|id|Id|with ID:)\s*([a-zA-Z0-9_\-]+)", create_res.stdout)
                if not match:
                    match = re.search(r"([a-zA-Z0-9_\-]{8,})", create_res.stdout)
                if match:
                    new_id = match.group(1)
                    self.database.update_subject_notebooklm_id(course_id, new_id)
                    return new_id
        except Exception as e:
            logger.error(f"Lỗi khi tạo sổ tay NotebookLM cho môn '{course_name}': {e}")

        return None

    def sync_file_to_notebook(
        self,
        file_path: str,
        course_name: str,
        course_id: int,
        file_id: Optional[int] = None,
    ) -> bool:
        """Nạp một tệp tài liệu vào sổ tay NotebookLM tương ứng."""
        p = Path(file_path)
        ext = p.suffix.lower()

        # Bỏ qua tệp không hỗ trợ
        if ext not in SUPPORTED_EXTENSIONS:
            logger.info(f"Bỏ qua tệp không hỗ trợ NotebookLM: {file_path}")
            self.database.log_notebooklm_sync(
                subject_id=course_id,
                file_path=file_path,
                notebooklm_id=None,
                status="skipped",
                file_id=file_id,
                error_message=f"Định dạng {ext} không được hỗ trợ",
            )
            return False

        nb_id = self.ensure_notebook_for_course(course_name, course_id)
        if not nb_id:
            err_msg = f"Không tìm thấy hoặc không thể tạo Notebook cho môn '{course_name}'"
            logger.error(err_msg)
            self.database.log_notebooklm_sync(
                subject_id=course_id,
                file_path=file_path,
                notebooklm_id=None,
                status="failed",
                file_id=file_id,
                error_message=err_msg,
            )
            return False

        # Thực thi thêm nguồn
        try:
            res = self._run_cli(["source", "add", nb_id, str(file_path)], timeout=60)
            if res.returncode == 0:
                logger.info(f"Nạp thành công {file_path} vào Notebook {nb_id}")
                self.database.log_notebooklm_sync(
                    subject_id=course_id,
                    file_path=file_path,
                    notebooklm_id=nb_id,
                    status="synced",
                    file_id=file_id,
                )
                return True
            else:
                err_msg = res.stderr or res.stdout
                logger.error(f"Lỗi khi nạp file vào NotebookLM: {err_msg}")
                self.database.log_notebooklm_sync(
                    subject_id=course_id,
                    file_path=file_path,
                    notebooklm_id=nb_id,
                    status="failed",
                    file_id=file_id,
                    error_message=err_msg.strip(),
                )
                return False
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Ngoại lệ khi nạp nguồn tệp vào NotebookLM: {err_msg}")
            self.database.log_notebooklm_sync(
                subject_id=course_id,
                file_path=file_path,
                notebooklm_id=nb_id,
                status="failed",
                file_id=file_id,
                error_message=err_msg,
            )
            return False

    def enqueue_sync(
        self,
        file_path: str,
        course_name: str,
        course_id: int,
        file_id: Optional[int] = None,
    ) -> None:
        """Đẩy tác vụ nạp nguồn vào hàng đợi ThreadPool chạy ngầm."""
        self.executor.submit(
            self.sync_file_to_notebook,
            file_path,
            course_name,
            course_id,
            file_id,
        )

    def query_notebook(self, notebook_id: str, prompt: str) -> Dict[str, Any]:
        """Truy vấn sổ tay trên NotebookLM và trích xuất câu trả lời kèm Citations."""
        try:
            res = self._run_cli(["query", notebook_id, prompt], timeout=60)
            if res.returncode != 0:
                return {
                    "success": False,
                    "answer": "",
                    "citations": [],
                    "error": res.stderr or res.stdout,
                }

            stdout = res.stdout.strip()
            # Trích xuất citations
            citations: List[Dict[str, Any]] = []
            citation_matches = re.findall(
                r"\[(?:Citations?|Trích dẫn|Source):\s*([^\]]+)\]",
                stdout,
                re.IGNORECASE,
            )
            for cm in citation_matches:
                citations.append({"text": cm.strip()})

            return {
                "success": True,
                "answer": stdout,
                "citations": citations,
                "error": None,
            }
        except Exception as e:
            return {
                "success": False,
                "answer": "",
                "citations": [],
                "error": str(e),
            }
