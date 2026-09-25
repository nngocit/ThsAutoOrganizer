"""tests/test_local_disk_reconcile.py — Kiểm thử tự động tính năng Quét & Đối soát tệp tin Local."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from local_agent.local_reconciler import (
    scan_local_disk,
    reconcile_with_firestore,
    handle_reconcile_local,
)


def test_scan_local_disk_finds_files(tmp_path):
    """Quét thư mục tạm có file hợp lệ và bỏ qua file ẩn / file rỗng."""
    subfolder = tmp_path / "Mon_Test"
    subfolder.mkdir()
    valid_file = subfolder / "Tai_Lieu.docx"
    valid_file.write_bytes(b"A" * 500)

    empty_file = subfolder / "Empty.docx"
    empty_file.write_bytes(b"")

    hidden_file = subfolder / ".DS_Store"
    hidden_file.write_bytes(b"some data")

    results = scan_local_disk(tmp_path)
    assert len(results) == 1
    assert results[0]["name"] == "Tai_Lieu.docx"
    assert results[0]["folder"] == "Mon_Test"
    assert results[0]["size_bytes"] == 500


def test_reconcile_with_firestore_matches_and_patches(tmp_path):
    """Khi file trên đĩa khớp với doc Firestore chưa synced, thực hiện patch status."""
    subfolder = tmp_path / "Mon_ABC"
    subfolder.mkdir()
    file_on_disk = subfolder / "Bai_Giang.pdf"
    file_on_disk.write_bytes(b"PDF DATA" * 100)

    mock_firestore_files = [
        {
            "id": "file_123",
            "filename": "Bai_Giang.pdf",
            "subject": "Mon_ABC",
            "local_sync_status": "pending",
            "local_path": "",
            "uid": "user_456",
        }
    ]

    with patch("local_agent.local_reconciler.scan_local_disk") as mock_scan, \
         patch("local_agent.local_reconciler._fetch_firestore_files", return_value=mock_firestore_files), \
         patch("local_agent.nlm_task_handler._report_local_sync_status", return_value=True) as mock_report:

        mock_scan.return_value = [
            {
                "name": "Bai_Giang.pdf",
                "folder": "Mon_ABC",
                "rel_path": "Mon_ABC/Bai_Giang.pdf",
                "full_path": str(file_on_disk),
                "size_bytes": 800,
            }
        ]

        summary = reconcile_with_firestore(uid="user_456")
        assert summary["matched_count"] == 1
        assert summary["updated_count"] == 1
        assert mock_report.called
        mock_report.assert_called_with("file_123", "Mon_ABC/Bai_Giang.pdf", "user_456", "synced")


def test_handle_reconcile_local_task():
    """Tác vụ reconcile_local từ task queue trả về chuỗi JSON hợp lệ."""
    with patch("local_agent.local_reconciler.reconcile_with_firestore") as mock_rec:
        mock_rec.return_value = {
            "status": "success",
            "matched_count": 2,
            "updated_count": 1,
            "disk_files_count": 5,
        }
        res_json = handle_reconcile_local({"uid": "user_abc", "course_id": "c_123"})
        data = json.loads(res_json)
        assert data["matched_count"] == 2
        assert data["updated_count"] == 1
