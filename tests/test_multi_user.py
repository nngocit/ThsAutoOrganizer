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

    assert user_a["email"] == "sinhvienA@fit.edu.vn"
    assert user_b["email"] == "sinhvienB@fit.edu.vn"

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
