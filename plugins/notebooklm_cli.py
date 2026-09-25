import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import threading
from typing import Any, Dict, Optional, Tuple
import requests

from .base import (
    COLOR_GREEN,
    COLOR_ORANGE,
    COLOR_PURPLE,
    COLOR_RED,
    COLOR_RESET,
    EventBus,
    PluginBase,
)

try:
    from local_agent.config_loader import get_config
except ImportError:
    def get_config() -> dict[str, Any]:
        return {}

NLM_BINARY = "nlm"


class NotebookLMCLIPlugin(PluginBase):
    """
    Plugin Nạp AI: Lắng nghe sự kiện ON_COURSE_CREATE, ON_SOURCE_ADD,
    vòng đời dữ liệu (ARCHIVE, RESTORE, HARD_DELETE),
    và tự phục hồi ngữ cảnh (RECONCILE, FORCE_REINDEX).
    """

    def __init__(self, event_bus: EventBus, nlm_binary: str = NLM_BINARY) -> None:
        super().__init__(event_bus, name="AI_CLI", color=COLOR_PURPLE)
        self.nlm_binary = nlm_binary

        # Đăng ký lắng nghe sự kiện từ EventBus
        self.event_bus.on("ON_COURSE_CREATE", self.on_course_create)
        self.event_bus.on("ON_SOURCE_ADD", self.on_source_add)
        self.event_bus.on("ON_COURSE_ARCHIVE", self.on_course_archive)
        self.event_bus.on("ON_COURSE_RESTORE", self.on_course_restore)
        self.event_bus.on("ON_COURSE_HARD_DELETE", self.on_course_hard_delete)
        self.event_bus.on("ON_TRIGGER_RECONCILE", self.on_trigger_reconcile)
        self.event_bus.on("ON_FORCE_REINDEX", self.on_force_reindex)

    def _is_nlm_available(self) -> bool:
        """Kiểm tra sự tồn tại của CLI nlm trong môi trường."""
        return shutil.which(self.nlm_binary) is not None

    def _resolve_profile_args(self, owner_email: str) -> list[str]:
        """Xác định cờ --profile tương ứng với owner_email hoặc cảnh báo dùng default session."""
        owner_email = (owner_email or "").strip()
        if not owner_email:
            return []

        cfg = get_config() if callable(get_config) else {}
        profiles = cfg.get("nlm_profiles", {}) if isinstance(cfg, dict) else {}
        profile = profiles.get(owner_email, "")

        if profile:
            self.log(f"Đã khớp profile '{profile}' cho tài khoản {owner_email}")
            return ["--profile", str(profile)]

        self.log(f"Task thuộc về {owner_email}, đang xử lý bằng Local Session mặc định của máy", level=logging.WARNING)
        return []

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
        owner_email = (payload.get("owner_email") or "").strip()
        profile_args = self._resolve_profile_args(owner_email)

        if not display_name:
            self.log(f"Task [{task_id}] bỏ qua ON_COURSE_CREATE vì thiếu display_name.", level=logging.WARNING)
            return

        self.log(f"Bắt đầu tạo NotebookLM cho môn: '{display_name}' [Task {task_id}]...")
        try:
            cmd = ["notebook", "create", display_name, "--json"] + profile_args
            code, stdout, stderr = self._execute_cmd(cmd, timeout=60)
            if code != 0 and "unrecognized" in stderr.lower():
                cmd = ["notebook", "create", display_name] + profile_args
                code, stdout, stderr = self._execute_cmd(cmd, timeout=60)

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
        owner_email = (payload.get("owner_email") or "").strip()
        profile_args = self._resolve_profile_args(owner_email)

        if not notebooklm_id or not file_url:
            self.log(f"Task [{task_id}] thiếu notebooklm_id hoặc file_url. Bỏ qua.", level=logging.WARNING)
            return

        self.log(f"Bắt đầu nạp URL vào NotebookLM [{notebooklm_id}] [Task {task_id}]...")
        try:
            cmd = ["source", "add", str(notebooklm_id), "--url", str(file_url), "--json"] + profile_args
            code, stdout, stderr = self._execute_cmd(cmd, timeout=90)
            if code != 0 and "unrecognized" in stderr.lower():
                cmd = ["source", "add", str(notebooklm_id), "--url", str(file_url)] + profile_args
                code, stdout, stderr = self._execute_cmd(cmd, timeout=90)

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

    def on_course_archive(self, payload: Dict[str, Any]) -> None:
        """
        Xử lý sự kiện ON_COURSE_ARCHIVE:
        KHÔNG XÓA. Đổi tên cuốn sổ trên NotebookLM thành '[LƯU TRỮ] - <display_name>'.
        """
        if not isinstance(payload, dict):
            return

        task_id = payload.get("id") or payload.get("task_id", "")
        notebooklm_id = payload.get("notebooklm_id") or payload.get("notebook_id")
        display_name = (payload.get("display_name") or payload.get("name") or "").strip()
        owner_email = (payload.get("owner_email") or "").strip()
        profile_args = self._resolve_profile_args(owner_email)

        if not notebooklm_id:
            self.log("Bỏ qua ON_COURSE_ARCHIVE vì thiếu notebooklm_id.", level=logging.WARNING)
            return

        # Đảm bảo tiền tố [LƯU TRỮ] -
        if not display_name.startswith("[LƯU TRỮ]"):
            new_title = f"[LƯU TRỮ] - {display_name}" if display_name else "[LƯU TRỮ]"
        else:
            new_title = display_name

        self.log(f"Đang đổi tên cuốn sổ sang trạng thái lưu trữ: '{new_title}' ({notebooklm_id})...")
        try:
            cmd = ["notebook", "rename", str(notebooklm_id), new_title] + profile_args
            code, stdout, stderr = self._execute_cmd(cmd, timeout=60)

            if code == 0:
                prefix = f"{COLOR_ORANGE}[ARCHIVE]{COLOR_RESET}"
                self.logger.info(f"{self.color}[{self.name}]{COLOR_RESET} {prefix} Đã lưu trữ thành công sổ: '{new_title}' ({notebooklm_id})")
                if task_id:
                    self.event_bus.emit("TASK_COMPLETED", {
                        "task_id": task_id,
                        "action": "course_archive",
                        "notebooklm_id": notebooklm_id,
                        "plugin": self.name,
                        "result": {"notebooklm_id": notebooklm_id, "new_title": new_title}
                    })
            else:
                self.log(f"✗ Thất bại khi đổi tên sổ lưu trữ: code={code}, error={stderr or stdout}", level=logging.ERROR)
        except Exception as e:
            self.log(f"Ngoại lệ ngoài dự kiến trong on_course_archive: {e}", level=logging.ERROR)

    def on_course_restore(self, payload: Dict[str, Any]) -> None:
        """
        Xử lý sự kiện ON_COURSE_RESTORE:
        Khôi phục tên cuốn sổ trên NotebookLM trở lại <display_name> (xóa tiền tố '[LƯU TRỮ] - ').
        """
        if not isinstance(payload, dict):
            return

        task_id = payload.get("id") or payload.get("task_id", "")
        notebooklm_id = payload.get("notebooklm_id") or payload.get("notebook_id")
        display_name = (payload.get("display_name") or payload.get("name") or "").strip()
        owner_email = (payload.get("owner_email") or "").strip()
        profile_args = self._resolve_profile_args(owner_email)

        if not notebooklm_id:
            self.log("Bỏ qua ON_COURSE_RESTORE vì thiếu notebooklm_id.", level=logging.WARNING)
            return

        # Loại bỏ tiền tố lưu trữ nếu có
        clean_title = display_name
        if clean_title.startswith("[LƯU TRỮ] - "):
            clean_title = clean_title[len("[LƯU TRỮ] - "):].strip()
        elif clean_title.startswith("[LƯU TRỮ] "):
            clean_title = clean_title[len("[LƯU TRỮ] "):].strip()
        elif clean_title.startswith("[LƯU TRỮ]"):
            clean_title = clean_title[len("[LƯU TRỮ]"):].strip()

        if not clean_title:
            clean_title = "Môn học khôi phục"

        self.log(f"Đang khôi phục tên cuốn sổ: '{clean_title}' ({notebooklm_id})...")
        try:
            cmd = ["notebook", "rename", str(notebooklm_id), clean_title] + profile_args
            code, stdout, stderr = self._execute_cmd(cmd, timeout=60)

            if code == 0:
                prefix = f"{COLOR_GREEN}[RESTORE]{COLOR_RESET}"
                self.logger.info(f"{self.color}[{self.name}]{COLOR_RESET} {prefix} Đã khôi phục thành công sổ: '{clean_title}' ({notebooklm_id})")
                if task_id:
                    self.event_bus.emit("TASK_COMPLETED", {
                        "task_id": task_id,
                        "action": "course_restore",
                        "notebooklm_id": notebooklm_id,
                        "plugin": self.name,
                        "result": {"notebooklm_id": notebooklm_id, "clean_title": clean_title}
                    })
            else:
                self.log(f"✗ Thất bại khi khôi phục tên sổ: code={code}, error={stderr or stdout}", level=logging.ERROR)
        except Exception as e:
            self.log(f"Ngoại lệ ngoài dự kiến trong on_course_restore: {e}", level=logging.ERROR)

    def on_course_hard_delete(self, payload: Dict[str, Any]) -> None:
        """
        Xử lý sự kiện ON_COURSE_HARD_DELETE:
        Xóa vĩnh viễn cuốn sổ trên NotebookLM qua lệnh 'nlm notebook delete <notebooklm_id> --confirm'.
        """
        if not isinstance(payload, dict):
            return

        task_id = payload.get("id") or payload.get("task_id", "")
        notebooklm_id = payload.get("notebooklm_id") or payload.get("notebook_id")
        owner_email = (payload.get("owner_email") or "").strip()
        profile_args = self._resolve_profile_args(owner_email)

        if not notebooklm_id:
            self.log("Bỏ qua ON_COURSE_HARD_DELETE vì thiếu notebooklm_id.", level=logging.WARNING)
            return

        self.log(f"Đang xóa vĩnh viễn cuốn sổ trên NotebookLM: notebooklm_id='{notebooklm_id}'...")
        try:
            cmd = ["notebook", "delete", str(notebooklm_id), "--confirm", "--json"] + profile_args
            code, stdout, stderr = self._execute_cmd(cmd, timeout=60)
            if code != 0 and "unrecognized" in stderr.lower():
                cmd = ["notebook", "delete", str(notebooklm_id), "--confirm"] + profile_args
                code, stdout, stderr = self._execute_cmd(cmd, timeout=60)

            if code == 0:
                prefix = f"{COLOR_RED}[PURGE]{COLOR_RESET}"
                self.logger.info(f"{self.color}[{self.name}]{COLOR_RESET} {prefix} Đã xóa vĩnh viễn cuốn sổ: notebooklm_id='{notebooklm_id}'")
                if task_id:
                    self.event_bus.emit("TASK_COMPLETED", {
                        "task_id": task_id,
                        "action": "course_hard_delete",
                        "notebooklm_id": notebooklm_id,
                        "plugin": self.name,
                        "result": {"notebooklm_id": notebooklm_id, "status": "deleted"}
                    })
            else:
                self.log(f"✗ Thất bại khi xóa vĩnh viễn sổ: code={code}, error={stderr or stdout}", level=logging.ERROR)
        except Exception as e:
            self.log(f"Ngoại lệ ngoài dự kiến trong on_course_hard_delete: {e}", level=logging.ERROR)

    def _extract_db_notebooks(self, payload: Any) -> list[dict[str, str]]:
        """Trích xuất danh sách các môn học {course_id, notebooklm_id} từ payload DB."""
        results: list[dict[str, str]] = []
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    nid = item.get("notebooklm_id") or item.get("notebook_id") or item.get("id")
                    cid = item.get("course_id") or item.get("id") or ""
                    if nid:
                        results.append({"notebooklm_id": str(nid).strip(), "course_id": str(cid).strip()})
                elif isinstance(item, str) and item.strip():
                    results.append({"notebooklm_id": item.strip(), "course_id": ""})
            return results

        if not isinstance(payload, dict):
            return []

        # Kiểm tra trường courses
        courses = payload.get("courses")
        if isinstance(courses, list):
            for item in courses:
                if isinstance(item, dict):
                    nid = item.get("notebooklm_id") or item.get("notebook_id")
                    cid = item.get("course_id") or item.get("id") or ""
                    if nid:
                        results.append({"notebooklm_id": str(nid).strip(), "course_id": str(cid).strip()})

        # Kiểm tra notebooklm_ids / notebook_ids / db_notebooklm_ids
        nids = payload.get("notebooklm_ids") or payload.get("notebook_ids") or payload.get("db_notebooklm_ids")
        if isinstance(nids, list):
            for nid in nids:
                if isinstance(nid, str) and nid.strip():
                    if not any(r["notebooklm_id"] == nid.strip() for r in results):
                        results.append({"notebooklm_id": nid.strip(), "course_id": ""})

        return results

    def _send_reconcile_patch(self, course_id: str, missing_id: str, target_uid: str = "") -> None:
        """Gửi PATCH request tới Cloudflare/Firebase để cập nhật sync_status: missing_ai."""
        cfg = get_config() if callable(get_config) else {}
        worker_url = (cfg.get("worker_url") or "").rstrip("/")
        agent_secret = cfg.get("agent_secret", "")

        path = f"/api/courses/{course_id}" if course_id else f"/api/courses/{missing_id}"
        body: dict[str, Any] = {
            "sync_status": "missing_ai",
            "notebooklm_id": missing_id,
        }
        if target_uid:
            body["uid"] = target_uid

        prefix = f"{COLOR_RED}[RECONCILE WARNING]{COLOR_RESET}"
        self.logger.warning(
            f"{self.color}[{self.name}]{COLOR_RESET} {prefix} Phát hiện State Drift! NotebookLM ID '{missing_id}' "
            f"không tồn tại trên Google (đã bị xóa thủ công). Đang cập nhật sync_status: 'missing_ai'..."
        )

        # Thử qua api_client._request trước nếu có
        try:
            from local_agent.api_client import _request
            query = f"?uid={target_uid}" if target_uid else ""
            _request("PATCH", f"{path}{query}", body)
            self.logger.warning(
                f"{self.color}[{self.name}]{COLOR_RESET} {COLOR_RED}[STATE DRIFT]{COLOR_RESET} "
                f"✓ Đã cập nhật sync_status: missing_ai cho '{course_id or missing_id}'"
            )
            return
        except Exception:
            pass

        # Fallback trực tiếp qua requests nếu worker_url được cấu hình
        if worker_url:
            try:
                url = f"{worker_url}{path}"
                headers = {
                    "X-Agent-Secret": agent_secret,
                    "Content-Type": "application/json",
                }
                params = {"uid": target_uid} if target_uid else {}
                resp = requests.patch(url, json=body, headers=headers, params=params, timeout=15)
                self.logger.warning(
                    f"{self.color}[{self.name}]{COLOR_RESET} {COLOR_RED}[STATE DRIFT]{COLOR_RESET} "
                    f"✓ Đã gửi PATCH cập nhật sync_status: missing_ai (status_code={resp.status_code})"
                )
            except Exception as e:
                self.log(f"✗ Lỗi khi gửi PATCH reconcile tới Worker ({path}): {e}", level=logging.ERROR)

    def on_trigger_reconcile(self, payload: Dict[str, Any]) -> None:
        """
        SỰ KIỆN KHÁM SỨC KHỎE TỔNG THỂ (ON_TRIGGER_RECONCILE):
        Gọi CLI lấy danh sách TOÀN BỘ sổ hiện có trên NotebookLM của account đó,
        đối chiếu với danh sách DB, phát hiện ID bị xóa tay và gửi PATCH sync_status='missing_ai'.
        """
        if not isinstance(payload, (dict, list)):
            return

        owner_email = payload.get("owner_email", "") if isinstance(payload, dict) else ""
        target_uid = payload.get("uid", "") if isinstance(payload, dict) else ""
        task_id = payload.get("id") or payload.get("task_id", "") if isinstance(payload, dict) else ""

        db_notebooks = self._extract_db_notebooks(payload)
        if not db_notebooks:
            self.log("Bỏ qua ON_TRIGGER_RECONCILE vì không có notebooklm_id nào trong DB cần kiểm tra.", level=logging.INFO)
            return

        profile_args = self._resolve_profile_args(owner_email)
        self.log(f"Bắt đầu khám sức khỏe tổng thể (Reconciliation) cho {len(db_notebooks)} sổ trong DB...")

        try:
            cmd = ["notebook", "list", "--json"] + profile_args
            code, stdout, stderr = self._execute_cmd(cmd, timeout=60)
            if code != 0 and "unrecognized" in stderr.lower():
                cmd = ["notebook", "list", "-q"] + profile_args
                code, stdout, stderr = self._execute_cmd(cmd, timeout=60)

            if code != 0:
                self.log(f"✗ Không thể lấy danh sách sổ từ NotebookLM CLI (code={code}): {stderr or stdout}", level=logging.ERROR)
                return

            active_ids = set()
            try:
                data = json.loads(stdout)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "id" in item:
                            active_ids.add(str(item["id"]).strip())
                        elif isinstance(item, str):
                            active_ids.add(item.strip())
            except Exception:
                for line in stdout.splitlines():
                    tokens = line.strip().split()
                    if tokens and len(tokens[0]) >= 8 and "-" in tokens[0]:
                        active_ids.add(tokens[0].strip(" '\"<>()[]:,"))

            missing_notebooks = [nb for nb in db_notebooks if nb["notebooklm_id"] not in active_ids]

            if not missing_notebooks:
                prefix = f"{COLOR_GREEN}[RECONCILE OK]{COLOR_RESET}"
                self.logger.info(f"{self.color}[{self.name}]{COLOR_RESET} {prefix} Toàn bộ {len(db_notebooks)} sổ trong DB đều khớp và tồn tại trên Google NotebookLM.")
            else:
                for item in missing_notebooks:
                    nid = item["notebooklm_id"]
                    cid = item.get("course_id") or nid
                    self.logger.warning(
                        f"{self.color}[{self.name}]{COLOR_RESET} {COLOR_RED}[STATE DRIFT]{COLOR_RESET} "
                        f"Phát hiện State Drift! NotebookLM ID '{nid}' không tồn tại trên Google (đã bị xóa thủ công). Đang cập nhật sync_status: 'missing_ai'..."
                    )
                    self._send_reconcile_patch(course_id=cid, missing_id=nid, target_uid=target_uid)

            if task_id:
                self.event_bus.emit("TASK_COMPLETED", {
                    "task_id": task_id,
                    "action": "trigger_reconcile",
                    "plugin": self.name,
                    "result": {
                        "total_checked": len(db_notebooks),
                        "missing_count": len(missing_notebooks),
                        "missing_ids": [m["notebooklm_id"] for m in missing_notebooks]
                    }
                })
        except Exception as e:
            self.log(f"✗ Ngoại lệ ngoài dự kiến trong on_trigger_reconcile: {e}", level=logging.ERROR)

    def on_force_reindex(self, payload: Dict[str, Any]) -> None:
        """
        SỰ KIỆN ÉP NẠP LẠI FILE (ON_FORCE_REINDEX):
        Quét toàn bộ file tài liệu (.pdf, .txt, .docx) trong thư mục local và nạp lại vào NotebookLM
        qua Thread phụ ngầm (Non-blocking) để tự phục hồi context (Self-Healing).
        """
        if not isinstance(payload, dict):
            return

        notebooklm_id = payload.get("notebooklm_id") or payload.get("notebook_id")
        folder_name = (
            payload.get("local_folder_name")
            or payload.get("folder_name")
            or payload.get("display_name")
            or ""
        ).strip()
        owner_email = (payload.get("owner_email") or "").strip()
        task_id = payload.get("id") or payload.get("task_id", "")

        if not notebooklm_id or not folder_name:
            self.log("Bỏ qua ON_FORCE_REINDEX vì thiếu notebooklm_id hoặc local_folder_name.", level=logging.WARNING)
            return

        thread = threading.Thread(
            target=self._reindex_worker,
            args=(notebooklm_id, folder_name, owner_email, task_id, payload),
            daemon=True,
            name=f"ReindexWorker-{str(notebooklm_id)[:8]}"
        )
        thread.start()

    def _reindex_worker(
        self,
        notebooklm_id: str,
        folder_name: str,
        owner_email: str,
        task_id: str,
        payload: Dict[str, Any]
    ) -> None:
        """Thực thi quét file và nạp lại vào NotebookLM trên luồng ngầm."""
        cfg = get_config() if callable(get_config) else {}
        base_path = Path(cfg.get("local_base_path") or cfg.get("root_folder") or r"H:\2026\Thac Sy\Mon_Hoc")

        folder_path = Path(folder_name) if Path(folder_name).is_absolute() else (base_path / folder_name)

        if not folder_path.exists():
            self.log(f"Thư mục '{folder_path}' không tồn tại để reindex.", level=logging.WARNING)
            return

        profile_args = self._resolve_profile_args(owner_email)
        allowed_exts = {".pdf", ".txt", ".docx"}

        # Quét toàn bộ file tài liệu (.pdf, .txt, .docx)
        doc_files: list[Path] = []
        for root, _, files in os.walk(folder_path):
            for file in files:
                p = Path(root) / file
                if p.suffix.lower() in allowed_exts and not p.name.startswith("~"):
                    doc_files.append(p)

        self.log(f"Bắt đầu Force Reindex: Quét thấy {len(doc_files)} file tài liệu trong '{folder_path}'.")

        added_count = 0
        for doc in doc_files:
            try:
                cmd = ["source", "add", str(notebooklm_id), "--file", str(doc), "--json"] + profile_args
                code, stdout, stderr = self._execute_cmd(cmd, timeout=90)
                if code != 0 and "unrecognized" in stderr.lower():
                    cmd = ["source", "add", str(notebooklm_id), "--file", str(doc)] + profile_args
                    code, stdout, stderr = self._execute_cmd(cmd, timeout=90)

                output_lower = (stdout + " " + stderr).lower()
                if "already exists" in output_lower or "already added" in output_lower:
                    self.log(f"Bỏ qua file đã tồn tại trên NotebookLM: {doc.name}")
                    added_count += 1
                elif code == 0:
                    self.log(f"✓ Đã nạp lại file vào NotebookLM: {doc.name}")
                    added_count += 1
                else:
                    self.log(f"✗ Cảnh báo khi nạp file {doc.name}: {stderr or stdout}", level=logging.WARNING)
            except Exception as e:
                self.log(f"Lỗi khi nạp file {doc.name}: {e}", level=logging.WARNING)

        # Log màu tím hoàn thành
        prefix = f"{COLOR_PURPLE}[AI_REINDEX]{COLOR_RESET}"
        self.logger.info(
            f"{self.color}[{self.name}]{COLOR_RESET} {prefix} Đã khôi phục AI Context thành công "
            f"({added_count}/{len(doc_files)} files) cho môn: '{folder_name}' ({notebooklm_id})"
        )

        if task_id:
            self.event_bus.emit("TASK_COMPLETED", {
                "task_id": task_id,
                "action": "force_reindex",
                "notebooklm_id": notebooklm_id,
                "plugin": self.name,
                "result": {"status": "success", "reindexed_count": added_count, "total_files": len(doc_files)}
            })
