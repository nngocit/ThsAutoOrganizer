"""tests/test_config_aliases.py — Test cơ chế alias 2 chiều giữa local_base_path <-> root_folder
và google_drive_root_folder_id <-> drive_root_folder.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from local_agent.config_loader import load_config, get_config, get, sync_remote_config


def test_alias_root_folder_to_local_base_path(tmp_path: Path):
    """Khi config.json chỉ có 'root_folder', 'local_base_path' tự động đồng bộ giá trị tương ứng."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "root_folder": "D:\\MyCourses\\2026",
    }), encoding="utf-8")

    cfg = load_config(cfg_file)
    assert cfg["root_folder"] == "D:\\MyCourses\\2026"
    assert cfg["local_base_path"] == "D:\\MyCourses\\2026"
    assert get("local_base_path") == "D:\\MyCourses\\2026"
    assert get("root_folder") == "D:\\MyCourses\\2026"


def test_alias_local_base_path_to_root_folder(tmp_path: Path):
    """Khi config.json chỉ có 'local_base_path', 'root_folder' tự động đồng bộ giá trị tương ứng."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "local_base_path": "E:\\Study\\HTTT",
    }), encoding="utf-8")

    cfg = load_config(cfg_file)
    assert cfg["local_base_path"] == "E:\\Study\\HTTT"
    assert cfg["root_folder"] == "E:\\Study\\HTTT"
    assert get("local_base_path") == "E:\\Study\\HTTT"
    assert get("root_folder") == "E:\\Study\\HTTT"


def test_alias_drive_root_folder_interchangeable(tmp_path: Path):
    """Khi config.json dùng 'drive_root_folder', 'google_drive_root_folder_id' tự động đồng bộ."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "drive_root_folder": "folder_abc_123",
    }), encoding="utf-8")

    cfg = load_config(cfg_file)
    assert cfg["drive_root_folder"] == "folder_abc_123"
    assert cfg["google_drive_root_folder_id"] == "folder_abc_123"
    assert get("google_drive_root_folder_id") == "folder_abc_123"
    assert get("drive_root_folder") == "folder_abc_123"


def test_sync_remote_config_updates_both_aliases(tmp_path: Path):
    """Khi remote Firestore cập nhật cấu hình Cloud, cả hai alias đều được cập nhật."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "local_base_path": "C:\\OldPath",
        "google_drive_root_folder_id": "old_drive_id",
    }), encoding="utf-8")

    load_config(cfg_file)

    mock_resp = {
        "config": {
            "local_base_path": "C:\\NewPathFromCloud",
            "google_drive_root_folder_id": "new_cloud_drive_id",
            "google_drive_root_name": "ThacSi_HTTT - Cloud",
        }
    }

    with patch("local_agent.api_client.get_system_config", return_value=mock_resp):
        updated = sync_remote_config(uid="test_user")
        assert updated["local_base_path"] == "C:\\NewPathFromCloud"
        assert updated["root_folder"] == "C:\\NewPathFromCloud"
        assert updated["google_drive_root_folder_id"] == "new_cloud_drive_id"
        assert updated["drive_root_folder"] == "new_cloud_drive_id"
