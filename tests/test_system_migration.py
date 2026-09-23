# tests/test_system_migration.py — Tests for system_migration tool
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.system_migration import (
    _sha256,
    _split_rel_path,
    _infer_document_type,
    resolve_course_for_subject,
    migrate_local_to_drive,
    reconcile_drive_to_local,
)


def test_sha256_calculation(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello World Migration", encoding="utf-8")
    digest = _sha256(f)
    assert isinstance(digest, str)
    assert len(digest) == 64


def test_split_rel_path():
    base = Path("H:/Mon_Hoc")
    # File at root of Mon_Hoc
    p1 = Path("H:/Mon_Hoc/thong_bao.pdf")
    subj, folder, fn = _split_rel_path(p1, base)
    assert subj == "Tài liệu chung"
    assert folder == ""
    assert fn == "thong_bao.pdf"

    # File in subject with subfolder
    p2 = Path("H:/Mon_Hoc/Triet Hoc/01_Giao_Trinh/book.pdf")
    subj, folder, fn = _split_rel_path(p2, base)
    assert subj == "Triet Hoc"
    assert folder == "01_Giao_Trinh"
    assert fn == "book.pdf"


def test_infer_document_type():
    assert _infer_document_type("01_Giao_Trinh_Goc") == "giao_trinh"
    assert _infer_document_type("02_Slide_Giang_Day") == "slide"
    assert _infer_document_type("03_Tai_Lieu_Tham_Khao/01_Bai_Bao_Khoa_Hoc") == "bai_bao"
    assert _infer_document_type("custom_slide_folder") == "slide"


def test_resolve_course_for_subject():
    courses_map = {
        "triet_hoc": {"id": "c_triet", "name": "Triết học", "notebooklm_id": "nb_triet_123"},
        "triết học": {"id": "c_triet", "name": "Triết học", "notebooklm_id": "nb_triet_123"},
        "triet hoc": {"id": "c_triet", "name": "Triết học", "notebooklm_id": "nb_triet_123"},
    }

    # Tài liệu chung -> empty course_id
    cid, nbid = resolve_course_for_subject("Tài liệu chung", courses_map)
    assert cid == ""
    assert nbid == ""

    # Subject Triet Hoc
    cid, nbid = resolve_course_for_subject("Triet Hoc", courses_map)
    assert cid == "c_triet"
    assert nbid == "nb_triet_123"


def test_migrate_local_to_drive_dry_run(tmp_path):
    """Kiểm tra migrate_local_to_drive chạy an toàn ở chế độ dry-run."""
    sub_dir = tmp_path / "Triet Hoc" / "01_Giao_Trinh"
    sub_dir.mkdir(parents=True, exist_ok=True)
    sample_file = sub_dir / "sample_doc.pdf"
    sample_file.write_bytes(b"A" * 2048)  # > 1000 bytes

    mock_service = MagicMock()
    mock_files = MagicMock()
    mock_service.files.return_value = mock_files
    mock_files.list.return_value.execute.return_value = {"files": []}

    with patch("tools.system_migration._get_drive_service", return_value=mock_service), \
         patch("tools.system_migration.get_courses_map", return_value={}):
        # Không được ném exception
        migrate_local_to_drive(tmp_path, "drive_root_test_id", dry_run=True)
        # Trong dry-run, không gọi create file thật
        mock_files.create.assert_not_called()


def test_reconcile_drive_to_local_dry_run(tmp_path):
    """Kiểm tra reconcile_drive_to_local chạy an toàn ở chế độ dry-run."""
    mock_service = MagicMock()
    mock_files = MagicMock()
    mock_service.files.return_value = mock_files
    mock_files.list.return_value.execute.return_value = {
        "files": [
            {
                "id": "f_1",
                "name": "Toan_Cao_Cap.pdf",
                "mimeType": "application/pdf",
                "size": "5000",
            }
        ]
    }

    with patch("tools.system_migration._get_drive_service", return_value=mock_service):
        reconcile_drive_to_local(tmp_path, "drive_root_test_id", dry_run=True)
        # Trong dry-run, không tạo file vật lý
        assert not (tmp_path / "Toan_Cao_Cap.pdf").exists()
