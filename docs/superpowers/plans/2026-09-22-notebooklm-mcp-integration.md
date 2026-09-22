# Kế Hoạch Triển Khai Tích Hợp NotebookLM MCP & AI Study Hub (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hiện thực hóa trọn vẹn Workflow 4 bước kết nối ThsAutoOrganizer với Google NotebookLM Plus thông qua giao thức MCP (Model Context Protocol), bao gồm MCP Server trong AntiGravity IDE, module đồng bộ ngầm Python, CSDL lưu trữ trích dẫn Citations, và giao diện Web "AI Study Hub" chuẩn phong cách Obsidian Minimalist Academic.

**Architecture:** Cài đặt package `notebooklm-mcp-cli` làm MCP Server cục bộ cho AntiGravity IDE; phát triển module backend `src/notebooklm_sync.py` quản lý ánh xạ môn học <-> sổ tay NotebookLM và nạp file nền (ThreadPool); mở rộng SQLite schema (`courses.notebooklm_id`, `ai_insights`, `notebooklm_sync_log`); bổ sung các REST API `/api/ai/*` và xây dựng Tab giao diện "🧠 AI Study Hub" trên Web Dashboard.

**Tech Stack:** Python 3.13 (`notebooklm-mcp-cli`, SQLite3, `concurrent.futures`, `subprocess`), Vanilla HTML5/CSS3/JavaScript (Obsidian Minimalist theme), Pytest.

**Spec:** [`docs/superpowers/specs/2026-09-22-notebooklm-mcp-integration-design.md`](file:///h:/2026/Thac%20Sy/App/ThsAutoOrganizer/docs/superpowers/specs/2026-09-22-notebooklm-mcp-integration-design.md)

## Global Constraints
- Tuân thủ nghiêm ngặt bảng màu Obsidian Minimalist Academic: Nền `#111113`, thẻ `#18181B`, viền `rgba(255, 255, 255, 0.08)`, chữ `#F4F4F5`, font `'Inter'` và `'JetBrains Mono'`.
- Toàn bộ thao tác gọi nạp file lên NotebookLM phải chạy ngầm trong ThreadPool, tuyệt đối không gây nghẽn hoặc làm chậm quá trình tải file của người dùng trên Web.
- Tương thích tối đa với môi trường Windows (PowerShell, đường dẫn tệp `Path`, xử lý ký tự tiếng Việt UTF-8 khi chạy CLI).
- Bảo toàn 100% các bài kiểm thử hiện có (không làm hỏng các tính năng đa chuyên ngành, Google Drive sync, đăng nhập OAuth).

## Review Focus
- Khi chưa đăng nhập NotebookLM (`nlm login` chưa chạy hoặc hết hạn session): Hệ thống không được crash mà phải ghi log `status='failed'`, trên Web UI hiển thị badge hướng dẫn chạy lệnh `nlm login`.
- Khi nạp tệp định dạng không được NotebookLM hỗ trợ (ví dụ file `.zip`, `.py`, `.exe`): Hệ thống tự động gán trạng thái `skipped` và không ném lỗi.
- Khi truy vấn qua MCP hoặc Web: Dữ liệu trả về phải bảo toàn cấu trúc trích dẫn Citations (tiêu đề nguồn, số trang/đoạn trích dẫn).
- Đẩy dữ liệu từ AntiGravity Agent vào Web qua API `POST /api/ai/insights` phải xuất hiện ngay lập tức trên Web Dashboard khi tải lại hoặc nhận tín hiệu.
- Đảm bảo toàn bộ test suites mới và cũ đều PASS (Zero regressions).

---

### Task 1: Cấu Hình MCP Server & Workspace Config Cho AntiGravity

**Files:**
- Create: `.agents/mcp_config.json`
- Test: `tests/test_mcp_config.py`

**Interfaces:**
- Consumes: Cấu hình MCP chuẩn của Antigravity (`command`, `args`).
- Produces: File cấu hình `.agents/mcp_config.json` để Antigravity nhận diện MCP Server `notebooklm`.

- [ ] **Step 1: Viết test kiểm tra tính hợp lệ của cấu hình MCP**

Tạo `tests/test_mcp_config.py`:
```python
import json
from pathlib import Path

def test_mcp_config_schema():
    config_file = Path(".agents/mcp_config.json")
    assert config_file.exists(), "File .agents/mcp_config.json phải tồn tại"
    
    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert "mcpServers" in data
    assert "notebooklm" in data["mcpServers"]
    nlm_cfg = data["mcpServers"]["notebooklm"]
    assert "command" in nlm_cfg
    assert "args" in nlm_cfg
    assert nlm_cfg["args"] == ["mcp"]
```

- [ ] **Step 2: Chạy test để xác nhận fail**

Run: `pytest tests/test_mcp_config.py -v`
Expected: FAIL (File `.agents/mcp_config.json` chưa tồn tại)

- [ ] **Step 3: Tạo file cấu hình `.agents/mcp_config.json`**

Tạo file `.agents/mcp_config.json`:
```json
{
  "mcpServers": {
    "notebooklm": {
      "command": "nlm",
      "args": ["mcp"]
    }
  }
}
```

- [ ] **Step 4: Chạy lại test để xác nhận pass**

Run: `pytest tests/test_mcp_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit task 1**

```bash
git add .agents/mcp_config.json tests/test_mcp_config.py; git commit -m "feat(mcp): add notebooklm mcp server configuration"
```

---

### Task 2: Nâng Cấp Schema CSDL SQLite & Phương Thức Quản Lý AI Insights

**Files:**
- Modify: `src/database.py`
- Modify: `tests/test_database.py`

**Interfaces:**
- Consumes: SQLite3 database connection.
- Produces: 
  - `Database.update_course_notebooklm_id(course_id: int, notebooklm_id: str) -> None`
  - `Database.get_course_notebooklm_id(course_id: int) -> Optional[str]`
  - `Database.save_ai_insight(course_id: int, insight_type: str, title: str, content: str, citations: Optional[str] = None, created_by: str = 'agent') -> int`
  - `Database.get_ai_insights(course_id: Optional[int] = None, insight_type: Optional[str] = None, limit: int = 50) -> List[dict]`
  - `Database.delete_ai_insight(insight_id: int) -> bool`
  - `Database.log_notebooklm_sync(course_id: int, file_path: str, notebooklm_id: Optional[str], status: str, file_id: Optional[int] = None, error_message: Optional[str] = None) -> int`
  - `Database.get_notebooklm_sync_logs(limit: int = 50) -> List[dict]`

- [ ] **Step 1: Viết test cho các bảng mới và methods trong `tests/test_database.py`**

Thêm các test cases vào `tests/test_database.py`:
```python
def test_notebooklm_schema_and_methods(tmp_path: Path):
    from src.database import Database
    db = Database(tmp_path / "test_nlm.db")
    db.initialize()
    
    # 1. Test update & get course notebooklm_id
    course_id = db.add_course("Triết học", "TH01", "TRIET", major="Hệ thống thông tin")
    assert db.get_course_notebooklm_id(course_id) is None
    db.update_course_notebooklm_id(course_id, "nlm_nb_12345")
    assert db.get_course_notebooklm_id(course_id) == "nlm_nb_12345"
    
    # 2. Test save & get ai_insights
    insight_id = db.save_ai_insight(
        course_id=course_id,
        insight_type="quiz",
        title="Trắc nghiệm Chương 1",
        content='[{"q": "Q1", "options": ["A", "B"], "ans": "A"}]',
        citations='[{"source": "Giao_trinh.pdf", "page": 12}]',
        created_by="agent"
    )
    assert insight_id > 0
    insights = db.get_ai_insights(course_id=course_id)
    assert len(insights) == 1
    assert insights[0]["title"] == "Trắc nghiệm Chương 1"
    assert insights[0]["insight_type"] == "quiz"
    
    # 3. Test delete insight
    deleted = db.delete_ai_insight(insight_id)
    assert deleted is True
    assert len(db.get_ai_insights(course_id=course_id)) == 0
    
    # 4. Test log sync
    log_id = db.log_notebooklm_sync(
        course_id=course_id,
        file_path="C:/docs/slide1.pdf",
        notebooklm_id="nlm_nb_12345",
        status="synced"
    )
    assert log_id > 0
    logs = db.get_notebooklm_sync_logs()
    assert len(logs) == 1
    assert logs[0]["status"] == "synced"
```

- [ ] **Step 2: Chạy test để xác nhận fail**

Run: `pytest tests/test_database.py::test_notebooklm_schema_and_methods -v`
Expected: FAIL (AttributeError do các method chưa có)

- [ ] **Step 3: Triển khai migration và methods trong `src/database.py`**

Cập nhật `src/database.py`:
1. Trong phương thức `initialize()`:
   - Kiểm tra và thêm cột `notebooklm_id` vào bảng `courses` nếu chưa có (`PRAGMA table_info(courses)`).
   - `CREATE TABLE IF NOT EXISTS ai_insights (...)`.
   - `CREATE TABLE IF NOT EXISTS notebooklm_sync_log (...)`.
2. Bổ sung các phương thức: `update_course_notebooklm_id`, `get_course_notebooklm_id`, `save_ai_insight`, `get_ai_insights`, `delete_ai_insight`, `log_notebooklm_sync`, `get_notebooklm_sync_logs`.

- [ ] **Step 4: Chạy lại test để xác nhận pass**

Run: `pytest tests/test_database.py -v`
Expected: PASS toàn bộ các test cases của database.

- [ ] **Step 5: Commit task 2**

```bash
git add src/database.py tests/test_database.py; git commit -m "feat(db): add notebooklm and ai_insights schema and methods"
```

---

### Task 3: Xây Dựng Module Đồng Bộ Ngầm `src/notebooklm_sync.py`

**Files:**
- Create: `src/notebooklm_sync.py`
- Create: `tests/test_notebooklm_sync.py`

**Interfaces:**
- Consumes: `src.database.Database`, CLI command `nlm`.
- Produces: `NotebookLMSyncManager` với các API:
  - `check_cli_status() -> dict`
  - `ensure_notebook_for_course(course_name: str, course_id: int) -> Optional[str]`
  - `sync_file_to_notebook(file_path: str, course_name: str, course_id: int, file_id: Optional[int] = None) -> bool`
  - `enqueue_sync(file_path: str, course_name: str, course_id: int, file_id: Optional[int] = None) -> None`
  - `query_notebook(notebook_id: str, prompt: str) -> dict`

- [ ] **Step 1: Viết test cho `NotebookLMSyncManager` với mock CLI**

Tạo `tests/test_notebooklm_sync.py`:
```python
from unittest.mock import patch, MagicMock
from pathlib import Path
from src.database import Database
from src.notebooklm_sync import NotebookLMSyncManager

def test_check_cli_status_installed(tmp_path: Path):
    db = Database(tmp_path / "sync_test.db")
    db.initialize()
    manager = NotebookLMSyncManager(database=db, executable="nlm")
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="nlm v0.2.0\n", stderr="")
        status = manager.check_cli_status()
        assert status["installed"] is True
        assert "0.2.0" in status["version"]

def test_ensure_notebook_for_course_existing(tmp_path: Path):
    db = Database(tmp_path / "sync_test.db")
    db.initialize()
    course_id = db.add_course("Triết học", "TH01", "TRIET", major="Hệ thống thông tin")
    db.update_course_notebooklm_id(course_id, "cached_id_999")
    
    manager = NotebookLMSyncManager(database=db)
    nb_id = manager.ensure_notebook_for_course("Triết học", course_id)
    assert nb_id == "cached_id_999"

def test_sync_file_supported_extension(tmp_path: Path):
    db = Database(tmp_path / "sync_test.db")
    db.initialize()
    course_id = db.add_course("Triết học", "TH01", "TRIET", major="Hệ thống thông tin")
    db.update_course_notebooklm_id(course_id, "nb_123")
    
    manager = NotebookLMSyncManager(database=db)
    sample_file = tmp_path / "test_slide.pdf"
    sample_file.write_text("dummy content")
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Source added successfully", stderr="")
        success = manager.sync_file_to_notebook(str(sample_file), "Triết học", course_id)
        assert success is True
        logs = db.get_notebooklm_sync_logs()
        assert len(logs) == 1
        assert logs[0]["status"] == "synced"

def test_sync_file_unsupported_extension_skipped(tmp_path: Path):
    db = Database(tmp_path / "sync_test.db")
    db.initialize()
    course_id = db.add_course("Triết học", "TH01", "TRIET", major="Hệ thống thông tin")
    manager = NotebookLMSyncManager(database=db)
    
    code_file = tmp_path / "main.py"
    code_file.write_text("print('hello')")
    
    success = manager.sync_file_to_notebook(str(code_file), "Triết học", course_id)
    assert success is False
    logs = db.get_notebooklm_sync_logs()
    assert len(logs) == 1
    assert logs[0]["status"] == "skipped"
```

- [ ] **Step 2: Chạy test để xác nhận fail**

Run: `pytest tests/test_notebooklm_sync.py -v`
Expected: FAIL (Module `src.notebooklm_sync` chưa tồn tại)

- [ ] **Step 3: Triển khai `src/notebooklm_sync.py`**

Viết code trong `src/notebooklm_sync.py`:
1. Hằng số `SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.txt', '.md', '.pptx', '.mp3'}`.
2. Quản lý `ThreadPoolExecutor(max_workers=2)` để chạy background sync.
3. Hàm gọi subprocess an toàn, encode UTF-8, timeout bảo vệ.
4. Parsing kết quả CLI `nlm notebook list`, `nlm notebook create`, `nlm source add`, `nlm query`.
5. Tự động lưu log vào `database.log_notebooklm_sync`.

- [ ] **Step 4: Chạy lại test để xác nhận pass**

Run: `pytest tests/test_notebooklm_sync.py -v`
Expected: PASS

- [ ] **Step 5: Commit task 3**

```bash
git add src/notebooklm_sync.py tests/test_notebooklm_sync.py; git commit -m "feat(sync): add NotebookLMSyncManager with CLI runner and background thread"
```

---

### Task 4: Tích Hợp Background Sync Trigger Vào Luồng Nạp Tệp

**Files:**
- Modify: `src/web_server.py`
- Modify: `tests/test_web_server.py`

**Interfaces:**
- Consumes: `NotebookLMSyncManager.enqueue_sync`.
- Produces: Tự động kích hoạt nạp file vào NotebookLM sau khi upload thành công trên Web.

- [ ] **Step 1: Viết test kiểm tra upload file kích hoạt nạp ngầm**

Thêm test vào `tests/test_web_server.py`:
```python
def test_upload_triggers_notebooklm_enqueue(tmp_path: Path):
    from src.database import Database
    from src.notebooklm_sync import NotebookLMSyncManager
    from unittest.mock import MagicMock
    
    db = Database(tmp_path / "up_test.db")
    db.initialize()
    course_id = db.add_course("Triết học", "TH01", "TRIET", major="Hệ thống thông tin")
    
    mock_nlm = MagicMock(spec=NotebookLMSyncManager)
    # Khởi động server với mock nlm_sync
    # Gọi endpoint upload file và kiểm tra mock_nlm.enqueue_sync được gọi đúng file và course_id
```

- [ ] **Step 2: Chạy test để xác nhận fail**

Run: `pytest tests/test_web_server.py::test_upload_triggers_notebooklm_enqueue -v`
Expected: FAIL

- [ ] **Step 3: Cập nhật `src/web_server.py` để inject và trigger sync manager**

Trong `src/web_server.py`:
1. Thêm tham số `nlm_sync_manager: Optional[NotebookLMSyncManager] = None` vào `start_web_server` và `RequestHandler`.
2. Tại luồng xử lý `POST /api/upload`: Sau khi file được lưu và băm SHA-256 thành công, gọi `self.nlm_sync_manager.enqueue_sync(dest_path, course_name, course_id, file_id)`.

- [ ] **Step 4: Chạy lại test để xác nhận pass**

Run: `pytest tests/test_web_server.py -k "test_upload" -v`
Expected: PASS

- [ ] **Step 5: Commit task 4**

```bash
git add src/web_server.py tests/test_web_server.py; git commit -m "feat(upload): wire up automatic NotebookLM background ingestion"
```

---

### Task 5: Triển Khai REST API Endpoints Cho AI Study Hub

**Files:**
- Modify: `src/web_server.py`
- Modify: `tests/test_web_server.py`

**Interfaces:**
- Endpoints:
  - `GET /api/ai/insights`
  - `POST /api/ai/insights`
  - `DELETE /api/ai/insights/<id>`
  - `POST /api/ai/query`
  - `GET /api/notebooklm/status`
  - `POST /api/notebooklm/sync-pending`

- [ ] **Step 1: Viết test cho các endpoints mới**

Thêm các test cases vào `tests/test_web_server.py`:
```python
def test_ai_insights_rest_api(tmp_path: Path):
    # Khởi động test server
    # 1. POST /api/ai/insights (tạo bài quiz mới)
    # 2. GET /api/ai/insights (lấy danh sách, kiểm tra dữ liệu)
    # 3. DELETE /api/ai/insights/<id> (xóa và kiểm tra lại danh sách rỗng)
    # 4. GET /api/notebooklm/status (kiểm tra trả về json status)
```

- [ ] **Step 2: Chạy test để xác nhận fail**

Run: `pytest tests/test_web_server.py::test_ai_insights_rest_api -v`
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Triển khai các route handler trong `src/web_server.py`**

Viết code xử lý request trong `RequestHandler.do_GET` và `RequestHandler.do_POST`:
- Parse JSON body an toàn, validation trường dữ liệu bắt buộc.
- Trả về mã lỗi HTTP và JSON message chuẩn.
- Liên kết với `Database` và `NotebookLMSyncManager`.

- [ ] **Step 4: Chạy lại test để xác nhận pass**

Run: `pytest tests/test_web_server.py::test_ai_insights_rest_api -v`
Expected: PASS

- [ ] **Step 5: Commit task 5**

```bash
git add src/web_server.py tests/test_web_server.py; git commit -m "feat(api): add REST endpoints for AI insights and NotebookLM operations"
```

---

### Task 6: Xây Dựng Giao Diện Tab "🧠 AI Study Hub" Phong Cách Obsidian

**Files:**
- Modify: `src/web_server.py` (HTML Template, CSS Stylesheet, JavaScript App Logic)
- Modify: `tests/test_web_server.py`

**Interfaces:**
- Consumes: Các API `/api/ai/*`, `/api/notebooklm/*`.
- Produces: Tab điều hướng `nav-tab-study-hub`, bộ lọc thể loại, thẻ bài học, Trình làm bài Quiz tương tác, Drawer trích dẫn Citations, ô hỏi đáp nhanh NotebookLM.

- [ ] **Step 1: Viết test kiểm tra các phần tử UI của AI Study Hub có mặt trong HTML**

Thêm test vào `tests/test_web_server.py`:
```python
def test_ai_study_hub_ui_elements(tmp_path: Path):
    from src.database import Database
    from src.web_server import start_web_server
    import urllib.request
    
    db = Database(tmp_path / "ui_test.db")
    db.initialize()
    port = 19124
    server = start_web_server(port=port, database=db, config_path=tmp_path / "cfg.json")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/")
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode("utf-8")
            assert 'id="tab-study-hub"' in html
            assert 'AI Study Hub' in html
            assert 'id="ai-course-filter"' in html
            assert 'id="ai-type-filter"' in html
            assert 'id="quiz-modal"' in html or 'id="quiz-container"' in html
            assert 'id="citations-drawer"' in html or 'class="citations-box"' in html
    finally:
        server.shutdown()
```

- [ ] **Step 2: Chạy test để xác nhận fail**

Run: `pytest tests/test_web_server.py::test_ai_study_hub_ui_elements -v`
Expected: FAIL

- [ ] **Step 3: Bổ sung HTML, CSS và JavaScript cho Tab "🧠 AI Study Hub"**

Trong `src/web_server.py`:
1. **Nav Bar:** Thêm nút chuyển Tab "🧠 AI Study Hub".
2. **Sub-Tab Layout:**
   - Header: Bộ lọc môn học, thẻ loại (`Tất cả`, `Đề cương`, `Quiz trắc nghiệm`, `Tóm tắt`, `Q&A`), Badge trạng thái NotebookLM.
   - Quick Research Box: Input gõ câu hỏi cho môn học đang chọn + nút "Gửi NotebookLM".
   - Cards Grid: Render các thẻ bài học/Quiz/Tóm tắt.
   - Citations Drawer/Collapse: Hiển thị trích dẫn nguồn số trang khi bấm "Xem trích dẫn".
   - Interactive Quiz Player: Cho phép làm câu hỏi trắc nghiệm, bấm chọn đáp án A/B/C/D, chấm điểm và xem giải thích trích dẫn.
3. **CSS:** Tinh chỉnh các card, quiz options, citation badges phong cách Obsidian tối giản cao cấp.
4. **JS Logic:** Xử lý gọi API, render dữ liệu động, làm bài trắc nghiệm, hiển thị citations.

- [ ] **Step 4: Chạy lại test để xác nhận pass**

Run: `pytest tests/test_web_server.py::test_ai_study_hub_ui_elements -v`
Expected: PASS

- [ ] **Step 5: Commit task 6**

```bash
git add src/web_server.py tests/test_web_server.py; git commit -m "feat(ui): implement Obsidian-styled AI Study Hub with Quiz player and citations viewer"
```

---

### Task 7: Kiểm Thử Toàn Bộ Hệ Thống & Viết Hướng Dẫn Kích Hoạt MCP

**Files:**
- Create: `docs/notebooklm_mcp_guide.md`
- Run all test suites

**Interfaces:**
- Consumes: Toàn bộ codebase ThsAutoOrganizer.
- Produces: Toàn bộ test suite pass 100%, tài liệu hướng dẫn người dùng kết nối tài khoản.

- [ ] **Step 1: Chạy toàn bộ test suites của dự án**

Run: `pytest -v`
Expected: PASS 100% tất cả các bài test (cũ và mới).

- [ ] **Step 2: Tạo tài liệu hướng dẫn sử dụng `docs/notebooklm_mcp_guide.md`**

Viết hướng dẫn chi tiết cách:
1. Chạy lệnh cài đặt `pip install notebooklm-mcp-cli` (hoặc qua `uv`).
2. Chạy lệnh `nlm login` để mở trình duyệt đăng nhập Google 1 lần duy nhất.
3. Cú pháp gõ prompt trong AntiGravity Chat để truy vấn NotebookLM và đẩy bài về Web.
4. Cách khai thác giao diện AI Study Hub trên điện thoại và máy tính.

- [ ] **Step 3: Commit task 7**

```bash
git add docs/notebooklm_mcp_guide.md; git commit -m "docs: add comprehensive NotebookLM MCP setup and user guide"
```
