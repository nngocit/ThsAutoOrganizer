"""Unit tests cho web_server.py."""

import json
from pathlib import Path
import urllib.request
import pytest

from src.database import Database
from src.web_server import start_web_server


@pytest.fixture
def web_test_env(tmp_path: Path):
    db_path = tmp_path / "web_test.db"
    database = Database(db_path=db_path)
    database.initialize()

    # Thêm bản ghi mẫu
    database.insert_record(
        sha256="test_hash_123",
        path="Toan_Khoa_Hoc_Du_Lieu/01_Giao_Trinh/Book.pdf",
        subject="Toán khoa học dữ liệu",
        document_type="Giáo trình",
        status="UPLOADED",
        drive_file_id="drive_sample_id",
    )

    cfg_path = tmp_path / "test_config.json"
    cfg_data = {
        "root_folder": str(tmp_path / "Mon_Hoc"),
        "stable_file_wait_seconds": 3,
        "supported_extensions": [".pdf", ".docx", ".pptx", ".jpg"],
    }
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg_data, f)

    scan_called = []

    def mock_scan():
        scan_called.append(True)
        return 5

    # Chọn port ngẫu nhiên trong khoảng 18000-18999 để không bị xung đột
    import random
    port = random.randint(18000, 18999)

    server = start_web_server(
        port=port,
        database=database,
        drive_manager=None,
        config_path=cfg_path,
        scan_callback=mock_scan,
    )

    base_url = f"http://127.0.0.1:{port}"
    yield base_url, database, scan_called

    server.shutdown()


def test_web_dashboard_html(web_test_env):
    base_url, _, _ = web_test_env
    req = urllib.request.Request(f"{base_url}/")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "ThsAutoOrganizer" in html
        assert "Studio Edition" in html


def test_api_stats(web_test_env):
    base_url, _, _ = web_test_env
    req = urllib.request.Request(f"{base_url}/api/stats")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["total_files"] == 1
        assert data["uploaded_files"] == 1
        assert "Toán khoa học dữ liệu" in data["subjects"]


def test_api_files(web_test_env):
    base_url, _, _ = web_test_env
    req = urllib.request.Request(f"{base_url}/api/files")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        files = json.loads(resp.read().decode("utf-8"))
        assert len(files) == 1
        assert files[0]["sha256"] == "test_hash_123"


def test_api_manual_update_classification(web_test_env):
    base_url, database, _ = web_test_env
    records = database.get_all_records()
    rec_id = records[0]["id"]

    payload = json.dumps({
        "id": rec_id,
        "subject": "Triết học",
        "document_type": "Ôn thi"
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/api/files/update",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        res = json.loads(resp.read().decode("utf-8"))
        assert res["ok"] is True

    # Kiểm tra database đã được sửa tay
    updated = database.get_record(rec_id)
    assert updated["subject"] == "Triết học"
    assert updated["document_type"] == "Ôn thi"


def test_api_scan_trigger(web_test_env):
    base_url, _, scan_called = web_test_env
    req = urllib.request.Request(
        f"{base_url}/api/scan",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        res = json.loads(resp.read().decode("utf-8"))
        assert res["ok"] is True
        assert res["count"] == 5
        assert len(scan_called) == 1


def test_obsidian_minimalist_css_tokens(web_test_env):
    base_url, _, _ = web_test_env
    req = urllib.request.Request(f"{base_url}/")
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")
        assert "--bg-base: #111113" in html
        assert "--bg-surface: #18181b" in html.lower()
        assert "--border-subtle" in html


def test_sidebar_minimalist_structure(web_test_env):
    base_url, _, _ = web_test_env
    req = urllib.request.Request(f"{base_url}/")
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")
        assert "Tổ chức tài liệu" in html
        assert "onclick=\"showView('workspace')\"" in html
        assert "onclick=\"showView('upload')\"" not in html
        assert "onclick=\"showView('drive')\"" not in html


def test_workspace_subtabs_presence(web_test_env):
    base_url, _, _ = web_test_env
    req = urllib.request.Request(f"{base_url}/")
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")
        assert "subtabDocs" in html
        assert "subtabSync" in html
        assert "switchSubTab" in html
        assert "unauthenticatedState" in html


def test_render_logged_out_state_clears_paths(web_test_env):
    base_url, _, _ = web_test_env
    req = urllib.request.Request(f"{base_url}/")
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")
        assert "statStoragePath" in html
        assert "statDriveFolder" in html
        assert "document.getElementById('statStoragePath').textContent = 'Chưa kết nối thư mục';" in html
        assert "document.getElementById('statDriveFolder').textContent = 'Chưa kết nối Google Drive';" in html


def test_admin_majors_api_access_control(tmp_path: Path):
    from src.database import Database
    from src.web_server import start_web_server
    import urllib.request
    import urllib.error
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

        # Đăng nhập và upload ảnh từ điện thoại mà không cần gửi subject/document_type
        login_req = urllib.request.Request(
            f"{base_url}/auth/test-login",
            data=json.dumps({"email": "mobile_user@univ.edu", "name": "Mobile User"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(login_req) as login_resp:
            cookie = login_resp.headers.get("Set-Cookie").split(";")[0]

        import base64
        fake_img = base64.b64encode(b"fake image bytes").decode("utf-8")
        upload_img_payload = json.dumps({
            "filename": "IMG_Slide_Triet_Hoc_01.jpg",
            "content_base64": fake_img
        }).encode("utf-8")
        up_req = urllib.request.Request(
            f"{base_url}/api/upload",
            data=upload_img_payload,
            headers={"Content-Type": "application/json", "Cookie": cookie},
            method="POST"
        )
        with urllib.request.urlopen(up_req) as up_resp:
            up_data = json.loads(up_resp.read().decode("utf-8"))
            assert up_data["ok"] is True
            assert up_data["subject"] == "Triết học"
            assert up_data["document_type"] == "Slide"
    finally:
        server.shutdown()


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

        # Kiểm tra trang chủ chứa menu admin navItemAdmin và adminView
        req_page = urllib.request.Request(f"{base_url}/")
        with urllib.request.urlopen(req_page) as page_resp:
            html = page_resp.read().decode("utf-8")
            assert "navItemAdmin" in html
            assert "adminView" in html
    finally:
        server.shutdown()


def test_logout_comprehensive_cleanup_and_empty_demo_state(web_test_env):
    base_url, _, _ = web_test_env
    req = urllib.request.Request(f"{base_url}/")
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")

        # 1. Khung Demo Trang chu phai sach se, khong duoc fix cung ten file hay mo the ket qua san
        assert 'value="BaiGiang_Toan_Khoa_Hoc_Du_Lieu_Chuong1.pdf"' not in html
        assert 'id="testerResultCard" class="tester-result-box" style="display: none;"' in html
        assert 'Sandbox' in html or 'Trải Nghiệm Thử AI' in html

        # 2. Ham renderLoggedOutState phai don dep sach se moi form, input va the demo
        assert "document.getElementById('demoInputFile').value = '';" in html
        assert "document.getElementById('testerResultCard').style.display = 'none';" in html
        assert "document.getElementById('settingsUserEmail').textContent = '';" in html
        assert "document.getElementById('cfgRootFolder').value = '';" in html
        assert "document.getElementById('inputUserFolder').value = '';" in html
        assert "document.getElementById('testEmailInput').value = '';" in html
        assert "document.getElementById('testNameInput').value = '';" in html
        assert "document.getElementById('searchQuery').value = '';" in html


def test_dashboard_javascript_syntax_validity():
    import subprocess
    import shutil
    import tempfile
    import re
    import os
    from src.web_server import get_html_dashboard

    node_bin = shutil.which("node")
    if not node_bin:
        return

    html = get_html_dashboard()
    scripts = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    assert len(scripts) > 0

    with tempfile.NamedTemporaryFile(suffix=".js", delete=False, mode="w", encoding="utf-8") as tmp:
        tmp.write("\n".join(scripts))
        tmp_path = tmp.name

    try:
        proc = subprocess.run([node_bin, "--check", tmp_path], capture_output=True, text=True)
        assert proc.returncode == 0, f"JavaScript syntax error in dashboard: {proc.stderr}"
    finally:
        os.unlink(tmp_path)


def test_google_oauth_login_uses_select_account_prompt(tmp_path: Path):
    from src.database import Database
    from src.web_server import start_web_server
    import urllib.request
    import urllib.error
    import json

    db = Database(tmp_path / "oauth_test.db")
    db.initialize()
    cfg_path = tmp_path / "cfg.json"
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"root_folder": str(tmp_path)}, f)

    port = 19205
    server = start_web_server(port=port, database=db, config_path=cfg_path)
    base_url = f"http://127.0.0.1:{port}"

    class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirectHandler)

    try:
        try:
            opener.open(f"{base_url}/auth/google/login")
        except urllib.error.HTTPError as e:
            if e.code == 302:
                loc = e.headers.get("Location", "")
                if "accounts.google.com" in loc:
                    assert "prompt=select_account" in loc
                    assert "drive.file" in loc
    finally:
        server.shutdown()


def test_persistent_session_restoration_across_restart(web_test_env):
    """Kiểm tra session được phục hồi từ SQLite sau khi SESSION_STORE bị xóa (mô phỏng restart server)."""
    from src.web_server import SESSION_STORE
    base_url, database, _ = web_test_env

    # 1. Đăng nhập tạo session
    req_data = json.dumps({"email": "persistent_user@univ.edu", "name": "Persistent User"}).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/auth/test-login", data=req_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        set_cookie = resp.headers.get("Set-Cookie", "")
        assert "ths_session=" in set_cookie
        assert "Max-Age=2592000" in set_cookie
        cookie_val = set_cookie.split(";")[0]

    # 2. Xóa sạch in-memory SESSION_STORE (mô phỏng khởi động lại web server)
    SESSION_STORE.clear()

    # 3. Gửi request tới /api/me kèm Cookie cũ
    me_req = urllib.request.Request(f"{base_url}/api/me", headers={"Cookie": cookie_val})
    with urllib.request.urlopen(me_req) as resp:
        me_data = json.loads(resp.read().decode("utf-8"))
        assert me_data.get("authenticated") is True
        assert me_data["user"]["email"] == "persistent_user@univ.edu"

    # 4. Đăng xuất
    logout_req = urllib.request.Request(f"{base_url}/auth/logout", data=b"{}", headers={"Cookie": cookie_val, "Content-Type": "application/json"})
    with urllib.request.urlopen(logout_req) as resp:
        clear_cookie = resp.headers.get("Set-Cookie", "")
        assert "Max-Age" not in clear_cookie or "1970" in clear_cookie

    # 5. Sau khi đăng xuất, /api/me không còn authenticated
    me_req2 = urllib.request.Request(f"{base_url}/api/me", headers={"Cookie": cookie_val})
    with urllib.request.urlopen(me_req2) as resp:
        me_data2 = json.loads(resp.read().decode("utf-8"))
        assert me_data2.get("authenticated") is False


def test_option_1_mandatory_subject_banner_and_upload(tmp_path: Path):
    """Kiểm tra Option 1: UI Banner nạp đa thiết bị có dropdown chọn môn bắt buộc & phân loại thư mục chuẩn 4 cấp con."""
    from src.database import Database
    from src.web_server import start_web_server, get_html_dashboard
    import base64
    import urllib.request
    import json

    # 1. Kiểm tra HTML Dashboard giao diện có đầy đủ thành phần Phương án 1
    html = get_html_dashboard()
    assert "uploadTargetSubject" in html
    assert "uploadTargetDocType" in html
    assert "uploadTargetBadge" in html
    assert "triggerCameraCapture()" in html
    assert "triggerFileUpload()" in html
    assert "populateUploadTargetSubjects" in html
    assert "onUploadTargetSubjectChange" in html

    # 2. Khởi tạo server và test upload có chọn môn & loại tài liệu
    db = Database(tmp_path / "opt1_test.db")
    db.initialize()
    cfg_path = tmp_path / "cfg.json"
    root_folder = tmp_path / "Root_Opt1"
    root_folder.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"root_folder": str(root_folder)}, f)

    port = 19207
    server = start_web_server(port=port, database=db, config_path=cfg_path)
    base_url = f"http://127.0.0.1:{port}"

    try:
        # Đăng nhập
        login_req = urllib.request.Request(
            f"{base_url}/auth/test-login",
            data=json.dumps({"email": "student_opt1@univ.edu", "name": "Sinh Vien"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(login_req) as resp:
            cookie = resp.headers.get("Set-Cookie").split(";")[0]

        # Nạp ảnh chụp bài giảng môn Cơ sở dữ liệu, loại Slide
        fake_content = base64.b64encode(b"lecture slide image content").decode("utf-8")
        payload = {
            "filename": "Photo_Lecture_01.jpg",
            "content_base64": fake_content,
            "subject": "Cơ sở dữ liệu",
            "subject_folder": "Co_So_Du_Lieu",
            "document_type": "Slide"
        }
        upload_req = urllib.request.Request(
            f"{base_url}/api/upload",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Cookie": cookie},
            method="POST"
        )
        with urllib.request.urlopen(upload_req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data["subject"] == "Cơ sở dữ liệu"
            assert data["document_type"] == "Slide"
            saved_path = Path(data["saved_path"])
            assert saved_path.exists()
            # Kiểm tra phân bổ chuẩn vào thư mục Co_So_Du_Lieu/02_Slide
            assert "Co_So_Du_Lieu" in saved_path.parts
            assert "02_Slide" in saved_path.parts
    finally:
        server.shutdown()


def test_upload_triggers_notebooklm_enqueue(tmp_path: Path):
    """Kiểm tra upload tài liệu tự động kích hoạt nạp nguồn NotebookLM qua enqueue_sync."""
    import base64
    from unittest.mock import MagicMock
    from src.notebooklm_sync import NotebookLMSyncManager

    db_path = tmp_path / "nlm_test.db"
    database = Database(db_path=db_path)
    database.initialize()

    cfg_path = tmp_path / "cfg.json"
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"root_folder": str(tmp_path / "Mon_Hoc")}, f)

    port = 19130
    mock_nlm = MagicMock(spec=NotebookLMSyncManager)


    server = start_web_server(
        port=port,
        database=database,
        config_path=tmp_path / "cfg.json",
        nlm_sync_manager=mock_nlm,
    )
    base_url = f"http://127.0.0.1:{port}"

    try:
        # Đăng nhập
        login_req = urllib.request.Request(
            f"{base_url}/auth/test-login",
            data=json.dumps({"email": "nlm_user@univ.edu", "name": "NLM User"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(login_req) as resp:
            cookie = resp.headers.get("Set-Cookie").split(";")[0]


        # Upload file PDF bài giảng
        fake_content = base64.b64encode(b"%PDF-1.4 dummy pdf content").decode("utf-8")
        payload = {
            "filename": "Giao_Trinh_CSDL.pdf",
            "content_base64": fake_content,
            "subject": "Cơ sở dữ liệu",
            "subject_folder": "Co_So_Du_Lieu",
            "document_type": "Giáo trình",
        }
        upload_req = urllib.request.Request(
            f"{base_url}/api/upload",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Cookie": cookie},
            method="POST",
        )
        with urllib.request.urlopen(upload_req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True

        # Kiểm tra mock_nlm.enqueue_sync đã được gọi
        assert mock_nlm.enqueue_sync.called
        call_args = mock_nlm.enqueue_sync.call_args[1]
        assert "Giao_Trinh_CSDL.pdf" in call_args["file_path"]
        assert call_args["course_name"] == "Cơ sở dữ liệu"
    finally:
        server.shutdown()












