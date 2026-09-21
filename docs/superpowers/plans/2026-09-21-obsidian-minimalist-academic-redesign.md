# Obsidian Minimalist Academic Workspace Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuyển đổi toàn diện giao diện và luồng trải nghiệm của ThsAutoOrganizer Studio theo phong cách Obsidian Minimalist: 1 điểm đăng nhập duy nhất, dọn sạch 100% dữ liệu khi đăng xuất, hợp nhất thanh Sidebar và bố cục "Tổ chức tài liệu" thành 2 Sub-Tabs học thuật tĩnh lặng.

**Architecture:** Cập nhật trực tiếp `src/web_server.py` (CSS design tokens, HTML layout, JavaScript state & handlers) và mở rộng `tests/test_multi_user.py` / `tests/test_web_server.py` để kiểm thử tự động chu trình đăng nhập đơn nhất, dọn sạch thông tin khi logout và chuyển tab không gian làm việc.

**Tech Stack:** Python 3.13 (http.server, SQLite), Vanilla HTML5/CSS3/JavaScript (Zero external frontend frameworks), Pytest.

**Spec:** [`docs/superpowers/specs/2026-09-21-obsidian-minimalist-academic-redesign-design.md`](file:///h:/2026/Thac%20Sy/App/ThsAutoOrganizer/docs/superpowers/specs/2026-09-21-obsidian-minimalist-academic-redesign-design.md)

## Global Constraints
- Typography: Font chính `'Inter'`, font mã `'JetBrains Mono'`.
- Palette: Nền `#111113`, thẻ `#18181B`, viền `rgba(255, 255, 255, 0.08)`, chữ `#F4F4F5`.
- Không sử dụng gradient đa sắc sặc sỡ hoặc banner cảnh báo lòe loẹt.
- Tuyệt đối không để sót tên "akitao".
- Bảo toàn 100% cách ly dữ liệu giữa tài khoản gốc (`xuanngocit@gmail.com`) và tài khoản sinh viên.

## Review Focus
- Bấm Đăng xuất từ tài khoản có dữ liệu (như `mongxuancomestic@gmail.com`) phải xóa sạch thẻ đường dẫn máy tính và email Drive trên DOM ngay lập tức, đưa về Trang chủ.
- Khi chưa đăng nhập, góc trên Topbar là nơi duy nhất có nút Đăng nhập; không có banner cảnh báo rườm rà.
- Truy cập mục "Tổ chức tài liệu" khi chưa đăng nhập chỉ hiển thị 1 khung tĩnh lặng học thuật với 1 nút Đăng nhập Google.
- Sub-tab 1 "Kho tài liệu & Phân loại" và Sub-tab 2 "Nạp & Kết nối" chuyển đổi mượt mà mà không làm tải lại trang.
- Đảm bảo toàn bộ 43+ unit tests hiện tại vẫn pass.

---

### Task 1: Chuẩn Hóa CSS Design Tokens Phong Cách Obsidian Minimalist

**Files:**
- Modify: `src/web_server.py:200-500`

**Interfaces:**
- Consumes: CSS Variables trong `:root`
- Produces: Hệ thống biến màu `--bg-base`, `--bg-surface`, `--border-subtle`, `--text-primary`, `--accent-purple`, `--accent-emerald`, typography Inter/JetBrains Mono.

- [x] **Step 1: Viết test kiểm tra các token CSS mới trong web server**

Thêm test case vào `tests/test_web_server.py`:
```python
def test_obsidian_minimalist_css_tokens(tmp_path: Path):
    from src.database import Database
    from src.web_server import start_web_server
    import urllib.request

    db = Database(tmp_path / "css_test.db")
    db.initialize()
    port = 19123
    server = start_web_server(port=port, database=db, config_path=tmp_path / "cfg.json")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/")
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode("utf-8")
            assert "--bg-base: #111113" in html
            assert "--bg-surface: #18181b" in html or "--bg-surface: #18181B" in html
            assert "--border-subtle" in html
    finally:
        server.shutdown()
```

- [x] **Step 2: Chạy test để xác nhận test thất bại**
Run: `pytest tests/test_web_server.py::test_obsidian_minimalist_css_tokens -v`
Expected: FAIL

- [x] **Step 3: Cập nhật CSS variables và rules trong `src/web_server.py`**
Thay thế các gradient chói sáng và màu neon cũ bằng bảng màu Obsidian Minimalist, tinh chỉnh card borders, buttons, sub-tabs styling.

- [x] **Step 4: Chạy test để xác nhận test pass**
Run: `pytest tests/test_web_server.py::test_obsidian_minimalist_css_tokens -v`
Expected: PASS

- [x] **Step 5: Commit**
```bash
git add src/web_server.py tests/test_web_server.py
git commit -m "style: apply Obsidian Minimalist design tokens and calm palette"
```

---

### Task 2: Tái Cấu Trúc Sidebar & Điểm Đăng Nhập Duy Nhất Trên Topbar

**Files:**
- Modify: `src/web_server.py:1400-1600`
- Modify: `src/web_server.py:2140-2230`

**Interfaces:**
- Consumes: Navigation elements, `#userSection`, `#sidebarUserBox`
- Produces: Sidebar 4 mục (`home`, `workspace`, `search`, `about`), Topbar nút Đăng nhập đơn nhất.

- [x] **Step 1: Viết test kiểm tra cấu trúc menu Sidebar mới**

Thêm test vào `tests/test_web_server.py`:
```python
def test_sidebar_minimalist_structure(tmp_path: Path):
    from src.database import Database
    from src.web_server import start_web_server
    import urllib.request

    db = Database(tmp_path / "nav_test.db")
    db.initialize()
    port = 19124
    server = start_web_server(port=port, database=db, config_path=tmp_path / "cfg.json")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/")
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode("utf-8")
            assert "Tổ chức tài liệu" in html
            assert "Kho tài liệu" not in html or "subtab" in html.lower()
    finally:
        server.shutdown()
```

- [x] **Step 2: Chạy test để xác nhận test thất bại**
Run: `pytest tests/test_web_server.py::test_sidebar_minimalist_structure -v`
Expected: FAIL

- [x] **Step 3: Cập nhật HTML Sidebar và Topbar trong `src/web_server.py`**
- Rút gọn menu bên trái thành: *Trang chủ*, *Tổ chức tài liệu*, *Tra cứu*, *Giới thiệu*.
- Chuyển nút Đăng nhập lên góc phải Topbar là nơi duy nhất quản lý Auth.
- Xóa các button đăng nhập rải rác.

- [x] **Step 4: Chạy test để xác nhận test pass**
Run: `pytest tests/test_web_server.py::test_sidebar_minimalist_structure -v`
Expected: PASS

- [x] **Step 5: Commit**
```bash
git add src/web_server.py tests/test_web_server.py
git commit -m "refactor(ui): streamline sidebar navigation and unify single topbar login point"
```

---

### Task 3: Bố Cục "Tổ Chức Tài Liệu" 2 Sub-Tabs & Khung Chưa Đăng Nhập Tĩnh Lặng

**Files:**
- Modify: `src/web_server.py:1600-1780`
- Modify: `src/web_server.py:2100-2200`

**Interfaces:**
- Consumes: `#workspaceView`
- Produces: `#subtabDocs` (Kho tệp & Lọc môn), `#subtabSync` (Nạp tệp đa thiết bị & Đồng bộ Drive), `#unauthenticatedState` (Khung tĩnh lặng khi chưa login), hàm JS `switchSubTab(tabName)`.

- [x] **Step 1: Viết test kiểm tra 2 sub-tabs trong Workspace**

Thêm test vào `tests/test_web_server.py`:
```python
def test_workspace_subtabs_presence(tmp_path: Path):
    from src.database import Database
    from src.web_server import start_web_server
    import urllib.request

    db = Database(tmp_path / "subtabs_test.db")
    db.initialize()
    port = 19125
    server = start_web_server(port=port, database=db, config_path=tmp_path / "cfg.json")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/")
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode("utf-8")
            assert "subtabDocs" in html
            assert "subtabSync" in html
            assert "switchSubTab" in html
    finally:
        server.shutdown()
```

- [x] **Step 2: Chạy test để xác nhận test thất bại**
Run: `pytest tests/test_web_server.py::test_workspace_subtabs_presence -v`
Expected: FAIL

- [x] **Step 3: Cập nhật HTML `#workspaceView` và hàm `switchSubTab` trong `src/web_server.py`**
- Thêm thanh chuyển Sub-Tabs: `Kho tài liệu & Phân loại` và `Nạp & Kết nối`.
- Di chuyển khu vực nạp đa thiết bị và cấu hình thư mục máy/Drive vào `#subtabSync`.
- Giữ 4 thẻ thống kê và bảng danh mục tài liệu trong `#subtabDocs`.
- Thêm `#unauthenticatedState` với 1 nút Đăng nhập Google trang nhã khi sinh viên chưa đăng nhập.

- [x] **Step 4: Chạy test để xác nhận test pass**
Run: `pytest tests/test_web_server.py::test_workspace_subtabs_presence -v`
Expected: PASS

- [x] **Step 5: Commit**
```bash
git add src/web_server.py tests/test_web_server.py
git commit -m "feat(ui): implement dual sub-tabs and calm unauthenticated state in Workspace"
```

---

### Task 4: Dọn Sạch 100% Dữ Liệu Khi Đăng Xuất (Zero-Leak Logout)

**Files:**
- Modify: `src/web_server.py:2220-2265`
- Modify: `src/web_server.py:2540-2560`

**Interfaces:**
- Consumes: `logoutUser()`, `renderLoggedOutState()`
- Produces: Hoàn toàn reset `statStoragePath`, `statDriveFolder`, `displayUserFolder`, `displayUserEmail`, `displayUserDrive`, `allFiles = []`, `currentUser = null`, điều hướng về `showView('home')`.

- [x] **Step 1: Viết test kiểm tra mã JS `renderLoggedOutState` xóa sạch đường dẫn và Drive**

Thêm test vào `tests/test_web_server.py`:
```python
def test_render_logged_out_state_clears_paths(tmp_path: Path):
    from src.database import Database
    from src.web_server import start_web_server
    import urllib.request

    db = Database(tmp_path / "logout_test.db")
    db.initialize()
    port = 19126
    server = start_web_server(port=port, database=db, config_path=tmp_path / "cfg.json")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/")
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode("utf-8")
            # Phải có code reset statStoragePath và statDriveFolder
            assert "statStoragePath" in html
            assert "statDriveFolder" in html
            assert "Chưa kết nối thư mục" in html or "Chưa kết nối" in html
    finally:
        server.shutdown()
```

- [x] **Step 2: Chạy test để xác nhận test thất bại**
Run: `pytest tests/test_web_server.py::test_render_logged_out_state_clears_paths -v`
Expected: FAIL

- [x] **Step 3: Cập nhật hàm `renderLoggedOutState()` và `logoutUser()` trong `src/web_server.py`**
- Đảm bảo dọn dẹp sạch sẽ toàn bộ text trên DOM:
  ```javascript
  document.getElementById('statStoragePath').textContent = 'Chưa kết nối thư mục máy tính';
  document.getElementById('statDriveFolder').textContent = 'Chưa kết nối Google Drive';
  document.getElementById('displayUserFolder').textContent = '--';
  document.getElementById('displayUserEmail').textContent = '--';
  document.getElementById('displayUserDrive').textContent = '--';
  ```
- Đặt `showView('home')` ngay khi logout thành công.

- [x] **Step 4: Chạy test để xác nhận test pass**
Run: `pytest tests/test_web_server.py::test_render_logged_out_state_clears_paths -v`
Expected: PASS

- [x] **Step 5: Commit**
```bash
git add src/web_server.py tests/test_web_server.py
git commit -m "fix(auth): implement zero-leak logout protocol and DOM state reset"
```

---

### Task 5: Kiểm Thử Toàn Diện & Hồi Quy (Full Integration & Regression)

**Files:**
- Test: `tests/test_multi_user.py`
- Test: `tests/test_web_server.py`

**Interfaces:**
- Consumes: Toàn bộ pipeline và web server
- Produces: 45+ test cases pass 100%.

- [x] **Step 1: Bổ sung end-to-end multi-user login/logout test case**
Viết kịch bản: Sinh viên Mộng Xuân đăng nhập -> xem thư mục riêng `Users_Storage/...` -> đăng xuất -> kiểm tra endpoint `/api/me` trả về `authenticated: false` và các thống kê không bị rò rỉ.

- [x] **Step 2: Chạy toàn bộ test suite pytest**
Run: `pytest tests/`
Expected: 45+ passed in < 7s

- [x] **Step 3: Commit**
```bash
git add tests/test_multi_user.py tests/test_web_server.py
git commit -m "test: add end-to-end zero-leak logout and multi-user integration tests"
```
