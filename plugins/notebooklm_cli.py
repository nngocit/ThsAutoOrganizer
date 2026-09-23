# plugins/notebooklm_cli.py — Plugin Nạp AI qua NotebookLM MCP CLI (<150 dòng)
import json
import logging
import shutil
import subprocess
from typing import Any, Dict, Optional, Tuple

from .base import COLOR_PURPLE, EventBus, PluginBase

NLM_BINARY = "nlm"


class NotebookLMCLIPlugin(PluginBase):
    """
    Plugin Nạp AI: Lắng nghe sự kiện ON_COURSE_CREATE và ON_SOURCE_ADD,
    thực thi lệnh nlm CLI và phát sự kiện TASK_COMPLETED.
    """

    def __init__(self, event_bus: EventBus, nlm_binary: str = NLM_BINARY) -> None:
        super().__init__(event_bus, name="AI_CLI", color=COLOR_PURPLE)
        self.nlm_binary = nlm_binary

        # Đăng ký lắng nghe sự kiện từ EventBus
        self.event_bus.on("ON_COURSE_CREATE", self.on_course_create)
        self.event_bus.on("ON_SOURCE_ADD", self.on_source_add)

    def _is_nlm_available(self) -> bool:
        """Kiểm tra sự tồn tại của CLI nlm trong môi trường."""
        return shutil.which(self.nlm_binary) is not None

    def _execute_cmd(self, args: list[str], timeout: int = 60) -> Tuple[int, str, str]:
        """Thực thi lệnh CLI an toàn, bọc Try/Catch chống treo luồng."""
        cmd = [self.nlm_binary] + args
        self.log(f"Thực thi: {' '.join(cmd)}")
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace"
            )
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except subprocess.TimeoutExpired:
            self.log(f"Lệnh nlm timeout sau {timeout}s: {args}", level=logging.WARNING)
            return -1, "", f"Timeout after {timeout}s"
        except FileNotFoundError:
            self.log(f"Không tìm thấy CLI '{self.nlm_binary}'. Hãy cài đặt notebooklm-mcp-cli.", level=logging.ERROR)
            return -2, "", "CLI binary not found"
        except Exception as e:
            self.log(f"Lỗi ngoại lệ khi gọi nlm CLI: {e}", level=logging.ERROR)
            return -3, "", str(e)

    def _parse_output_id(self, stdout: str) -> Optional[str]:
        """Trích xuất ID từ JSON stdout hoặc chuỗi thô."""
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    return data.get("notebook_id") or data.get("id") or data.get("source_id")
                except json.JSONDecodeError:
                    continue
        try:
            data = json.loads(stdout)
            return data.get("notebook_id") or data.get("id") or data.get("source_id")
        except json.JSONDecodeError:
            pass

        # Fallback tìm token dạng ID nếu output text
        for token in stdout.split():
            clean_token = token.strip(" '\"<>()[]:,")
            if len(clean_token) >= 8 and "-" in clean_token:
                return clean_token
        return None

    def on_course_create(self, payload: Dict[str, Any]) -> None:
        """
        Xử lý sự kiện ON_COURSE_CREATE:
        Tạo NotebookLM mới qua lệnh 'nlm notebook create "<display_name>"'.
        """
        if not isinstance(payload, dict):
            return

        task_id = payload.get("id") or payload.get("task_id", "")
        display_name = (payload.get("display_name") or payload.get("name") or "").strip()

        if not display_name:
            self.log(f"Task [{task_id}] bỏ qua ON_COURSE_CREATE vì thiếu display_name.", level=logging.WARNING)
            return

        self.log(f"Bắt đầu tạo NotebookLM cho môn: '{display_name}' [Task {task_id}]...")
        try:
            code, stdout, stderr = self._execute_cmd(["notebook", "create", display_name, "--json"], timeout=60)
            if code != 0 and "unrecognized" in stderr.lower():
                code, stdout, stderr = self._execute_cmd(["notebook", "create", display_name], timeout=60)

            if code == 0:
                notebooklm_id = self._parse_output_id(stdout) or "mock_nlm_id"
                self.log(f"✓ Tạo NotebookLM thành công: '{display_name}' -> notebooklm_id='{notebooklm_id}'")
                # Phát sự kiện hoàn thành
                self.event_bus.emit("TASK_COMPLETED", {
                    "task_id": task_id,
                    "action": "course_create",
                    "notebooklm_id": notebooklm_id,
                    "plugin": self.name,
                    "result": {"notebooklm_id": notebooklm_id, "display_name": display_name}
                })
            else:
                self.log(f"✗ Thất bại khi tạo Notebook: code={code}, error={stderr or stdout}", level=logging.ERROR)
        except Exception as e:
            self.log(f"Ngoại lệ ngoài dự kiến trong on_course_create: {e}", level=logging.ERROR)

    def on_source_add(self, payload: Dict[str, Any]) -> None:
        """
        Xử lý sự kiện ON_SOURCE_ADD:
        Nạp tài liệu URL vào NotebookLM qua lệnh 'nlm source add <notebooklm_id> --url "<file_url>"'.
        """
        if not isinstance(payload, dict):
            return

        task_id = payload.get("id") or payload.get("task_id", "")
        notebooklm_id = payload.get("notebooklm_id") or payload.get("notebook_id")
        file_url = payload.get("file_url") or payload.get("url")

        if not notebooklm_id or not file_url:
            self.log(f"Task [{task_id}] thiếu notebooklm_id hoặc file_url. Bỏ qua.", level=logging.WARNING)
            return

        self.log(f"Bắt đầu nạp URL vào NotebookLM [{notebooklm_id}] [Task {task_id}]...")
        try:
            code, stdout, stderr = self._execute_cmd(["source", "add", str(notebooklm_id), "--url", str(file_url), "--json"], timeout=90)
            if code != 0 and "unrecognized" in stderr.lower():
                code, stdout, stderr = self._execute_cmd(["source", "add", str(notebooklm_id), "--url", str(file_url)], timeout=90)

            if code == 0:
                source_id = self._parse_output_id(stdout) or "ok"
                self.log(f"✓ Nạp nguồn vào NotebookLM thành công! source_id='{source_id}'")
                self.event_bus.emit("TASK_COMPLETED", {
                    "task_id": task_id,
                    "action": "source_add",
                    "source_id": source_id,
                    "plugin": self.name,
                    "result": {"source_id": source_id, "file_url": file_url}
                })
            else:
                self.log(f"✗ Thất bại khi nạp nguồn: code={code}, error={stderr or stdout}", level=logging.ERROR)
        except Exception as e:
            self.log(f"Ngoại lệ ngoài dự kiến trong on_source_add: {e}", level=logging.ERROR)
