"""Unit tests cho sync.py (Đồng bộ Drive về Local)."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.classifier import PathClassifier
from src.database import Database, STATUS_UPLOADED
from src.sync import sync_from_drive_to_local


def test_sync_from_drive_to_local(tmp_path: Path) -> None:
    root = tmp_path / "Mon_Hoc"
    root.mkdir(parents=True, exist_ok=True)
    db_file = tmp_path / "test_sync.db"

    database = Database(db_path=db_file)
    database.initialize()
    classifier = PathClassifier(root_folder=root)

    mock_drive = MagicMock()
    mock_drive.is_configured.return_value = True
    mock_drive.list_all_study_materials.return_value = [
        {
            "file_id": "drive_file_cloud_123",
            "name": "Bai_Moi_Tu_Dien_Thoai.pdf",
            "subject": "Triết học",
            "document_type": "Giáo trình",
            "size": 1024,
        }
    ]

    def mock_download(file_id, dest_path):
        p = Path(dest_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("Nội dung tải về từ Google Drive", encoding="utf-8")
        return p

    mock_drive.download_file.side_effect = mock_download

    # Lần chạy 1: Phát hiện file trên Drive chưa có ở local -> Kéo về máy
    downloaded = sync_from_drive_to_local(
        drive_manager=mock_drive,
        database=database,
        root_folder=root,
        classifier=classifier,
    )

    assert len(downloaded) == 1
    assert downloaded[0]["file_name"] == "Bai_Moi_Tu_Dien_Thoai.pdf"
    assert downloaded[0]["subject"] == "Triết học"

    # Kiểm tra file đã được tạo trên ổ cứng
    local_file = Path(downloaded[0]["local_path"])
    assert local_file.is_file()
    assert local_file.read_text(encoding="utf-8") == "Nội dung tải về từ Google Drive"

    # Kiểm tra SQLite đã có record với drive_file_id tương ứng
    db_rec = database.find_by_drive_file_id("drive_file_cloud_123")
    assert db_rec is not None
    assert db_rec["status"] == STATUS_UPLOADED
    assert db_rec["subject"] == "Triết học"

    # Lần chạy 2: File đã có trên máy -> Không tải lại nữa
    downloaded_again = sync_from_drive_to_local(
        drive_manager=mock_drive,
        database=database,
        root_folder=root,
        classifier=classifier,
    )
    assert len(downloaded_again) == 0


def test_auto_drive_sync_worker(tmp_path: Path) -> None:
    from src.sync import AutoDriveSyncWorker

    root = tmp_path / "Mon_Hoc"
    root.mkdir(parents=True, exist_ok=True)
    db_file = tmp_path / "test_worker.db"

    database = Database(db_path=db_file)
    database.initialize()

    mock_drive = MagicMock()
    mock_drive.is_configured.return_value = True
    mock_drive.list_all_study_materials.return_value = []

    worker = AutoDriveSyncWorker(
        drive_manager=mock_drive,
        database=database,
        root_folder=root,
        interval_seconds=60,
        enabled=True,
    )

    info = worker.get_status_info()
    assert info["enabled"] is True
    assert info["interval_seconds"] == 60
    assert info["last_sync_status"] == "Chưa chạy"

    # Kích hoạt trigger_now
    result = worker.trigger_now()
    assert result == []

    updated_info = worker.get_status_info()
    assert "Đã đồng bộ" in updated_info["last_sync_status"]

    # Cập nhật setting
    worker.update_settings(enabled=False, interval_seconds=120)
    assert worker.enabled is False
    assert worker.interval_seconds == 120

    worker.stop()

