# tests/test_local_agent_nlm.py — Test bộ lọc file và auto-lookup notebook_id

import pytest
from unittest.mock import patch, MagicMock
from local_agent.nlm_task_handler import (
    SUPPORTED_EXTS,
    handle_source_add,
    lookup_notebook_id_from_course,
)
from local_agent.firestore_poller import FirestorePoller


def test_supported_exts_defined():
    """Kiểm tra biến SUPPORTED_EXTS đúng theo yêu cầu."""
    expected = ['.pdf', '.docx', '.pptx', '.txt', '.md', '.mp3']
    assert SUPPORTED_EXTS == expected


def test_handle_source_add_skips_unsupported_ext():
    """Nếu task chứa file không thuộc list SUPPORTED_EXTS -> trả về skipped_ext mà không gọi nlm."""
    task = {
        "filename": "screenshot.png",
        "notebook_id": "nb_123",
        "subject": "Triet Hoc",
    }
    with patch("local_agent.nlm_task_handler._run_nlm") as mock_run:
        res = handle_source_add(task)
        assert res == "skipped_ext"
        mock_run.assert_not_called()

    task_jpg = {
        "filename": "photo.jpg",
        "local_path": "H:/Mon_Hoc/photo.jpg",
    }
    with patch("local_agent.nlm_task_handler._run_nlm") as mock_run:
        res = handle_source_add(task_jpg)
        assert res == "skipped_ext"
        mock_run.assert_not_called()


def test_handle_source_add_auto_lookups_notebook_id_from_course():
    """Nếu thiếu notebook_id nhưng có course_id -> auto-lookup từ Firestore courses."""
    task = {
        "filename": "document.pdf",
        "course_id": "course_abc_123",
        "subject": "Triet Hoc",
        "local_path": "tests/test_classifier.py",  # dummy file tồn tại
    }

    with patch("local_agent.nlm_task_handler._nlm_available", return_value=True), \
         patch("local_agent.nlm_task_handler.lookup_notebook_id_from_course", return_value="nb_from_course_789") as mock_lookup, \
         patch("local_agent.nlm_task_handler._run_nlm", return_value=(0, '{"source_id": "src_ok"}', "")) as mock_run:

        res = handle_source_add(task)
        assert res == "src_ok"
        mock_lookup.assert_called_once_with("course_id_abc_123" if False else "course_abc_123", "")
        assert task["notebook_id"] == "nb_from_course_789"
        mock_run.assert_called_once()
        # Đối số gọi nlm phải chứa nb_from_course_789
        args = mock_run.call_args[0][0]
        assert "nb_from_course_789" in args


def test_handle_source_add_raises_value_error_if_no_notebook_id():
    """Nếu không có notebook_id và không lookup được từ course hay subject -> raise ValueError."""
    task = {
        "filename": "document.pdf",
        "course_id": "course_unknown",
        "subject": "",
        "local_path": "tests/test_classifier.py",
    }

    with patch("local_agent.nlm_task_handler._nlm_available", return_value=True), \
         patch("local_agent.nlm_task_handler.lookup_notebook_id_from_course", return_value=""):
        with pytest.raises(ValueError, match="source_add task thiếu notebook_id"):
            handle_source_add(task)


def test_firestore_poller_marks_skipped_ext():
    """Khi handler trả về skipped_ext, poller phải mark task với status 'skipped_ext'."""
    poller = FirestorePoller("nlm_task_queue")
    poller.register("source_add", lambda t: "skipped_ext")

    task = {"id": "task_1", "action": "source_add", "filename": "image.png"}

    with patch.object(poller, "_mark_task") as mock_mark:
        poller._process_task(task)
        # Lần 1: mark processing, Lần 2: mark skipped_ext
        assert mock_mark.call_count == 2
        mock_mark.assert_any_call("task_1", "processing")
        mock_mark.assert_any_call("task_1", "skipped_ext", result="skipped_ext")


def test_upload_file_sets_public_reader_permission():
    """upload_file trên Drive BẮT BUỘC gọi permissions().create(anyone, reader) và trả về webViewLink."""
    from local_agent.drive_sync import upload_file

    mock_service = MagicMock()
    mock_files = MagicMock()
    mock_permissions = MagicMock()
    mock_service.files.return_value = mock_files
    mock_service.permissions.return_value = mock_permissions

    mock_files.create.return_value.execute.return_value = {"id": "file_123", "name": "doc.pdf", "size": "1024"}
    mock_files.get.return_value.execute.return_value = {"id": "file_123", "webViewLink": "https://drive.google.com/file/d/file_123/view"}
    mock_permissions.create.return_value.execute.return_value = {"id": "perm_1"}

    with patch("local_agent.drive_sync._get_drive_service", return_value=mock_service), \
         patch("local_agent.drive_sync.ensure_folder_path", return_value="folder_parent_1"):
        res = upload_file("tests/test_classifier.py", folder_path="test", subject="Triet Hoc")

        # Kiểm tra permissions.create được gọi với type: anyone, role: reader
        mock_permissions.create.assert_called_once_with(
            fileId="file_123",
            body={"type": "anyone", "role": "reader"},
        )
        assert res["drive_file_id"] == "file_123"
        assert res["webViewLink"] == "https://drive.google.com/file/d/file_123/view"
        assert res["web_view_link"] == "https://drive.google.com/file/d/file_123/view"

