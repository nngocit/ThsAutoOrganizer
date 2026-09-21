# Multi-Major Academic Workspace, Admin Management & Upload Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuyển đổi ThsAutoOrganizer thành nền tảng quản lý tài liệu đa chuyên ngành Thạc sĩ (14 chuyên ngành chuẩn), bổ sung phân hệ Quản trị Admin, luồng Onboarding chọn ngành cho sinh viên, khóa bảo mật tuyệt đối tính năng nạp tệp và bộ phân loại AI động tuân thủ cấu trúc 4 thư mục con bất biến.

**Architecture:** Mở rộng SQLite (`majors`, `subjects`, `users.major_id`), bổ sung các API quản trị Admin và chọn ngành sinh viên trong `src/web_server.py`, cập nhật `src/classifier.py` / `src/processor.py` để phân loại động theo chuyên ngành của từng tài khoản, và tinh chỉnh giao diện Obsidian Minimalist (Modal Onboarding, Admin view, Lock card bảo vệ nạp tệp, Home demo đa ngành).

**Tech Stack:** Python 3.13 (http.server, SQLite), Vanilla HTML5/CSS3/JavaScript (Zero external frontend frameworks), Pytest.

**Spec:** [`docs/superpowers/specs/2026-09-21-multi-major-admin-onboarding-design.md`](file:///h:/2026/Thac%20Sy/App/ThsAutoOrganizer/docs/superpowers/specs/2026-09-21-multi-major-admin-onboarding-design.md)

## Global Constraints
- Typography: Font chính `'Inter'`, font mã & metadata `'JetBrains Mono'`.
- Palette: Nền `#111113`, thẻ `#18181B`, viền `rgba(255, 255, 255, 0.08)`, màu nhấn `--accent-purple: #7C3AED` và `--accent-emerald: #10B981`.
- Cấu trúc 4 thư mục con bất biến cho mọi môn học: `01_Giao_Trinh`, `02_Slide`, `03_Tai_Lieu_Tham_Khao`, `04_On_Thi`.
- Phân quyền Admin: Duy nhất `xuanngocit@gmail.com` (hoặc `root_account_email` trong `config.json`) có quyền truy cập trang quản trị và các API admin.
- Tuyệt đối không để sót tên "akitao".
- Bảo toàn 100% cách ly dữ liệu giữa các sinh viên và giữa sinh viên với Admin.

## Review Focus
1. Sinh viên mới đăng nhập (`major_id IS NULL`) phải tự động kích hoạt Modal Onboarding và không thể truy cập Workspace cho đến khi hoàn tất chọn chuyên ngành.
2. Sinh viên thông thường (không phải `xuanngocit@gmail.com`) khi gọi các endpoint `/api/admin/*` phải nhận ngay HTTP 403 Forbidden.
3. Khi sinh viên nạp tệp qua `/api/upload` mà chưa đăng nhập (không có cookie `ths_session`), hệ thống phải từ chối ngay với HTTP 401 Unauthorized và không lưu file rác.
4. Mọi thư mục chuyên ngành và môn học được tạo ra (dù do Admin cấu hình hay do sinh viên chọn) đều phải tự động sinh đủ 4 thư mục con `01_...` đến `04_...`.
5. Đảm bảo toàn bộ 48 unit tests hiện có tiếp tục PASS 100% không bị hồi quy.

---

### Task 1: Mô Hình Dữ Liệu SQLite cho Chuyên Ngành & Môn Học

**Files:**
- Modify: `src/database.py:55-120`
- Modify: `src/database.py:350-450`
- Test: `tests/test_database.py`

**Interfaces:**
- Consumes: SQLite Database
- Produces:
  - Bảng `majors` (14 chuyên ngành chuẩn)
  - Bảng `subjects` (liên kết `major_id`)
  - Cột `users.major_id`
  - Các hàm DB: `get_all_majors()`, `get_major_by_id(major_id)`, `get_subjects_by_major(major_id)`, `add_major(...)`, `add_subject(...)`, `set_user_major(email, major_id)`.

- [ ] **Step 1: Viết test kiểm tra schema bảng `majors` và `subjects` cùng dữ liệu 14 chuyên ngành mẫu**

Thêm test case vào `tests/test_database.py`:
```python
def test_majors_and_subjects_schema_and_seed(tmp_path: Path):
    from src.database import Database
    db = Database(tmp_path / "majors_test.db")
    db.initialize()

    majors = db.get_all_majors()
    assert len(majors) == 14
    major_names = [m["name"] for m in majors]
    assert "Hệ thống thông tin" in major_names
    assert "Quản trị kinh doanh" in major_names
    assert "Luật kinh tế" in major_names

    # Kiểm tra môn học mẫu của ngành Hệ thống thông tin
    httt = next(m for m in majors if m["code"] == "HTTT")
    subjects = db.get_subjects_by_major(httt["id"])
    assert len(subjects) >= 2
    sub_names = [s["name"] for s in subjects]
    assert "Cơ sở dữ liệu" in sub_names

    # Kiểm tra liên kết major_id trong users
    user = db.get_or_create_user("student@univ.edu", "Sinh Viên")
    assert user.get("major_id") is None
    db.set_user_major("student@univ.edu", httt["id"])
    updated_user = db.get_user_by_email("student@univ.edu")
    assert updated_user["major_id"] == httt["id"]
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**
Run: `pytest tests/test_database.py::test_majors_and_subjects_schema_and_seed -v`
Expected: FAIL (AttributeError: 'Database' object has no attribute 'get_all_majors')

- [ ] **Step 3: Cập nhật `src/database.py`**
- Thêm `CREATE TABLE IF NOT EXISTS majors` và `CREATE TABLE IF NOT EXISTS subjects`.
- Thêm cột `major_id INTEGER REFERENCES majors(id)` trong `users` (dùng `PRAGMA table_info(users)` để tự động `ALTER TABLE` nếu bảng đã tồn tại).
- Tạo hàm `_seed_default_majors_and_subjects()` khởi tạo 14 chuyên ngành chuẩn và môn học mẫu kèm từ khóa.
- Triển khai các phương thức truy vấn và cập nhật `majors`, `subjects`, `set_user_major`.

- [ ] **Step 4: Chạy test để xác nhận test pass**
Run: `pytest tests/test_database.py::test_majors_and_subjects_schema_and_seed -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add src/database.py tests/test_database.py
git commit -m "feat(db): add majors and subjects schema with 14 seed academic disciplines"
```

---

### Task 2: API Quản Trị Admin & Phân Quyền Kiểm Soát Truy Cập

**Files:**
- Modify: `src/web_server.py:2770-2820` (GET handlers)
- Modify: `src/web_server.py:3070-3120` (POST handlers)
- Test: `tests/test_web_server.py`

**Interfaces:**
- Consumes: `DashboardRequestHandler`, `Database.get_all_majors`, `Database.add_major`, `Database.add_subject`
- Produces:
  - `GET /api/majors` (Public)
  - `GET /api/majors/<id>/subjects` (Logged In)
  - `GET /api/admin/majors` (Admin Only: 403 nếu không phải `xuanngocit@gmail.com`)
  - `POST /api/admin/majors` (Admin Only)
  - `POST /api/admin/subjects` (Admin Only)

- [ ] **Step 1: Viết test kiểm tra phân quyền Admin API**

Thêm test vào `tests/test_web_server.py`:
```python
def test_admin_majors_api_access_control(tmp_path: Path):
    from src.database import Database
    from src.web_server import start_web_server
    import urllib.request
    import json

    db = Database(tmp_path / "admin_test.db")
    db.initialize()
    cfg_path = tmp_path / "cfg.json"
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"root_account_email": "xuanngocit@gmail.com", "root_folder": str(tmp_path)}, f)

    port = 19201
    server = start_web_server(port=port, database=db, config_path=cfg_path)
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. Sinh viên thường đăng nhập
        login_student = json.dumps({"email": "student@gmail.com", "name": "Sinh Viên"}).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/auth/test-login", data=login_student, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            student_cookie = resp.headers.get("Set-Cookie")

        # Sinh viên gọi API Admin -> Bị chặn 403
        req_admin = urllib.request.Request(f"{base_url}/api/admin/majors", headers={"Cookie": student_cookie})
        try:
            urllib.request.urlopen(req_admin)
            assert False, "Sinh viên thường không được phép truy cập API admin"
        except urllib.error.HTTPError as e:
            assert e.code == 403

        # 2. Admin đăng nhập
        login_admin = json.dumps({"email": "xuanngocit@gmail.com", "name": "Admin"}).encode("utf-8")
        req_adm_login = urllib.request.Request(f"{base_url}/auth/test-login", data=login_admin, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req_adm_login) as resp:
            admin_cookie = resp.headers.get("Set-Cookie")

        # Admin gọi API Admin -> Thành công 200
        req_admin_ok = urllib.request.Request(f"{base_url}/api/admin/majors", headers={"Cookie": admin_cookie})
        with urllib.request.urlopen(req_admin_ok) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert len(data.get("majors", [])) == 14
    finally:
        server.shutdown()
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**
Run: `pytest tests/test_web_server.py::test_admin_majors_api_access_control -v`
Expected: FAIL (404 Not Found hoặc không có endpoint)

- [ ] **Step 3: Triển khai các API quản trị và kiểm tra quyền Admin trong `src/web_server.py`**
- Thêm hàm `_is_admin(current_user)` kiểm tra email có khớp `root_account_email` (`xuanngocit@gmail.com`).
- Xử lý `GET /api/majors`, `GET /api/majors/<id>/subjects`.
- Xử lý `GET /api/admin/majors`, `POST /api/admin/majors`, `POST /api/admin/subjects` (nếu không phải Admin trả về HTTP 403).

- [ ] **Step 4: Chạy test để xác nhận test pass**
Run: `pytest tests/test_web_server.py::test_admin_majors_api_access_control -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add src/web_server.py tests/test_web_server.py
git commit -m "feat(api): implement admin major management endpoints with strict authorization"
```

---

### Task 3: Luồng Onboarding Sinh Viên & Khởi Tạo Thư Mục Chuẩn 4 Cấp Con

**Files:**
- Modify: `src/web_server.py:1750-1850` (HTML Onboarding Modal)
- Modify: `src/web_server.py:2550-2650` (JS check onboarding & select major)
- Modify: `src/web_server.py:3100-3160` (POST `/api/user/select-major`)
- Test: `tests/test_multi_user.py`

**Interfaces:**
- Consumes: `POST /api/user/select-major`, `Database.set_user_major`
- Produces:
  - Sinh viên chọn ngành -> Tạo cấu trúc thư mục trên máy tính `{User_Storage}/{user}/{Major}/{Subject}/{01_Giao_Trinh | 02_Slide | 03_Tai_Lieu_Tham_Khao | 04_On_Thi}`.
  - Trả về thông tin chuyên ngành đã chọn cho client.

- [ ] **Step 1: Viết test kiểm tra luồng chọn ngành và tự động sinh 4 thư mục con**

Thêm test vào `tests/test_multi_user.py`:
```python
def test_student_select_major_and_folder_provisioning(tmp_path: Path):
    from src.database import Database
    from src.web_server import start_web_server
    import urllib.request
    import json

    db = Database(tmp_path / "onboard_test.db")
    db.initialize()
    root_folder = tmp_path / "Mon_Hoc"
    root_folder.mkdir(parents=True, exist_ok=True)
    cfg_path = tmp_path / "cfg.json"
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"root_folder": str(root_folder), "root_account_email": "xuanngocit@gmail.com"}, f)

    port = 19202
    server = start_web_server(port=port, database=db, config_path=cfg_path)
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. Sinh viên đăng nhập lần đầu
        login_payload = json.dumps({"email": "lan_anh@univ.edu", "name": "Lan Anh"}).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/auth/test-login", data=login_payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            cookie = resp.headers.get("Set-Cookie")

        # 2. Sinh viên gửi yêu cầu chọn chuyên ngành Quản trị kinh doanh
        majors = db.get_all_majors()
        qtkd = next(m for m in majors if m["code"] == "QTKD")
        select_payload = json.dumps({"major_id": qtkd["id"]}).encode("utf-8")
        req_select = urllib.request.Request(f"{base_url}/api/user/select-major", data=select_payload, headers={"Content-Type": "application/json", "Cookie": cookie}, method="POST")
        with urllib.request.urlopen(req_select) as resp:
            assert resp.status == 200
            res_data = json.loads(resp.read().decode("utf-8"))
            assert res_data["ok"] is True
            assert res_data["major"]["code"] == "QTKD"

        # 3. Xác minh cấu trúc thư mục 4 cấp con được sinh tự động trên ổ đĩa
        user_storage = root_folder.parent / "Users_Storage" / "lan_anh_at_univ_edu"
        major_dir = user_storage / qtkd["folder_name"]
        assert major_dir.exists()

        # Kiểm tra ít nhất 1 môn học của ngành có đủ 4 thư mục con
        subjects = list(major_dir.iterdir())
        assert len(subjects) > 0
        first_sub = subjects[0]
        assert (first_sub / "01_Giao_Trinh").exists()
        assert (first_sub / "02_Slide").exists()
        assert (first_sub / "03_Tai_Lieu_Tham_Khao").exists()
        assert (first_sub / "04_On_Thi").exists()
    finally:
        server.shutdown()
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**
Run: `pytest tests/test_multi_user.py::test_student_select_major_and_folder_provisioning -v`
Expected: FAIL (404 Not Found endpoint `/api/user/select-major`)

- [ ] **Step 3: Triển khai endpoint `/api/user/select-major` và Modal Onboarding trong `src/web_server.py`**
- Thêm handler `POST /api/user/select-major`: Nhận `major_id`, cập nhật database, lấy danh sách môn học của ngành đó và tự động `mkdir(parents=True, exist_ok=True)` 4 thư mục con chuẩn (`01_Giao_Trinh`, `02_Slide`, `03_Tai_Lieu_Tham_Khao`, `04_On_Thi`) cho từng môn.
- Thêm HTML `#onboardingModal` với giao diện Obsidian: Tiêu đề trang nhã, ô tìm kiếm nhanh và danh sách 14 thẻ chuyên ngành.
- Trong JS `checkCurrentUser()`: Nếu `currentUser && !currentUser.major_id`, tự động gọi `openOnboardingModal()`.

- [ ] **Step 4: Chạy test để xác nhận test pass**
Run: `pytest tests/test_multi_user.py::test_student_select_major_and_folder_provisioning -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add src/web_server.py tests/test_multi_user.py
git commit -m "feat(onboarding): implement student major selection with automatic 4-subfolder provisioning"
```

---

### Task 4: Khóa Bảo Mật Tuyệt Đối Tính Năng "⚡ Nạp & Kết Nối"

**Files:**
- Modify: `src/web_server.py:1700-1740` (UI `#syncLockCard`)
- Modify: `src/web_server.py:3080-3120` (API `/api/upload` 401 check)
- Test: `tests/test_web_server.py`

**Interfaces:**
- Consumes: `DashboardRequestHandler.do_POST`
- Produces:
  - Khóa hiển thị Lock Card tại `#subtabSync` khi chưa đăng nhập.
  - Từ chối upload với HTTP 401 khi không có session cookie.

- [ ] **Step 1: Viết test kiểm tra bảo mật upload bắt buộc đăng nhập**

Thêm test vào `tests/test_web_server.py`:
```python
def test_upload_strictly_requires_auth(tmp_path: Path):
    from src.database import Database
    from src.web_server import start_web_server
    import urllib.request
    import json

    db = Database(tmp_path / "upload_sec.db")
    db.initialize()
    cfg_path = tmp_path / "cfg.json"
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"root_folder": str(tmp_path / "Mon_Hoc")}, f)

    port = 19203
    server = start_web_server(port=port, database=db, config_path=cfg_path)
    base_url = f"http://127.0.0.1:{port}"

    try:
        # Gửi request upload không có cookie phiên làm việc
        upload_payload = json.dumps({
            "filename": "Slide_BaiGiang.pdf",
            "content_base64": "JVBERi0xLjQK..."
        }).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/api/upload", data=upload_payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req)
            assert False, "Upload không có xác thực phải bị từ chối"
        except urllib.error.HTTPError as e:
            assert e.code == 401
            resp_body = json.loads(e.read().decode("utf-8"))
            assert resp_body["ok"] is False
            assert "đăng nhập" in resp_body["error"].lower()

        # Kiểm tra HTML trang web có Lock Card bảo vệ
        req_page = urllib.request.Request(f"{base_url}/")
        with urllib.request.urlopen(req_page) as page_resp:
            html = page_resp.read().decode("utf-8")
            assert "syncLockCard" in html
            assert "Tính năng yêu cầu định danh tài khoản" in html
    finally:
        server.shutdown()
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**
Run: `pytest tests/test_web_server.py::test_upload_strictly_requires_auth -v`
Expected: FAIL

- [ ] **Step 3: Cập nhật giao diện Lock Card và kiểm tra session trong `src/web_server.py`**
- Cập nhật `#subtabSync`:
  - Thêm thẻ khóa bảo vệ `#syncLockCard` (hiển thị mặc định khi chưa login).
  - Khối nút nạp file `#syncUploadButtons` chỉ hiển thị khi `currentUser !== null`.
- Trong `do_POST` `/api/upload`: Đảm bảo kiểm tra `if not current_user` trả về mã 401 rõ ràng.

- [ ] **Step 4: Chạy test để xác nhận test pass**
Run: `pytest tests/test_web_server.py::test_upload_strictly_requires_auth -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add src/web_server.py tests/test_web_server.py
git commit -m "fix(security): enforce strict authentication for multi-device upload and add calm UI lock card"
```

---

### Task 5: Bộ Phân Loại AI Động Theo Chuyên Ngành & Trang Chủ Đa Ngành

**Files:**
- Modify: `src/classifier.py:75-140`
- Modify: `src/processor.py:120-180`
- Modify: `src/web_server.py:1460-1510` (Home page multi-major tester)
- Test: `tests/test_classifier.py`

**Interfaces:**
- Consumes: `PathClassifier`, `majors`, `subjects`
- Produces:
  - `PathClassifier.classify_for_major(file_path, major_subjects_map)`
  - Dropdown chọn ngành và các chip thử nghiệm đa dạng trên Trang chủ.

- [ ] **Step 1: Viết test kiểm tra phân loại động theo chuyên ngành**

Thêm test vào `tests/test_classifier.py`:
```python
def test_dynamic_classifier_by_major():
    from src.classifier import PathClassifier

    classifier = PathClassifier(root_folder="H:/2026/Thac Sy/Users_Storage/lan_anh")

    # Bản đồ môn học của ngành Quản trị kinh doanh
    qtkd_subject_map = {
        "Marketing_Quoc_Te": "Marketing quốc tế",
        "Quan_Tri_Chien_Luoc": "Quản trị chiến lược",
    }

    # Đường dẫn file của sinh viên QTKD
    path_slide = Path("H:/2026/Thac Sy/Users_Storage/lan_anh/Quan_Tri_Kinh_Doanh/Marketing_Quoc_Te/02_Slide/Slide_Chuong1.pdf")
    res = classifier.classify(path_slide, root_folder="H:/2026/Thac Sy/Users_Storage/lan_anh/Quan_Tri_Kinh_Doanh", subject_map=qtkd_subject_map)
    assert res.subject == "Marketing quốc tế"
    assert res.document_type == "Slide"
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**
Run: `pytest tests/test_classifier.py::test_dynamic_classifier_by_major -v`
Expected: FAIL (nếu hàm chưa hỗ trợ truyền `subject_map` tùy biến hoặc lỗi đường dẫn)

- [ ] **Step 3: Cập nhật `src/classifier.py`, `src/processor.py` và Trang chủ trong `src/web_server.py`**
- Hỗ trợ truyền `subject_map` linh hoạt trong `PathClassifier.classify()`.
- Trong `processor.py`: Trích xuất môn học theo danh mục môn của `major_id` người dùng khi phân loại dự phòng.
- Trong `src/web_server.py` (Trang chủ `#sectionTester`):
  - Xóa bỏ câu chữ fix cứng cho 1 môn.
  - Thêm dropdown chọn Chuyên ngành mẫu (QTKD, HTTT, Luật kinh tế, Toán học, Quản lý giáo dục).
  - Cập nhật các chip gợi ý đại diện cho nhiều ngành.

- [ ] **Step 4: Chạy test để xác nhận test pass**
Run: `pytest tests/test_classifier.py::test_dynamic_classifier_by_major -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add src/classifier.py src/processor.py src/web_server.py tests/test_classifier.py
git commit -m "feat(classifier): support dynamic academic subject mapping and generalize home page tester"
```

---

### Task 6: Giao Diện Quản Trị Admin (`#adminView`) & Kiểm Thử Hồi Quy Toàn Diện

**Files:**
- Modify: `src/web_server.py:1550-1650` (Sidebar Admin menu item)
- Modify: `src/web_server.py:1850-1950` (HTML `#adminView`)
- Modify: `src/web_server.py:2650-2750` (JS Admin logic)
- Test: Toàn bộ suite `tests/`

**Interfaces:**
- Consumes: `/api/admin/majors`, `/api/admin/subjects`
- Produces: Giao diện quản trị phong cách Obsidian Zinc, kiểm thử toàn bộ hệ thống đạt 100%.

- [ ] **Step 1: Viết test kiểm tra hiển thị menu Admin chỉ cho tài khoản Admin**

Thêm test vào `tests/test_web_server.py`:
```python
def test_admin_sidebar_item_visibility(tmp_path: Path):
    from src.database import Database
    from src.web_server import start_web_server
    import urllib.request
    import json

    db = Database(tmp_path / "admin_view_test.db")
    db.initialize()
    cfg_path = tmp_path / "cfg.json"
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"root_account_email": "xuanngocit@gmail.com", "root_folder": str(tmp_path)}, f)

    port = 19204
    server = start_web_server(port=port, database=db, config_path=cfg_path)
    base_url = f"http://127.0.0.1:{port}"

    try:
        # Sinh viên đăng nhập -> /api/me trả về is_admin: False
        login_student = json.dumps({"email": "student@gmail.com", "name": "SV"}).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/auth/test-login", data=login_student, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            cookie_sv = resp.headers.get("Set-Cookie")
        req_me_sv = urllib.request.Request(f"{base_url}/api/me", headers={"Cookie": cookie_sv})
        with urllib.request.urlopen(req_me_sv) as resp:
            data_sv = json.loads(resp.read().decode("utf-8"))
            assert data_sv.get("is_admin") is False

        # Admin đăng nhập -> /api/me trả về is_admin: True
        login_adm = json.dumps({"email": "xuanngocit@gmail.com", "name": "Admin"}).encode("utf-8")
        req_adm = urllib.request.Request(f"{base_url}/auth/test-login", data=login_adm, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req_adm) as resp:
            cookie_adm = resp.headers.get("Set-Cookie")
        req_me_adm = urllib.request.Request(f"{base_url}/api/me", headers={"Cookie": cookie_adm})
        with urllib.request.urlopen(req_me_adm) as resp:
            data_adm = json.loads(resp.read().decode("utf-8"))
            assert data_adm.get("is_admin") is True
    finally:
        server.shutdown()
```

- [ ] **Step 2: Chạy test để xác nhận test thất bại**
Run: `pytest tests/test_web_server.py::test_admin_sidebar_item_visibility -v`
Expected: FAIL

- [ ] **Step 3: Triển khai Giao diện `#adminView` và cập nhật `/api/me` `is_admin`**
- Trong `/api/me`: Bổ sung trường `"is_admin": is_admin_user(current_user)`.
- Trong Sidebar HTML: Thêm mục `#navItemAdmin` (mặc định `display: none`, chỉ hiển thị khi `data.is_admin === true`).
- Thêm HTML `#adminView`: 2 cột Obsidian Zinc hiển thị danh sách Chuyên ngành (trái) và Môn học (phải) kèm form thêm môn/ngành.
- Viết JS gọi `/api/admin/majors` và `/api/admin/subjects`.

- [ ] **Step 4: Chạy toàn bộ test suite pytest**
Run: `pytest tests/`
Expected: Tất cả 54+ tests PASSED trong < 10s.

- [ ] **Step 5: Commit**
```bash
git add src/web_server.py tests/test_web_server.py
git commit -m "feat(admin): implement admin management view and finalize multi-major test suite"
```
