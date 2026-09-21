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


