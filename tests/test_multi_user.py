"""Kiểm thử tính năng Multi-User và Nạp tài liệu đa thiết bị."""

import base64
import json
from pathlib import Path
import urllib.request
import pytest

from src.database import Database
from src.web_server import start_web_server


def test_multi_user_database_isolation(tmp_path: Path):
    db_path = tmp_path / "multi_user.db"
    db = Database(db_path)
    db.initialize()

    # Tạo 2 sinh viên khác nhau
    user_a = db.get_or_create_user(email="sinhvienA@fit.edu.vn", name="Sinh viên A")
    user_b = db.get_or_create_user(email="sinhvienB@fit.edu.vn", name="Sinh viên B")

    assert user_a["email"] == "sinhviena@fit.edu.vn"
    assert user_b["email"] == "sinhvienb@fit.edu.vn"

    # User A thêm file
    db.insert_record(
        sha256="hash_a",
        path="Toan_Khoa_Hoc_Du_Lieu/file_a.pdf",
        subject="Toán khoa học dữ liệu",
        document_type="Giáo trình",
        user_email="sinhvienA@fit.edu.vn",
    )

    # User B thêm file
    db.insert_record(
        sha256="hash_b",
        path="Triet_Hoc/file_b.pdf",
        subject="Triết học",
        document_type="Ôn thi",
        user_email="sinhvienB@fit.edu.vn",
    )

    # Kiểm tra tính cách ly (Data Isolation)
    records_a = db.get_all_records(user_email="sinhvienA@fit.edu.vn")
    records_b = db.get_all_records(user_email="sinhvienB@fit.edu.vn")

    assert len(records_a) == 1
    assert records_a[0]["sha256"] == "hash_a"

    assert len(records_b) == 1
    assert records_b[0]["sha256"] == "hash_b"


def test_multi_user_web_api(tmp_path: Path):
    db_path = tmp_path / "web_multi.db"
    db = Database(db_path)
    db.initialize()

    cfg_path = tmp_path / "config.json"
    root_folder = tmp_path / "Mon_Hoc"
    root_folder.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"root_folder": str(root_folder)}, f)

    import random
    port = random.randint(19000, 19999)
    server = start_web_server(port=port, database=db, config_path=cfg_path)
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. Test đăng nhập sinh viên
        login_payload = json.dumps({"email": "student1@school.edu.vn", "name": "Nguyễn Văn A"}).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/auth/test-login",
            data=login_payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data["user"]["email"] == "student1@school.edu.vn"
            cookie = resp.headers.get("Set-Cookie")
            assert "ths_session" in cookie

        # 2. Test nạp tài liệu qua API upload
        file_content = b"Noi dung bai giang tren lop"
        content_b64 = base64.b64encode(file_content).decode("utf-8")
        upload_payload = json.dumps({
            "filename": "Bai_Giang_Buoi_1.txt",
            "content_base64": content_b64,
            "subject": "Triết học",
            "document_type": "Giáo trình",
        }).encode("utf-8")

        upload_req = urllib.request.Request(
            f"{base_url}/api/upload",
            data=upload_payload,
            headers={"Content-Type": "application/json", "Cookie": cookie},
        )
        with urllib.request.urlopen(upload_req) as resp:
            assert resp.status == 200
            res_data = json.loads(resp.read().decode("utf-8"))
            assert res_data["ok"] is True
            assert res_data["filename"] == "Bai_Giang_Buoi_1.txt"

        # 3. Test lấy danh sách file đã nạp
        files_req = urllib.request.Request(
            f"{base_url}/api/files",
            headers={"Cookie": cookie},
        )
        with urllib.request.urlopen(files_req) as resp:
            files_data = json.loads(resp.read().decode("utf-8"))
            assert len(files_data) == 1
            assert files_data[0]["subject"] == "Triết học"
    finally:
        server.shutdown()


def test_user_folder_and_scan(tmp_path: Path):
    """Kiểm tra lưu thư mục cá nhân và kích hoạt quét đúng thư mục + email."""
    db_path = tmp_path / "folder_scan.db"
    db = Database(db_path)
    db.initialize()

    cfg_path = tmp_path / "config.json"
    root_folder = tmp_path / "Default_Root"
    root_folder.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"root_folder": str(root_folder)}, f)

    scan_invocations = []

    def mock_scan(target_folder=None, user_email="default@user"):
        scan_invocations.append((target_folder, user_email))
        return 7

    import random
    port = random.randint(20000, 20999)
    server = start_web_server(port=port, database=db, config_path=cfg_path, scan_callback=mock_scan)
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. Đăng nhập với email cụ thể
        login_payload = json.dumps({"email": "mongxuancomestic@gmail.com", "name": "Mộng Xuân"}).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/auth/test-login",
            data=login_payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            cookie = resp.headers.get("Set-Cookie")

        # 2. Cập nhật thư mục máy tính riêng cho user
        custom_folder = str(tmp_path / "MongXuan_Folder")
        folder_payload = json.dumps({"local_folder": custom_folder}).encode("utf-8")
        folder_req = urllib.request.Request(
            f"{base_url}/api/user/folder",
            data=folder_payload,
            headers={"Content-Type": "application/json", "Cookie": cookie},
        )
        with urllib.request.urlopen(folder_req) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            assert res["ok"] is True
            assert res["local_folder"] == custom_folder

        # Kiểm tra database đã lưu folder
        u = db.get_user_by_email("mongxuancomestic@gmail.com")
        assert u is not None
        assert u["local_folder"] == custom_folder

        # 3. Kích hoạt quét thư mục cho user này
        scan_req = urllib.request.Request(
            f"{base_url}/api/scan",
            data=json.dumps({"folder_path": custom_folder}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Cookie": cookie},
        )
        with urllib.request.urlopen(scan_req) as resp:
            assert resp.status == 200
            scan_res = json.loads(resp.read().decode("utf-8"))
            assert scan_res["ok"] is True
            assert scan_res["count"] == 7
            assert scan_res["user_email"] == "mongxuancomestic@gmail.com"
            assert scan_res["folder"] == custom_folder

        assert len(scan_invocations) == 1
        assert scan_invocations[0] == (custom_folder, "mongxuancomestic@gmail.com")
    finally:
        server.shutdown()


def test_multi_user_upload_and_drive_isolation(tmp_path: Path):
    """Kiểm tra tuyệt đối không rò rỉ file hoặc Google Drive giữa tài khoản gốc và sinh viên khác."""
    from unittest.mock import MagicMock

    db_path = tmp_path / "isolation.db"
    db = Database(db_path)
    db.initialize()

    cfg_path = tmp_path / "config.json"
    root_folder = tmp_path / "Root_Mon_Hoc"
    root_folder.mkdir()
    cfg_data = {
        "root_folder": str(root_folder),
        "root_account_email": "xuanngocit@gmail.com",
    }
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg_data, f)

    # Thêm sẵn 2 file thuộc về tài khoản gốc xuanngocit
    db.insert_record(
        sha256="root_hash_1",
        path=str(root_folder / "root_file1.pdf"),
        subject="Toán khoa học dữ liệu",
        document_type="Giáo trình",
        status="UPLOADED",
        drive_file_id="root_drive_1",
        user_email="xuanngocit@gmail.com",
    )

    # Mock Google Drive của tài khoản gốc
    mock_root_drive = MagicMock()
    mock_root_drive.is_configured.return_value = True
    mock_root_drive.upload_file.return_value = "drive_should_not_be_called_for_others"

    import socket
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()

    server = start_web_server(
        port=port,
        database=db,
        drive_manager=mock_root_drive,
        config_path=cfg_path,
    )
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. Đăng nhập tài khoản gốc xuanngocit
        req_root = urllib.request.Request(
            f"{base_url}/auth/test-login",
            data=json.dumps({"email": "xuanngocit@gmail.com", "name": "Admin XuanNgoc"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_root) as resp:
            cookie_root = resp.headers.get("Set-Cookie")

        # Kiểm tra /api/files của xuanngocit có 1 file gốc
        req_files_root = urllib.request.Request(f"{base_url}/api/files", headers={"Cookie": cookie_root})
        with urllib.request.urlopen(req_files_root) as resp:
            files_root = json.loads(resp.read().decode("utf-8"))
            assert len(files_root) == 1
            assert files_root[0]["sha256"] == "root_hash_1"

        # 2. Đăng nhập tài khoản sinh viên mongxuancomestic@gmail.com
        req_b = urllib.request.Request(
            f"{base_url}/auth/test-login",
            data=json.dumps({"email": "mongxuancomestic@gmail.com", "name": "Mộng Xuân"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_b) as resp:
            cookie_b = resp.headers.get("Set-Cookie")

        # Kiểm tra /api/me của User B: Drive chưa kết nối, thư mục thuộc Users_Storage
        req_me_b = urllib.request.Request(f"{base_url}/api/me", headers={"Cookie": cookie_b})
        with urllib.request.urlopen(req_me_b) as resp:
            me_b = json.loads(resp.read().decode("utf-8"))
            assert me_b["authenticated"] is True
            assert me_b["drive_connected"] is False
            assert "Users_Storage" in me_b["user"]["local_folder"]

        # Kiểm tra /api/files của User B: Phải rỗng (0 file)
        req_files_b = urllib.request.Request(f"{base_url}/api/files", headers={"Cookie": cookie_b})
        with urllib.request.urlopen(req_files_b) as resp:
            files_b = json.loads(resp.read().decode("utf-8"))
            assert len(files_b) == 0

        # 3. User B nạp file qua API upload
        dummy_content = base64.b64encode("Nội dung tài liệu của sinh viên Mộng Xuân".encode("utf-8")).decode("utf-8")
        upload_payload = json.dumps({
            "filename": "BaiGiang_MongXuan.pdf",
            "content_base64": dummy_content,
            "subject": "Triết học",
            "document_type": "Slide",
        }).encode("utf-8")

        upload_req = urllib.request.Request(
            f"{base_url}/api/upload",
            data=upload_payload,
            headers={"Content-Type": "application/json", "Cookie": cookie_b},
            method="POST",
        )
        with urllib.request.urlopen(upload_req) as resp:
            upload_res = json.loads(resp.read().decode("utf-8"))
            assert upload_res["ok"] is True
            assert upload_res["status"] == "SAVED_LOCAL"
            assert upload_res["drive_file_id"] is None

        # Tuyệt đối KHÔNG gọi upload_file lên Google Drive của tài khoản gốc!
        assert mock_root_drive.upload_file.call_count == 0

        # 4. Kiểm tra /api/files của User B có đúng 1 file vừa nạp
        with urllib.request.urlopen(req_files_b) as resp:
            files_b_after = json.loads(resp.read().decode("utf-8"))
            assert len(files_b_after) == 1
            assert files_b_after[0]["subject"] == "Triết học"
            assert files_b_after[0]["status"] == "SAVED_LOCAL"
            assert "Users_Storage" in files_b_after[0]["path"]

        # 5. Kiểm tra /api/files của xuanngocit: Vẫn chỉ có 1 file gốc, KHÔNG BỊ LẪN file của User B!
        with urllib.request.urlopen(req_files_root) as resp:
            files_root_after = json.loads(resp.read().decode("utf-8"))
            assert len(files_root_after) == 1
            assert files_root_after[0]["sha256"] == "root_hash_1"

    finally:
        server.shutdown()

