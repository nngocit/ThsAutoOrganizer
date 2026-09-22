"""Module đồng bộ dữ liệu ngầm với Google NotebookLM qua CLI / MCP.

Hỗ trợ tự động ánh xạ môn học <-> sổ tay NotebookLM, nạp tệp nền không gây nghẽn
(Non-blocking ThreadPool), và truy vấn có trích dẫn (Citations).
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import subprocess
import time
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
        self._status_cache: Optional[Dict[str, Any]] = None
        self._status_cache_time: float = 0.0
        self._sources_cache: Dict[str, Dict[str, Any]] = {}
        self._active_research_tasks: Dict[str, Dict[str, Any]] = {}

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

    def check_cli_status(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Kiểm tra tình trạng cài đặt và phiên đăng nhập của NotebookLM CLI (kèm bộ đệm 30s)."""
        now = time.time()
        if not force_refresh and self._status_cache and (now - self._status_cache_time < 30.0):
            return dict(self._status_cache)

        try:
            res = self._run_cli(["--version"], timeout=5)
            installed = res.returncode == 0
            version = res.stdout.strip() if installed else ""
        except FileNotFoundError:
            result = {
                "installed": False,
                "version": "",
                "authenticated": False,
                "error": "CLI chưa được cài đặt. Hãy chạy 'pip install notebooklm-mcp-cli' hoặc cài đặt qua uv.",
            }
            self._status_cache = result
            self._status_cache_time = now
            return result
        except Exception as e:
            result = {
                "installed": False,
                "version": "",
                "authenticated": False,
                "error": str(e),
            }
            self._status_cache = result
            self._status_cache_time = now
            return result

        # Kiểm tra trạng thái đăng nhập
        authenticated = False
        try:
            auth_res = self._run_cli(["notebook", "list"], timeout=10)
            authenticated = auth_res.returncode == 0
        except Exception:
            authenticated = False

        result = {
            "installed": installed,
            "version": version,
            "authenticated": authenticated,
            "error": None if authenticated else "Chưa đăng nhập. Hãy mở terminal và chạy lệnh 'nlm login'.",
        }
        self._status_cache = result
        self._status_cache_time = now
        return result

    def ensure_notebook_for_course(self, course_name: str, course_id: int) -> Optional[str]:
        """Lấy ID sổ tay tương ứng với môn học.

        Nếu chưa có trong CSDL, tìm kiếm trên NotebookLM hoặc tạo mới rồi lưu cache vào CSDL.
        """
        cached_id = self.database.get_subject_notebooklm_id(course_id)
        if cached_id and cached_id.strip() and cached_id != "notebook_id":
            return cached_id

        # Kiểm tra danh sách sổ tay hiện có trên NotebookLM
        try:
            list_res = self._run_cli(["notebook", "list"], timeout=15)
            if list_res.returncode == 0:
                stdout = list_res.stdout
                # Tìm kiếm theo tên môn học (match JSON title/name hoặc văn bản)
                try:
                    data = json.loads(stdout)
                    if isinstance(data, list):
                        c_clean = re.sub(r"[^a-zA-Z0-9]", "", course_name).lower()
                        for item in data:
                            if isinstance(item, dict):
                                title = item.get("title") or item.get("name", "")
                                t_clean = re.sub(r"[^a-zA-Z0-9]", "", title).lower()
                                if c_clean == t_clean or (len(c_clean) > 3 and (c_clean in t_clean or t_clean in c_clean)):
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
            res = self._run_cli(["source", "add", nb_id, "--file", str(file_path)], timeout=120)
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

    def query_notebook(
        self,
        notebook_id: str,
        prompt: str,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Truy vấn sổ tay trên NotebookLM và trích xuất câu trả lời kèm Citations và Conversation ID."""
        try:
            cli_args = ["query", "notebook", notebook_id, prompt, "--json"]
            if conversation_id:
                cli_args.extend(["--conversation-id", str(conversation_id)])
            res = self._run_cli(cli_args, timeout=180)
            if res.returncode != 0:
                return {
                    "success": False,
                    "answer": "",
                    "citations": [],
                    "conversation_id": conversation_id,
                    "error": res.stderr or res.stdout,
                }

            stdout = res.stdout.strip()
            answer = stdout
            citations: List[Dict[str, Any]] = []
            res_cid = conversation_id

            # Thử parse JSON trả về từ nlm CLI
            try:
                data = json.loads(stdout)
                if isinstance(data, dict):
                    answer = data.get("answer", stdout)
                    if data.get("conversation_id"):
                        res_cid = data.get("conversation_id")
                    raw_c = data.get("citations", {})
                    if isinstance(raw_c, dict):
                        for k, v in raw_c.items():
                            citations.append({"text": f"{k}: {v}"})
                    elif isinstance(raw_c, list):
                        for item in raw_c:
                            citations.append({"text": str(item)})
                    for s in data.get("sources_used", []):
                        citations.append({"source": str(s)})
            except Exception:
                # Nếu không phải JSON thuần, fallback regex
                citation_matches = re.findall(
                    r"\[(?:Citations?|Trích dẫn|Source):\s*([^\]]+)\]",
                    stdout,
                    re.IGNORECASE,
                )
                for cm in citation_matches:
                    citations.append({"text": cm.strip()})

            return {
                "success": True,
                "answer": answer,
                "citations": citations,
                "conversation_id": res_cid,
                "error": None,
            }
        except Exception as e:
            return {
                "success": False,
                "answer": "",
                "citations": [],
                "conversation_id": conversation_id,
                "error": str(e),
            }

    def get_active_conversation_id(self, notebook_id: str) -> Optional[str]:
        """Lấy conversation_id của phiên chat đang hoạt động trên Google NotebookLM."""
        try:
            res = self._run_cli(["chats", "list", notebook_id, "--json"], timeout=30)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                sessions = data.get("sessions", [])
                for s in sessions:
                    if s.get("is_active"):
                        return s.get("conversation_id")
                if sessions:
                    return sessions[0].get("conversation_id")
        except Exception as exc:
            logger.warning("Không thể lấy active conversation_id: %s", exc)
        return None

    def sync_chats_from_notebook(self, notebook_id: str, subject_id: int) -> Dict[str, Any]:
        """Đồng bộ toàn bộ lịch sử các phiên trò chuyện từ NotebookLM về SQLite."""
        synced_sessions = 0
        synced_messages = 0
        try:
            res = self._run_cli(["chats", "list", notebook_id, "--json"], timeout=45)
            if res.returncode != 0:
                return {"success": False, "error": res.stderr or res.stdout, "sessions": 0, "messages": 0}

            data = json.loads(res.stdout)
            sessions = data.get("sessions", [])

            for s in sessions:
                cid = s.get("conversation_id")
                if not cid:
                    continue

                preview = s.get("preview") or "Cuộc hội thoại NotebookLM"
                # Kiểm tra hoặc tạo session trong DB
                existing_session = self.database.get_chat_session_by_conversation_id(cid)
                if not existing_session:
                    session_id = self.database.create_chat_session(
                        subject_id=subject_id,
                        title=preview[:80],
                        conversation_id=cid,
                    )
                    synced_sessions += 1
                else:
                    session_id = existing_session["id"]

                # Lấy chi tiết transcript
                detail_res = self._run_cli(["chats", "get", notebook_id, cid, "--json"], timeout=60)
                if detail_res.returncode == 0:
                    detail_data = json.loads(detail_res.stdout)
                    turns = detail_data.get("transcript") or detail_data.get("turns") or []
                    existing_msgs = self.database.get_chat_messages(session_id)
                    existing_contents = {m.get("content", "").strip() for m in existing_msgs}

                    for turn in turns:
                        q = (turn.get("query") or "").strip()
                        a = (turn.get("answer") or "").strip()
                        if q and q not in existing_contents:
                            self.database.save_chat_message(session_id, role="user", content=q)
                            existing_contents.add(q)
                            synced_messages += 1
                        if a and a not in existing_contents:
                            self.database.save_chat_message(session_id, role="assistant", content=a)
                            existing_contents.add(a)
                            synced_messages += 1

            return {"success": True, "sessions": synced_sessions, "messages": synced_messages, "error": None}
        except Exception as e:
            logger.error("Lỗi khi đồng bộ chat từ NotebookLM: %s", e, exc_info=True)
            return {"success": False, "error": str(e), "sessions": synced_sessions, "messages": synced_messages}

    def sync_studio_artifacts(
        self,
        notebook_id: str,
        download_dir: Optional[Path] = None,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """Lấy danh sách Studio Artifacts (Slide deck, file...) và tải về đĩa nếu chưa có (kèm cache 60s)."""
        now = time.time()
        if not force_refresh and hasattr(self, "_artifacts_cache"):
            cache_entry = self._artifacts_cache.get(notebook_id)
            if cache_entry and (now - cache_entry["time"] < 60.0):
                return list(cache_entry["artifacts"])

        results: List[Dict[str, Any]] = []
        if download_dir is None:
            download_dir = Path("data") / "artifacts"
        download_dir.mkdir(parents=True, exist_ok=True)

        try:
            res = self._run_cli(["studio", "status", notebook_id, "--json"], timeout=120)
            if res.returncode != 0:
                logger.warning("Lỗi lấy studio status: %s", res.stderr or res.stdout)
                for f in download_dir.glob("slide_deck_*.pptx"):
                    results.append({
                        "id": f.stem.replace("slide_deck_", ""),
                        "type": "slide_deck",
                        "status": "completed",
                        "title": f"Slide Deck PowerPoint ({f.name})",
                        "instructions": "Slide thuyết trình đã tải về",
                        "download_url": f"/api/ai/artifacts/download?file={f.name}",
                        "local_path": str(f),
                        "filename": f.name,
                    })
                return results

            artifacts = json.loads(res.stdout)
            for art in artifacts:
                art_id = art.get("id") or art.get("artifact_id")
                art_type = art.get("type", "unknown")
                status = art.get("status", "unknown")
                instructions = art.get("custom_instructions") or ""

                item = {
                    "id": art_id,
                    "type": art_type,
                    "status": status,
                    "title": (instructions[:80] + "...") if instructions else f"Tài liệu {art_type.replace('_', ' ').title()}",
                    "instructions": instructions,
                    "download_url": None,
                    "local_path": None,
                    "filename": None,
                }

                if status == "completed" and art_type == "slide_deck":
                    local_filename = f"slide_deck_{art_id[:8]}.pptx"
                    dest_file = download_dir / local_filename
                    if not dest_file.exists():
                        logger.info("Đang tự động tải Slide Deck %s về %s...", art_id, dest_file)
                        dl_res = self._run_cli([
                            "download", "slide-deck", notebook_id,
                            "--id", art_id,
                            "--format", "pptx",
                            "--output", str(dest_file),
                        ], timeout=120)
                        if dl_res.returncode == 0 and dest_file.exists():
                            logger.info("Tải Slide Deck thành công: %s", dest_file)

                    if dest_file.exists():
                        item["local_path"] = str(dest_file)
                        item["filename"] = local_filename
                        item["download_url"] = f"/api/ai/artifacts/download?file={local_filename}"

                results.append(item)

            if not hasattr(self, "_artifacts_cache"):
                self._artifacts_cache = {}
            self._artifacts_cache[notebook_id] = {"time": now, "artifacts": results}
        except Exception as e:
            logger.error("Lỗi khi đồng bộ Studio Artifacts: %s", e, exc_info=True)
            for f in download_dir.glob("slide_deck_*.pptx"):
                results.append({
                    "id": f.stem.replace("slide_deck_", ""),
                    "type": "slide_deck",
                    "status": "completed",
                    "title": f"Slide Deck PowerPoint ({f.name})",
                    "instructions": "Slide thuyết trình đã tải về",
                    "download_url": f"/api/ai/artifacts/download?file={f.name}",
                    "local_path": str(f),
                    "filename": f.name,
                })

        return results

    def list_sources(self, notebook_id: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Lấy danh sách các nguồn hiện có trong sổ tay NotebookLM."""
        now = time.time()
        if not force_refresh and notebook_id in self._sources_cache:
            cache = self._sources_cache[notebook_id]
            if now - cache["time"] < 30.0:
                return list(cache["sources"])

        try:
            res = self._run_cli(["source", "list", notebook_id, "--json"], timeout=45)
            if res.returncode == 0 and res.stdout.strip():
                try:
                    sources = json.loads(res.stdout)
                    if isinstance(sources, list):
                        self._sources_cache[notebook_id] = {"time": now, "sources": sources}
                        return sources
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            logger.warning("Không thể lấy danh sách nguồn Notebook %s: %s", notebook_id, e)

        return []

    def remove_source_from_notebook(
        self,
        notebook_id: str,
        source_id: Optional[str] = None,
        file_name: Optional[str] = None,
        file_path: Optional[str] = None,
        subject_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Gỡ bỏ nguồn tài liệu khỏi sổ tay NotebookLM bằng source_id hoặc tên tệp."""
        target_id = source_id
        target_name = file_name or (Path(file_path).name if file_path else None)

        if not target_id and target_name:
            sources = self.list_sources(notebook_id, force_refresh=True)
            t_clean = target_name.lower().strip()
            for s in sources:
                s_title = (s.get("title") or "").lower().strip()
                if s_title == t_clean or t_clean in s_title or s_title in t_clean:
                    target_id = s.get("id")
                    break

        if not target_id:
            err = f"Không tìm thấy nguồn '{target_name or 'không rõ'}' trong Notebook {notebook_id}"
            logger.warning(err)
            return {"success": False, "error": err}

        try:
            res = self._run_cli(["source", "delete", target_id, "--confirm"], timeout=45)
            if res.returncode == 0:
                logger.info("Đã xóa thành công nguồn %s khỏi Notebook %s", target_id, notebook_id)
                self._sources_cache.pop(notebook_id, None)
                if file_path or target_name:
                    self.database.log_notebooklm_sync(
                        subject_id=subject_id or 0,
                        file_path=file_path or target_name or target_id,
                        notebooklm_id=notebook_id,
                        status="removed",
                        error_message=None,
                    )
                return {"success": True, "source_id": target_id, "message": "Đã xóa nguồn thành công"}
            else:
                err = res.stderr or res.stdout
                logger.error("Lỗi khi xóa nguồn %s: %s", target_id, err)
                return {"success": False, "error": err.strip()}
        except Exception as e:
            logger.error("Ngoại lệ khi xóa nguồn khỏi NotebookLM: %s", e)
            return {"success": False, "error": str(e)}

    def enqueue_remove_source(
        self,
        notebook_id: str,
        source_id: Optional[str] = None,
        file_name: Optional[str] = None,
        file_path: Optional[str] = None,
        subject_id: Optional[int] = None,
    ) -> None:
        """Đẩy tác vụ xóa nguồn vào hàng đợi ThreadPool chạy ngầm."""
        self.executor.submit(
            self.remove_source_from_notebook,
            notebook_id,
            source_id,
            file_name,
            file_path,
            subject_id,
        )

    def _execute_research_worker(
        self,
        task_id: str,
        notebook_id: str,
        query: str,
        mode: str,
        subject_id: Optional[int],
        subject_name: Optional[str],
        user_email: Optional[str],
        drive_manager: Optional[Any],
    ) -> None:
        """Tiến trình nền thực thi cào dữ liệu Web và đồng bộ kết quả vào Google Drive."""
        task = self._active_research_tasks.get(notebook_id)
        if not task or task.get("id") != task_id:
            return

        try:
            logger.info("Bắt đầu săn tài liệu Web (Task: %s, Notebook: %s, Query: '%s', Mode: %s)", task_id, notebook_id, query, mode)
            task["progress"] = f"Đang gửi yêu cầu nghiên cứu {mode.upper()} đến Google AI..."

            before_sources = {s.get("id") for s in self.list_sources(notebook_id, force_refresh=True) if s.get("id")}

            timeout_sec = 600 if mode == "deep" else 180
            res = self._run_cli([
                "research", "start", query,
                "--notebook-id", notebook_id,
                "--mode", mode,
                "--source", "web",
                "--auto-import",
            ], timeout=timeout_sec)

            if res.returncode != 0:
                err_msg = res.stderr or res.stdout
                logger.warning("Research CLI warning/error: %s", err_msg)
                try:
                    self._run_cli(["research", "import", notebook_id], timeout=60)
                except Exception:
                    pass

            task["progress"] = "Đang kiểm tra và nhập các nguồn web được phát hiện..."
            time.sleep(2.0)

            all_sources = self.list_sources(notebook_id, force_refresh=True)
            new_sources = [s for s in all_sources if s.get("id") not in before_sources]
            if not new_sources:
                new_sources = [s for s in all_sources if s.get("type") in ["web_page", "url", "web"]] or all_sources

            task["sources"] = new_sources
            task["sources_count"] = len(new_sources)
            task["progress"] = f"Đã phát hiện {len(new_sources)} nguồn web. Đang xuất báo cáo và lưu vào Drive..."

            clean_sub = (subject_name or "Chung").replace(" ", "_")
            slug_q = re.sub(r"[^a-zA-Z0-9_\-]", "_", query.strip().lower())[:30]
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"DeepResearch_{clean_sub}_{slug_q}_{timestamp_str}.md"

            research_dir = Path("data") / "research"
            research_dir.mkdir(parents=True, exist_ok=True)
            local_path = research_dir / filename

            lines = [
                f"# Báo Cáo Nghiên Cứu Sâu (Deep Web Research)",
                f"",
                f"- **Chủ đề / Từ khóa:** {query}",
                f"- **Môn học:** {subject_name or 'Tài liệu chung'}",
                f"- **Thời gian thực hiện:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
                f"- **Chế độ nghiên cứu:** {mode.upper()} (~{'40 nguồn' if mode == 'deep' else '10 nguồn'})",
                f"- **Số lượng nguồn tài liệu khai thác:** {len(new_sources)}",
                f"",
                f"---",
                f"",
                f"## 📚 Danh Mục Tài Liệu Tham Khảo Đã Thu Thập",
                f"",
            ]

            citations_list = []
            for idx, s in enumerate(new_sources, 1):
                s_title = s.get("title") or f"Nguồn Web #{idx}"
                s_url = s.get("url") or "#"
                s_type = s.get("type", "web")
                lines.append(f"### {idx}. {s_title}")
                lines.append(f"- **Định dạng:** `{s_type}`")
                if s.get("url"):
                    lines.append(f"- **Liên kết gốc:** [{s_url}]({s_url})")
                    citations_list.append(s_url)
                lines.append("")

            report_content = "\n".join(lines)
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(report_content)

            task["local_path"] = str(local_path)
            sha256_hash = hashlib.sha256(report_content.encode("utf-8")).hexdigest()

            drive_file_id = None
            if drive_manager and hasattr(drive_manager, "is_configured") and drive_manager.is_configured():
                try:
                    task["progress"] = "Đang tải tệp báo cáo lên Google Drive (03_Tai_Lieu_Tham_Khao)..."
                    folder_id = drive_manager.resolve_folder_hierarchy(
                        subject=subject_name or "Tài liệu chung",
                        document_type="03_Tai_Lieu_Tham_Khao",
                    )
                    drive_file_id = drive_manager.upload_file(
                        file_path=local_path,
                        parent_folder_id=folder_id,
                        custom_name=filename,
                    )
                    task["drive_file_id"] = drive_file_id
                    logger.info("Đã lưu tài liệu nghiên cứu lên Google Drive (ID: %s)", drive_file_id)
                except Exception as d_err:
                    logger.warning("Không thể tải lên Drive thư mục 03_Tai_Lieu_Tham_Khao: %s", d_err)

            rec_status = "UPLOADED" if drive_file_id else "SAVED_LOCAL"
            self.database.insert_record(
                sha256=sha256_hash,
                path=str(local_path),
                subject=subject_name or "Tài liệu chung",
                document_type="03_Tai_Lieu_Tham_Khao",
                status=rec_status,
                drive_file_id=drive_file_id,
                user_email=user_email,
            )

            if subject_id:
                self.database.save_ai_insight(
                    subject_id=subject_id,
                    insight_type="deep_research",
                    title=f"Nghiên cứu Web ({mode.upper()}): {query}",
                    content=report_content,
                    citations=json.dumps(citations_list, ensure_ascii=False) if citations_list else None,
                    created_by="notebooklm_research",
                )

            task["status"] = "completed"
            task["progress"] = f"Hoàn tất! Đã thu thập {len(new_sources)} nguồn và lưu vào thư mục 03_Tai_Lieu_Tham_Khao."
            logger.info("Hoàn tất tác vụ nghiên cứu Web %s thành công.", task_id)

        except Exception as e:
            logger.error("Lỗi trong quá trình nghiên cứu Web: %s", e, exc_info=True)
            task["status"] = "failed"
            task["error"] = str(e)
            task["progress"] = f"Lỗi: {e}"

    def start_web_research(
        self,
        notebook_id: str,
        query: str,
        mode: str = "deep",
        subject_id: Optional[int] = None,
        subject_name: Optional[str] = None,
        user_email: Optional[str] = None,
        drive_manager: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Bắt đầu tác vụ Săn tài liệu (Deep Web Research) ngầm không gây nghẽn."""
        clean_query = query.strip()
        if not clean_query:
            return {"success": False, "error": "Từ khóa nghiên cứu không được để trống"}

        active = self._active_research_tasks.get(notebook_id)
        if active and active.get("status") == "running":
            return {
                "success": True,
                "task_id": active.get("id"),
                "status": "already_running",
                "message": "Đang có một tiến trình nghiên cứu đang chạy cho sổ tay này",
            }

        task_id = f"research_{int(time.time())}"
        task_info = {
            "id": task_id,
            "notebook_id": notebook_id,
            "subject_id": subject_id,
            "subject_name": subject_name or "Tài liệu",
            "query": clean_query,
            "mode": mode,
            "status": "running",
            "start_time": time.time(),
            "progress": f"Đang khởi động cào web ({mode.upper()})...",
            "sources_count": 0,
            "sources": [],
            "drive_file_id": None,
            "local_path": None,
            "error": None,
        }
        self._active_research_tasks[notebook_id] = task_info

        self.executor.submit(
            self._execute_research_worker,
            task_id,
            notebook_id,
            clean_query,
            mode,
            subject_id,
            subject_name,
            user_email,
            drive_manager,
        )

        return {
            "success": True,
            "task_id": task_id,
            "status": "running",
            "message": f"Đã bắt đầu săn tài liệu cho '{clean_query}'",
        }

    def get_research_status(self, notebook_id: str) -> Dict[str, Any]:
        """Lấy trạng thái tác vụ nghiên cứu mới nhất của sổ tay."""
        task = self._active_research_tasks.get(notebook_id)
        if task:
            return dict(task)

        try:
            res = self._run_cli(["research", "status", notebook_id, "--max-wait", "0"], timeout=15)
            stdout = res.stdout.strip()
            return {
                "id": None,
                "notebook_id": notebook_id,
                "status": "idle",
                "progress": stdout or "Không có tác vụ nghiên cứu nào đang chờ",
                "sources_count": 0,
                "sources": [],
            }
        except Exception:
            return {
                "id": None,
                "notebook_id": notebook_id,
                "status": "idle",
                "progress": "Sẵn sàng nghiên cứu",
                "sources_count": 0,
                "sources": [],
            }

    # ==================== Cascade Delete 4 bước (Safe Cascade Delete) ====================

    def cascade_delete_file(
        self,
        file_record: Dict[str, Any],
        notebook_id: Optional[str] = None,
        drive_manager: Optional[Any] = None,
        deleted_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Xóa file theo 4 bước an toàn: Step1=NLM remove, Step2=Drive archive, Step3=SQLite soft-delete, Step4=schedule 90d.

        Args:
            file_record: Bản ghi file từ database (dict có 'id', 'path', 'drive_file_id', 'subject').
            notebook_id: ID sổ tay NotebookLM của môn học tương ứng.
            drive_manager: DriveManager đã được cấu hình (dùng cho Drive archive).
            deleted_by: Email người thực hiện xóa.

        Returns:
            Dict kết quả với các key: step1/step2/step3/step4 (bool) + 'log_id' + 'errors'.
        """
        result: Dict[str, Any] = {
            "step1_nlm_remove": False,
            "step2_drive_archive": False,
            "step3_sqlite_softdelete": False,
            "step4_scheduled_hard_delete": False,
            "log_id": None,
            "errors": [],
        }

        file_id = file_record.get("id")
        file_path = file_record.get("path")
        drive_file_id = file_record.get("drive_file_id")
        subject = file_record.get("subject", "")
        file_name = Path(file_path).name if file_path else None

        # Lấy NLM source ID từ sync log
        nlm_source_id: Optional[str] = None
        if file_id and self.database:
            nlm_source_id = self.database.get_nlm_source_id_for_file(file_id)

        # ==== STEP 1: Gỡ Source AI — AI ngắt trích dẫn lập tức ====
        if notebook_id:
            try:
                remove_result = self.remove_source_from_notebook(
                    notebook_id=notebook_id,
                    source_id=nlm_source_id,
                    file_name=file_name,
                    file_path=file_path,
                )
                if remove_result.get("success"):
                    result["step1_nlm_remove"] = True
                    logger.info("[Cascade Delete] Step 1 OK: Đã gỡ source khỏi NLM (source=%s)", nlm_source_id or file_name)
                else:
                    err = f"Step 1 warning: {remove_result.get('error', 'unknown')}"
                    result["errors"].append(err)
                    logger.warning("[Cascade Delete] %s", err)
                    # Không block các bước sau nếu source không tồn tại trên NLM
                    result["step1_nlm_remove"] = True  # Mark OK nếu source không tồn tại
            except Exception as e:
                result["errors"].append(f"Step 1 exception: {e}")
                logger.error("[Cascade Delete] Step 1 exception: %s", e)
        else:
            result["step1_nlm_remove"] = True  # Bỏ qua nếu không có notebook_id
            logger.info("[Cascade Delete] Step 1 skipped: không có notebook_id")

        # ==== STEP 2: Soft Delete trên Drive — dời sang _Archive_Trash_90Days/ ====
        if drive_file_id and drive_manager:
            try:
                archive_folder_id = drive_manager.get_or_create_archive_folder()
                if archive_folder_id:
                    drive_manager.move_file(drive_file_id, archive_folder_id)
                    result["step2_drive_archive"] = True
                    logger.info("[Cascade Delete] Step 2 OK: File đã dời sang _Archive_Trash_90Days/ (Drive ID=%s)", drive_file_id)
                else:
                    result["errors"].append("Step 2: Không tạo được folder _Archive_Trash_90Days/ trên Drive")
            except Exception as e:
                result["errors"].append(f"Step 2 exception: {e}")
                logger.error("[Cascade Delete] Step 2 exception: %s", e)
        else:
            result["step2_drive_archive"] = True  # Bỏ qua nếu chưa upload Drive
            logger.info("[Cascade Delete] Step 2 skipped: không có drive_file_id hoặc drive_manager")

        # ==== STEP 3: Soft Delete trên PC local — cập nhật Firebase/SQLite status='archived' ====
        try:
            if file_id and self.database:
                from src.database import STATUS_ERROR  # reuse để đánh dấu archived
                # Lưu log soft-delete + schedule hard-delete sau 90 ngày
                log_id = self.database.log_soft_delete(
                    file_id=file_id,
                    original_path=file_path,
                    drive_file_id=drive_file_id,
                    nlm_source_id=nlm_source_id,
                    subject=subject,
                    deleted_by=deleted_by,
                    hard_delete_days=90,
                )
                result["log_id"] = log_id
                result["step3_sqlite_softdelete"] = True
                logger.info("[Cascade Delete] Step 3 OK: Logged soft-delete (log_id=%s, schedule=90d)", log_id)
            else:
                result["step3_sqlite_softdelete"] = True
        except Exception as e:
            result["errors"].append(f"Step 3 exception: {e}")
            logger.error("[Cascade Delete] Step 3 exception: %s", e)

        # ==== STEP 4: Cronjob mark — hệ thống đã schedule, Hard Delete xảy ra sau 90 ngày ====
        result["step4_scheduled_hard_delete"] = result["step3_sqlite_softdelete"]
        if result["step4_scheduled_hard_delete"]:
            logger.info("[Cascade Delete] Step 4: Hard Delete scheduled sau 90 ngày (log_id=%s)", result["log_id"])

        return result

    def enqueue_cascade_delete(
        self,
        file_record: Dict[str, Any],
        notebook_id: Optional[str] = None,
        drive_manager: Optional[Any] = None,
        deleted_by: Optional[str] = None,
    ) -> None:
        """Đẩy 4-step Cascade Delete vào hàng đợi ThreadPool chạy ngầm."""
        self.executor.submit(
            self.cascade_delete_file,
            file_record,
            notebook_id,
            drive_manager,
            deleted_by,
        )

    def run_due_hard_deletes(self) -> Dict[str, Any]:
        """Chạy Hard Delete cho các file đã hết 90 ngày (dùng cho Cronjob hàng ngày).

        Thực hiện xóa vật lý file local + ghi nhận hoàn tất vào file_deletion_logs.
        """
        if not self.database:
            return {"processed": 0, "errors": []}

        due_items = self.database.get_due_for_hard_delete()
        processed = 0
        errors: List[str] = []

        for item in due_items:
            try:
                log_id = item["id"]
                local_path = item.get("original_path")

                # Xóa file vật lý trên máy (ghi vào Recycle Bin Windows)
                if local_path:
                    p = Path(local_path)
                    if p.is_file():
                        try:
                            import send2trash
                            send2trash.send2trash(str(p))
                            logger.info("[Hard Delete] Đã chuyển '%s' vào Recycle Bin.", p)
                        except ImportError:
                            p.unlink(missing_ok=True)
                            logger.info("[Hard Delete] Đã xóa vĩnh viễn '%s' (send2trash không có).", p)

                self.database.mark_hard_deleted(log_id=log_id, backup_link=item.get("backup_link"))
                processed += 1
            except Exception as e:
                err = f"Hard delete log_id={item.get('id')} lỗi: {e}"
                errors.append(err)
                logger.error("[Hard Delete] %s", err)

        return {"processed": processed, "errors": errors}

