"""Kiểm thử tính năng Multi-User và Nạp tài liệu đa thiết bị."""

import base64
import json
from pathlib import Path
import urllib.request
import pytest

from src.database import Database, STATUS_SAVED_LOCAL
from src.drive import DriveManager
from src.classifier import PathClassifier
from src.processor import FileProcessor
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


def test_drive_manager_from_token_dict_credentials_file(tmp_path: Path):
    """Kiểm tra DriveManager.from_token_dict chấp nhận tham số credentials_file và đọc client_id."""
    fake_creds = tmp_path / "fake_creds.json"
    fake_creds.write_text(
        json.dumps({
            "installed": {
                "client_id": "test_client_id.apps.googleusercontent.com",
                "client_secret": "test_secret_123",
            }
        }),
        encoding="utf-8",
    )

    token_dict = {
        "access_token": "fake_access_token",
        "refresh_token": "fake_refresh_token",
    }

    dm = DriveManager.from_token_dict(
        token_info=token_dict,
        credentials_file=str(fake_creds),
        root_folder_id="custom_drive_id_456",
    )
    assert dm is not None
    assert dm._credentials is not None
    assert dm._credentials.client_id == "test_client_id.apps.googleusercontent.com"
    assert dm._credentials.client_secret == "test_secret_123"
    assert dm.root_folder_id == "custom_drive_id_456"


def test_multi_user_isolated_folder_with_heuristic_classification(tmp_path: Path):
    """Kiểm tra file đặt trong thư mục riêng của user (Users_Storage/<user>/New folder/...)
    vẫn được phân loại thông minh và xử lý an toàn thay vì báo lỗi cấu trúc."""
    db_path = tmp_path / "test_iso.db"
    db = Database(db_path)
    db.initialize()

    # Tạo tài khoản sinh viên Mộng Xuân
    user_email = "mongxuancomestic@gmail.com"
    db.get_or_create_user(email=user_email, name="Mộng Xuân")

    root_folder = tmp_path / "Mon_Hoc"
    root_folder.mkdir(parents=True, exist_ok=True)

    # Thư mục Users_Storage cho sinh viên
    user_storage = tmp_path / "Users_Storage" / "mongxuancomestic_at_gmail_com"
    ad_hoc_folder = user_storage / "New folder"
    ad_hoc_folder.mkdir(parents=True, exist_ok=True)

    # Tạo file mẫu (ảnh hoặc tài liệu) trong New folder
    test_img = ad_hoc_folder / "Gemini_Generated_Image_gk1m29gk1m29gk1m.png"
    test_img.write_bytes(b"dummy image data" * 100)  # > 1000 bytes

    classifier = PathClassifier(root_folder=root_folder, allow_direct_subject_files=True)
    processor = FileProcessor(
        classifier=classifier,
        database=db,
        drive_manager=None,
        min_file_size_bytes=100,
        supported_extensions=[".png", ".pdf", ".txt"],
        extract_content=True,
    )

    # Xử lý file cho user_email mongxuancomestic@gmail.com
    result = processor.process_file(test_img, user_email=user_email)

    assert result.status == STATUS_SAVED_LOCAL
    assert result.subject == "Tài liệu chung"
    assert result.document_type == "Tài liệu tham khảo"
    assert result.sha256 is not None

    # Kiểm tra trong Database
    records = db.get_all_records(user_email=user_email)
    assert len(records) == 1
    assert records[0]["status"] == STATUS_SAVED_LOCAL
    assert records[0]["subject"] == "Tài liệu chung"
    assert records[0]["document_type"] == "Tài liệu tham khảo"
    assert records[0]["user_email"] == user_email


def test_multi_user_end_to_end_logout_leak_prevention(tmp_path: Path):
    """Kiểm tra toàn diện quy trình Đăng nhập -> Kiểm tra thông tin cá nhân -> Đăng xuất -> Không còn vết dữ liệu."""
    import random
    db_path = tmp_path / "leak_test.db"
    db = Database(db_path)
    db.initialize()

    cfg_path = tmp_path / "cfg.json"
    root_folder = tmp_path / "Mon_Hoc"
    root_folder.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"root_folder": str(root_folder)}, f)

    port = random.randint(18800, 19800)
    server = start_web_server(port=port, database=db, config_path=cfg_path)
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. Đăng nhập tài khoản sinh viên Mộng Xuân
        login_payload = json.dumps({
            "email": "mongxuancomestic@gmail.com",
            "name": "Mộng Xuân"
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/auth/test-login",
            data=login_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            cookie = resp.headers.get("Set-Cookie")
            assert "ths_session" in cookie

        # 2. Kiểm tra /api/me trả về đúng thông tin cá nhân của Mộng Xuân
        req_me = urllib.request.Request(f"{base_url}/api/me", headers={"Cookie": cookie})
        with urllib.request.urlopen(req_me) as resp:
            me_data = json.loads(resp.read().decode("utf-8"))
            assert me_data["authenticated"] is True
            assert me_data["user"]["email"] == "mongxuancomestic@gmail.com"
            assert "mongxuancomestic" in me_data["user"]["local_folder"]

        # 3. Thực hiện Đăng xuất (Logout)
        req_logout = urllib.request.Request(
            f"{base_url}/auth/logout",
            data=b"{}",
            headers={"Cookie": cookie},
            method="POST",
        )
        with urllib.request.urlopen(req_logout) as resp:
            assert resp.status == 200
            logout_cookie = resp.headers.get("Set-Cookie")
            assert "Max-Age=0" in logout_cookie or "expires=" in logout_cookie.lower() or "ths_session=;" in logout_cookie

        # 4. Kiểm tra /api/me sau khi logout (kể cả khi gửi cookie cũ): authenticated = False, không rò rỉ user
        req_me_after = urllib.request.Request(f"{base_url}/api/me", headers={"Cookie": cookie})
        with urllib.request.urlopen(req_me_after) as resp:
            after_data = json.loads(resp.read().decode("utf-8"))
            assert after_data["authenticated"] is False
            assert after_data["user"] is None
            assert after_data["drive_connected"] is False
            assert "mongxuan" not in json.dumps(after_data)
    finally:
        server.shutdown()


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





