"""tests/test_golden_baseline.py — Test bộ 5 luồng cốt lõi Golden Baseline theo chuẩn TDD."""

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

import main


def test_stubs_exist_and_are_empty():
    """Kiểm tra các hàm/class xử lý hàng đợi, file watcher, drive sync đã được dọn sạch thành stub."""
    # File watcher handler
    assert hasattr(main, "WatchdogHandler")
    handler = main.WatchdogHandler()
    assert handler is not None

    # Worker loop / queue
    assert hasattr(main, "worker_loop")
    assert main.worker_loop() is None

    # Drive sync
    assert hasattr(main, "sync_drive")
    assert main.sync_drive() is None

    # Scan existing files
    assert hasattr(main, "scan_existing_files")
    assert main.scan_existing_files() is None


def test_step1_load_config_success(tmp_path: Path):
    """Bước 1: Đọc cấu hình từ file/môi trường thành công."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text('{"root_folder": "%s", "root_account_email": "test@example.com"}' % str(tmp_path).replace("\\", "\\\\"), encoding="utf-8")
    
    cfg = main.step1_load_config(config_path=cfg_file)
    assert cfg["root_account_email"] == "test@example.com"
    assert Path(cfg["root_folder"]).exists()


def test_step1_load_config_failure(tmp_path: Path):
    """Bước 1: Ném Exception nếu file cấu hình không tồn tại."""
    with pytest.raises(Exception):
        main.step1_load_config(config_path=tmp_path / "non_existent.json")


def test_step2_connect_mcp_success():
    """Bước 2: Kiểm tra kết nối MCP và NotebookLM CLI thành công."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="nlm version 0.11.6\n")
        res = main.step2_connect_mcp()
        assert res is True
        mock_run.assert_called_once()


def test_step2_connect_mcp_failure():
    """Bước 2: Ném Exception nếu NotebookLM CLI không phản hồi hoặc lỗi."""
    with patch("subprocess.run", side_effect=FileNotFoundError("nlm not found")):
        with pytest.raises(Exception):
            main.step2_connect_mcp()


def test_step3_init_firebase_success(tmp_path: Path):
    """Bước 3: Khởi tạo SDK Firebase thành công."""
    with patch("main.initialize_firebase_sdk") as mock_init:
        mock_init.return_value = MagicMock()
        app = main.step3_init_firebase()
        assert app is not None


def test_step3_init_firebase_failure():
    """Bước 3: Ném Exception nếu không tìm thấy service account hoặc lỗi init."""
    with patch("main.initialize_firebase_sdk", side_effect=FileNotFoundError("Không tìm thấy service account")):
        with pytest.raises(Exception):
            main.step3_init_firebase()


def test_step4_auth_user_success():
    """Bước 4: Xác thực người dùng bằng email thành công."""
    with patch("main.verify_user_auth", return_value={"email": "xuanngocit@gmail.com", "verified": True}):
        user = main.step4_authenticate_user("xuanngocit@gmail.com")
        assert user["email"] == "xuanngocit@gmail.com"


def test_step4_auth_user_failure():
    """Bước 4: Ném Exception nếu email rỗng hoặc không hợp lệ."""
    with pytest.raises(Exception):
        main.step4_authenticate_user("")


def test_step5_ping_cloudflare_success():
    """Bước 5: Ping Cloudflare Worker trả về 200 OK."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok"}
    
    with patch("requests.get", return_value=mock_resp):
        res = main.step5_ping_cloudflare("https://dummy.workers.dev")
        assert res is True


def test_step5_ping_cloudflare_failure():
    """Bước 5: Ném Exception nếu Cloudflare Worker lỗi kết nối hoặc HTTP 500."""
    mock_resp = MagicMock()
    mock_resp.status_code = 502
    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(Exception):
            main.step5_ping_cloudflare("https://dummy.workers.dev")


def test_main_runs_all_5_steps_and_prints_exact_5_lines(capsys):
    """Kiểm tra hàm main() chạy đúng 5 bước và in ra ĐÚNG 5 dòng log chuẩn."""
    with patch("main.step1_load_config", return_value={"root_account_email": "xuanngocit@gmail.com", "worker_url": "https://test.workers.dev"}), \
         patch("main.step2_connect_mcp", return_value=True), \
         patch("main.step3_init_firebase", return_value=MagicMock()), \
         patch("main.step4_authenticate_user", return_value={"email": "xuanngocit@gmail.com"}), \
         patch("main.step5_ping_cloudflare", return_value=True):
        
        main.main()

        captured = capsys.readouterr().out.strip().splitlines()
        expected = [
            "✅ Đọc cấu hình thư mục thành công...",
            "✅ Kết nối NotebookLM MCP CLI thành công...",
            "✅ Kết nối login firebase thành công",
            "✅ Kết nối login bằng email thành công",
            "✅ Build deploy cloudflare sẵn sàng",
        ]
        assert captured == expected


def test_main_aborts_immediately_on_step_failure():
    """Kiểm tra khi bất kỳ bước nào lỗi, chương trình dừng ngay lập tức và ném Exception / thoát."""
    with patch("main.step1_load_config", side_effect=RuntimeError("Lỗi cấu hình")), \
         patch("main.step2_connect_mcp") as mock_step2:
        
        with pytest.raises(Exception):
            main.main()
        
        # Bước 2 không bao giờ được gọi tới
        mock_step2.assert_not_called()
