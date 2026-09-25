# tests/test_local_agent_nlm.py — Test bộ lọc file và auto-lookup notebook_id

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from local_agent.nlm_task_handler import (
    SUPPORTED_EXTS,
    handle_source_add,
    handle_course_create,
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


def test_handle_source_add_avoids_drive_url_and_uses_file(tmp_path):
    """Tệp tin Drive: Bắt buộc dùng flag --file (tải về trước) và TUYỆT ĐỐI không dùng --url để tránh bị Google bot block."""
    local_file = tmp_path / "de_cuong.pdf"
    local_file.write_bytes(b"PDF CONTENT" * 50)

    task = {
        "filename": "de_cuong.pdf",
        "notebook_id": "nb_triet_hoc_123",
        "course_id": "course_triet_hoc_123",
        "drive_file_id": "1UTcXSlhYKXuIpVObDzZ6ejKxINdxkQrd",
        "drive_view_link": "https://drive.google.com/file/d/1UTcXSlhYKXuIpVObDzZ6ejKxINdxkQrd/view",
        "subject": "Triết học",
        "local_path": str(local_file),
    }

    with patch("local_agent.nlm_task_handler._nlm_available", return_value=True), \
         patch("local_agent.nlm_task_handler._run_nlm", return_value=(0, '{"source_id": "src_file_456"}', "")) as mock_run:

        res = handle_source_add(task)
        assert res == "src_file_456"
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        # Bắt buộc dùng flag --file
        assert "--file" in args
        assert str(local_file.resolve()) in args
        # Tuyệt đối không dùng --url cho link drive.google.com
        assert "--url" not in args


def test_handle_source_add_uses_url_for_generic_web():
    """Với Web URL công khai (không phải drive.google.com), sử dụng cờ --url bình thường."""
    task = {
        "filename": "article",
        "notebook_id": "nb_web_123",
        "course_id": "course_web_123",
        "url": "https://vietnamnet.vn/giao-duc-thac-si-2026.html",
        "subject": "Tin tức",
        "local_path": "tests/test_classifier.py",
    }

    with patch("local_agent.nlm_task_handler._nlm_available", return_value=True), \
         patch("local_agent.nlm_task_handler._run_nlm", return_value=(0, '{"source_id": "src_web_789"}', "")) as mock_run:

        res = handle_source_add(task)
        assert res == "src_web_789"
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "--url" in args
        assert "https://vietnamnet.vn/giao-duc-thac-si-2026.html" in args


def test_handle_source_add_downloads_if_local_not_present(tmp_path):
    """Khi local file chưa tồn tại trên đĩa, tự động tải qua drive_sync trước khi nạp vào NLM."""
    dest_file = tmp_path / "sach_giao_trinh.pdf"

    task = {
        "filename": "sach_giao_trinh.pdf",
        "notebook_id": "nb_999",
        "course_id": "course_triet_hoc_123",
        "drive_file_id": "drive_id_xyz",
        "subject": "Triết học",
        "local_path": str(dest_file),
    }

    def fake_download(drive_id, dest):
        dest.write_bytes(b"DOWNLOADED_PDF")
        return dest

    with patch("local_agent.nlm_task_handler._nlm_available", return_value=True), \
         patch("local_agent.drive_sync.download_file", side_effect=fake_download) as mock_dl, \
         patch("local_agent.nlm_task_handler._run_nlm", return_value=(0, '{"source_id": "src_ok"}', "")) as mock_run:

        res = handle_source_add(task)
        assert res == "src_ok"
        assert mock_dl.called
        assert dest_file.exists()
        args = mock_run.call_args[0][0]
        assert "--file" in args


def test_handle_source_add_skips_when_course_id_empty():
    """Bỏ qua nạp NLM và trả về skipped_no_course nếu course_id rỗng hoặc None."""
    task = {
        "id": "task_no_course_1",
        "filename": "tailieu.pdf",
        "course_id": "",
        "subject": "Tài liệu chung",
    }
    with patch("requests.patch") as mock_patch:
        res = handle_source_add(task)
        assert res == "skipped_no_course"
        # Phải cập nhật task status skipped_no_course lên Worker API
        mock_patch.assert_called_once()
        args, kwargs = mock_patch.call_args
        assert "task_no_course_1" in args[0]
        assert kwargs["json"]["status"] == "skipped_no_course"


def test_handle_source_add_skips_when_subject_tai_lieu_chung():
    """Bỏ qua nạp NLM nếu subject là 'Tài liệu chung' kể cả khi có course_id."""
    task = {
        "filename": "Chuong_trinh_khung.pdf",
        "course_id": "some_id",
        "subject": "Tài liệu chung",
    }
    res = handle_source_add(task)
    assert res == "skipped_no_course"


def test_firestore_poller_marks_skipped_no_course():
    """Khi handler trả về skipped_no_course, poller phải mark task với status 'skipped_no_course'."""
    poller = FirestorePoller("nlm_task_queue")
    poller.register("source_add", lambda t: "skipped_no_course")

    task = {"id": "task_no_course_2", "action": "source_add", "filename": "quyche.pdf"}

    with patch.object(poller, "_mark_task") as mock_mark:
        poller._process_task(task)
        # Lần 1: mark processing, Lần 2: mark skipped_no_course
        assert mock_mark.call_count == 2
        mock_mark.assert_any_call("task_no_course_2", "processing")
        mock_mark.assert_any_call("task_no_course_2", "skipped_no_course", result="skipped_no_course")


def test_sync_remote_config_updates_runtime_config():
    """sync_remote_config kéo cấu hình từ Cloud và merge vào config runtime."""
    from local_agent.config_loader import sync_remote_config, get

    mock_remote = {
        "config": {
            "local_base_path": "E:\\New_Folder_2026",
            "google_drive_root_folder_id": "remote_drive_root_999",
            "file_watcher_enabled": True,
        }
    }

    with patch("local_agent.api_client.get_system_config", return_value=mock_remote):
        cfg = sync_remote_config()
        assert cfg["local_base_path"] == "E:\\New_Folder_2026"
        assert get("local_base_path") == "E:\\New_Folder_2026"
        assert get("google_drive_root_folder_id") == "remote_drive_root_999"


def test_send_log_posts_to_worker_api():
    """send_log gọi _post tới /api/logs với payload đầy đủ."""
    from local_agent.api_client import send_log

    with patch("local_agent.api_client._post") as mock_post:
        mock_post.return_value = {"status": "created", "log_id": "log_123"}
        res = send_log(
            level="ERROR",
            module="nlm_task_handler",
            message="Test error message",
            subject="Triết học",
            file_name="de_cuong.pdf",
        )
        assert res["status"] == "created"
        mock_post.assert_called_once()
        path, payload = mock_post.call_args[0]
        assert path == "/api/logs"
        assert payload["level"] == "ERROR"
        assert payload["module"] == "nlm_task_handler"
        assert payload["message"] == "Test error message"


def test_handle_course_create(tmp_path: Path):
    """Kiểm tra handle_course_create chạy nlm notebook create và tạo thư mục local."""
    task = {
        "action": "course_create",
        "course_id": "course_123",
        "display_name": "Kiến Trúc Phần Mềm",
        "local_folder_name": "Kien_Truc_Phan_Mem",
        "uid": "user_test_456",
    }
    with patch("local_agent.nlm_task_handler._nlm_available", return_value=True), \
         patch("local_agent.nlm_task_handler._run_nlm", return_value=(0, '{"id": "nb_ktpm_999"}', "")) as mock_run, \
         patch("local_agent.config_loader.get", return_value=str(tmp_path)), \
         patch("local_agent.api_client._request") as mock_api:

        res = handle_course_create(task)
        assert res == "nb_ktpm_999"
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["notebook", "create", "Kiến Trúc Phần Mềm", "--json"]
        # Thư mục local phải được tạo ra
        created_folder = tmp_path / "Kien_Truc_Phan_Mem"
        assert created_folder.exists()
        # API PUT /api/courses/:id/notebooklm phải được gọi kèm uid
        mock_api.assert_called_once()
        method, url, data = mock_api.call_args[0]
        assert method == "PUT"
        assert "/api/courses/course_123/notebooklm?uid=user_test_456" in url
        assert data["notebooklm_id"] == "nb_ktpm_999"
        assert data["status"] == "active"
        assert data["uid"] == "user_test_456"



