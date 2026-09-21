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
    finally:
        server.shutdown()





