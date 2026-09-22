"""Unit tests cho module đồng bộ NotebookLM ngầm (src/notebooklm_sync.py)."""

from pathlib import Path
import time
from unittest.mock import MagicMock, patch

from src.database import Database
from src.notebooklm_sync import NotebookLMSyncManager, SUPPORTED_EXTENSIONS


def test_check_cli_status_installed(tmp_path: Path):
    db = Database(tmp_path / "sync_test.db")
    db.initialize()
    manager = NotebookLMSyncManager(database=db, executable="nlm")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="nlm v0.2.0\n", stderr="")
        status = manager.check_cli_status()
        assert status["installed"] is True
        assert "0.2.0" in status["version"]


def test_check_cli_status_not_installed(tmp_path: Path):
    db = Database(tmp_path / "sync_test.db")
    db.initialize()
    manager = NotebookLMSyncManager(database=db, executable="nlm_non_existent")

    with patch("subprocess.run", side_effect=FileNotFoundError):
        status = manager.check_cli_status()
        assert status["installed"] is False
        assert status["authenticated"] is False


def test_ensure_notebook_for_course_cached(tmp_path: Path):
    db = Database(tmp_path / "sync_test.db")
    db.initialize()
    majors = db.get_all_majors()
    httt = next(m for m in majors if m["code"] == "HTTT")
    subjects = db.get_subjects_by_major(httt["id"])
    subject = subjects[0]
    subject_id = subject["id"]
    subject_name = subject["name"]

    db.update_subject_notebooklm_id(subject_id, "cached_id_999")
    manager = NotebookLMSyncManager(database=db)
    nb_id = manager.ensure_notebook_for_course(subject_name, subject_id)
    assert nb_id == "cached_id_999"


def test_ensure_notebook_for_course_creates_new(tmp_path: Path):
    db = Database(tmp_path / "sync_test.db")
    db.initialize()
    majors = db.get_all_majors()
    httt = next(m for m in majors if m["code"] == "HTTT")
    subjects = db.get_subjects_by_major(httt["id"])
    subject = subjects[0]
    subject_id = subject["id"]
    subject_name = subject["name"]

    manager = NotebookLMSyncManager(database=db)

    # Mock list (rỗng) và create
    with patch("subprocess.run") as mock_run:
        # Lần 1 list -> không thấy notebook
        # Lần 2 create -> trả về id
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="[]", stderr=""),
            MagicMock(returncode=0, stdout="Created notebook with ID: nlm_created_888", stderr=""),
        ]
        nb_id = manager.ensure_notebook_for_course(subject_name, subject_id)
        assert nb_id == "nlm_created_888"
        # Kiểm tra db đã lưu id
        assert db.get_subject_notebooklm_id(subject_id) == "nlm_created_888"


def test_sync_file_supported_extension(tmp_path: Path):
    db = Database(tmp_path / "sync_test.db")
    db.initialize()
    majors = db.get_all_majors()
    httt = next(m for m in majors if m["code"] == "HTTT")
    subjects = db.get_subjects_by_major(httt["id"])
    subject = subjects[0]
    subject_id = subject["id"]
    subject_name = subject["name"]
    db.update_subject_notebooklm_id(subject_id, "nb_123")

    manager = NotebookLMSyncManager(database=db)
    sample_file = tmp_path / "test_slide.pdf"
    sample_file.write_text("dummy content")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Source added successfully", stderr="")
        success = manager.sync_file_to_notebook(str(sample_file), subject_name, subject_id)
        assert success is True
        logs = db.get_notebooklm_sync_logs()
        assert len(logs) == 1
        assert logs[0]["status"] == "synced"


def test_sync_file_unsupported_extension_skipped(tmp_path: Path):
    db = Database(tmp_path / "sync_test.db")
    db.initialize()
    majors = db.get_all_majors()
    httt = next(m for m in majors if m["code"] == "HTTT")
    subjects = db.get_subjects_by_major(httt["id"])
    subject = subjects[0]
    subject_id = subject["id"]
    subject_name = subject["name"]

    manager = NotebookLMSyncManager(database=db)
    code_file = tmp_path / "main.py"
    code_file.write_text("print('hello')")

    success = manager.sync_file_to_notebook(str(code_file), subject_name, subject_id)
    assert success is False
    logs = db.get_notebooklm_sync_logs()
    assert len(logs) == 1
    assert logs[0]["status"] == "skipped"


def test_query_notebook(tmp_path: Path):
    db = Database(tmp_path / "sync_test.db")
    db.initialize()
    manager = NotebookLMSyncManager(database=db)

    with patch("subprocess.run") as mock_run:
        mock_stdout = "Dưới đây là 3 luận điểm chính:\n1. Điểm 1\n2. Điểm 2\n[Citations: Triet_hoc.pdf, p. 15]"
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_stdout, stderr="")
        res = manager.query_notebook("nb_123", "Nêu các luận điểm chính")
        assert res["success"] is True
        assert "Dưới đây là 3 luận điểm chính" in res["answer"]
        assert len(res["citations"]) >= 1


def test_enqueue_sync_background(tmp_path: Path):
    db = Database(tmp_path / "sync_test.db")
    db.initialize()
    majors = db.get_all_majors()
    httt = next(m for m in majors if m["code"] == "HTTT")
    subjects = db.get_subjects_by_major(httt["id"])
    subject = subjects[0]
    subject_id = subject["id"]
    subject_name = subject["name"]
    db.update_subject_notebooklm_id(subject_id, "nb_123")

    manager = NotebookLMSyncManager(database=db)
    sample_file = tmp_path / "async_doc.docx"
    sample_file.write_text("dummy")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Source added", stderr="")
        manager.enqueue_sync(str(sample_file), subject_name, subject_id)
        # Đợi threadpool thực thi
        time.sleep(0.5)
        logs = db.get_notebooklm_sync_logs()
        assert len(logs) == 1
        assert logs[0]["status"] == "synced"
