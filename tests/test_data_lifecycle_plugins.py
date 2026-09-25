"""tests/test_data_lifecycle_plugins.py — Test vòng đời dữ liệu (Archive, Restore, Hard Delete)
cho LocalStoragePlugin và NotebookLMCLIPlugin.
"""

import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from plugins.base import EventBus
from plugins.local_storage import LocalStoragePlugin
from plugins.notebooklm_cli import NotebookLMCLIPlugin


@pytest.fixture
def event_bus():
    return EventBus()


# ==============================================================================
# TESTS CHO LOCAL_STORAGE PLUGIN
# ==============================================================================

def test_local_storage_archive_moves_folder_to_archived(event_bus, tmp_path):
    """ON_COURSE_ARCHIVE: di chuyển thư mục vào _Archived/<folder_name> mà KHÔNG xóa."""
    plugin = LocalStoragePlugin(event_bus, base_path=str(tmp_path))

    # Tạo thư mục môn học giả lập
    course_dir = tmp_path / "Mon_Toan_Roi_Rac"
    course_dir.mkdir()
    sample_file = course_dir / "bai_giang_1.pdf"
    sample_file.write_text("dummy pdf content", encoding="utf-8")

    event_bus.emit("ON_COURSE_ARCHIVE", {
        "local_folder_name": "Mon_Toan_Roi_Rac",
        "course_id": "course_101",
    })

    # Thư mục gốc không còn
    assert not course_dir.exists()
    # Thư mục đã chuyển vào _Archived
    archived_dir = tmp_path / "_Archived" / "Mon_Toan_Roi_Rac"
    assert archived_dir.exists()
    assert (archived_dir / "bai_giang_1.pdf").read_text(encoding="utf-8") == "dummy pdf content"


def test_local_storage_restore_moves_folder_back(event_bus, tmp_path):
    """ON_COURSE_RESTORE: di chuyển thư mục từ _Archived trở lại vị trí gốc."""
    plugin = LocalStoragePlugin(event_bus, base_path=str(tmp_path))

    # Tạo thư mục đang nằm trong _Archived
    archived_dir = tmp_path / "_Archived" / "Mon_Kien_Truc_May_Tinh"
    archived_dir.mkdir(parents=True)
    sample_file = archived_dir / "slide_01.pptx"
    sample_file.write_text("dummy pptx", encoding="utf-8")

    event_bus.emit("ON_COURSE_RESTORE", {
        "local_folder_name": "Mon_Kien_Truc_May_Tinh",
        "course_id": "course_102",
    })

    # Đã dời khỏi _Archived
    assert not archived_dir.exists()
    # Đã trở lại vị trí gốc
    restored_dir = tmp_path / "Mon_Kien_Truc_May_Tinh"
    assert restored_dir.exists()
    assert (restored_dir / "slide_01.pptx").read_text(encoding="utf-8") == "dummy pptx"


def test_local_storage_hard_delete_purges_archived_folder(event_bus, tmp_path):
    """ON_COURSE_HARD_DELETE: dùng shutil.rmtree xóa sạch thư mục trong _Archived."""
    plugin = LocalStoragePlugin(event_bus, base_path=str(tmp_path))

    # Tạo thư mục trong _Archived
    archived_dir = tmp_path / "_Archived" / "Mon_Xoa_Vinh_Vien"
    archived_dir.mkdir(parents=True)
    (archived_dir / "file.txt").write_text("bye", encoding="utf-8")

    event_bus.emit("ON_COURSE_HARD_DELETE", {
        "local_folder_name": "Mon_Xoa_Vinh_Vien",
        "course_id": "course_103",
    })

    assert not archived_dir.exists()


# ==============================================================================
# TESTS CHO NOTEBOOKLM_CLI PLUGIN
# ==============================================================================

def test_notebooklm_cli_archive_renames_notebook(event_bus):
    """ON_COURSE_ARCHIVE: gọi CLI rename thêm tiền tố '[LƯU TRỮ] - '."""
    plugin = NotebookLMCLIPlugin(event_bus)

    with patch.object(plugin, "_execute_cmd", return_value=(0, '{"status": "ok"}', "")) as mock_cmd:
        event_bus.emit("ON_COURSE_ARCHIVE", {
            "notebooklm_id": "nb_archive_123",
            "display_name": "Hệ Cơ Sở Dữ Liệu",
            "owner_email": "xuanngocit@gmail.com",
        })

        assert mock_cmd.called
        args = mock_cmd.call_args[0][0]
        assert "notebook" in args
        assert "rename" in args
        assert "nb_archive_123" in args
        assert "[LƯU TRỮ] - Hệ Cơ Sở Dữ Liệu" in args


def test_notebooklm_cli_restore_renames_notebook_clean(event_bus):
    """ON_COURSE_RESTORE: gọi CLI rename gỡ tiền tố '[LƯU TRỮ] - '."""
    plugin = NotebookLMCLIPlugin(event_bus)

    with patch.object(plugin, "_execute_cmd", return_value=(0, '{"status": "ok"}', "")) as mock_cmd:
        event_bus.emit("ON_COURSE_RESTORE", {
            "notebooklm_id": "nb_restore_456",
            "display_name": "[LƯU TRỮ] - Trí Tuệ Nhân Tạo",
            "owner_email": "xuanngocit@gmail.com",
        })

        assert mock_cmd.called
        args = mock_cmd.call_args[0][0]
        assert "notebook" in args
        assert "rename" in args
        assert "nb_restore_456" in args
        assert "Trí Tuệ Nhân Tạo" in args
        assert "[LƯU TRỮ] -" not in args[args.index("nb_restore_456") + 1]


def test_notebooklm_cli_hard_delete_purges_notebook(event_bus):
    """ON_COURSE_HARD_DELETE: gọi CLI delete cuốn sổ hoàn toàn."""
    plugin = NotebookLMCLIPlugin(event_bus)

    with patch.object(plugin, "_execute_cmd", return_value=(0, '{"status": "deleted"}', "")) as mock_cmd:
        event_bus.emit("ON_COURSE_HARD_DELETE", {
            "notebooklm_id": "nb_purge_789",
            "owner_email": "xuanngocit@gmail.com",
        })

        assert mock_cmd.called
        args = mock_cmd.call_args[0][0]
        assert "notebook" in args
        assert "delete" in args
        assert "nb_purge_789" in args
        assert "--confirm" in args


# ==============================================================================
# TESTS EDGE CASES & COLOR LOGGING
# ==============================================================================

def test_local_storage_archive_handles_collision(event_bus, tmp_path):
    """Nếu thư mục trong _Archived đã tồn tại trước đó, ghi đè an toàn."""
    plugin = LocalStoragePlugin(event_bus, base_path=str(tmp_path))

    # Thư mục gốc mới
    source_dir = tmp_path / "Mon_X"
    source_dir.mkdir()
    (source_dir / "new.txt").write_text("new content", encoding="utf-8")

    # Thư mục cũ còn sót lại trong _Archived
    old_archived = tmp_path / "_Archived" / "Mon_X"
    old_archived.mkdir(parents=True)
    (old_archived / "old.txt").write_text("old content", encoding="utf-8")

    event_bus.emit("ON_COURSE_ARCHIVE", {"local_folder_name": "Mon_X"})

    assert not source_dir.exists()
    assert old_archived.exists()
    assert (old_archived / "new.txt").exists()
    assert not (old_archived / "old.txt").exists()


def test_local_storage_nonexistent_sources_do_not_crash(event_bus, tmp_path):
    """Nếu thư mục không tồn tại khi archive, restore hoặc hard delete thì không crash."""
    plugin = LocalStoragePlugin(event_bus, base_path=str(tmp_path))

    # Không có thư mục nào tồn tại
    event_bus.emit("ON_COURSE_ARCHIVE", {"local_folder_name": "Non_Existent"})
    event_bus.emit("ON_COURSE_RESTORE", {"local_folder_name": "Non_Existent"})
    event_bus.emit("ON_COURSE_HARD_DELETE", {"local_folder_name": "Non_Existent"})


def test_notebooklm_cli_handles_cli_error_gracefully(event_bus, caplog):
    """Khi nlm CLI trả về lỗi hoặc ngoại lệ, plugin bắt try/except không làm crash EventBus."""
    import logging
    plugin = NotebookLMCLIPlugin(event_bus)

    with patch.object(plugin, "_execute_cmd", return_value=(1, "", "Error: Notebook not found")):
        with caplog.at_level(logging.ERROR):
            event_bus.emit("ON_COURSE_ARCHIVE", {"notebooklm_id": "nb_bad", "display_name": "Toan"})
            event_bus.emit("ON_COURSE_RESTORE", {"notebooklm_id": "nb_bad", "display_name": "Toan"})
            event_bus.emit("ON_COURSE_HARD_DELETE", {"notebooklm_id": "nb_bad"})

    # EventBus hoạt động bình thường, không exception bung ra ngoài


def test_colored_log_indicators(event_bus, tmp_path, caplog):
    """Kiểm tra log chứa mã màu và nhãn [ARCHIVE] (cam), [RESTORE] (xanh), [PURGE] (đỏ)."""
    import logging
    from plugins.base import COLOR_ORANGE, COLOR_GREEN, COLOR_RED

    storage = LocalStoragePlugin(event_bus, base_path=str(tmp_path))
    cli = NotebookLMCLIPlugin(event_bus)

    # 1. Archive
    d = tmp_path / "Mon_Log_Test"
    d.mkdir()
    with patch.object(cli, "_execute_cmd", return_value=(0, "ok", "")):
        with caplog.at_level(logging.INFO):
            event_bus.emit("ON_COURSE_ARCHIVE", {
                "local_folder_name": "Mon_Log_Test",
                "notebooklm_id": "nb_log_1",
                "display_name": "Mon_Log_Test"
            })
            archive_logs = [rec.message for rec in caplog.records]
            assert any("[ARCHIVE]" in msg and COLOR_ORANGE in msg for msg in archive_logs)

    # 2. Restore
    caplog.clear()
    with patch.object(cli, "_execute_cmd", return_value=(0, "ok", "")):
        with caplog.at_level(logging.INFO):
            event_bus.emit("ON_COURSE_RESTORE", {
                "local_folder_name": "Mon_Log_Test",
                "notebooklm_id": "nb_log_1",
                "display_name": "[LƯU TRỮ] - Mon_Log_Test"
            })
            restore_logs = [rec.message for rec in caplog.records]
            assert any("[RESTORE]" in msg and COLOR_GREEN in msg for msg in restore_logs)

    # 3. Hard Delete (Purge)
    # Di chuyển lại vào archive để purge
    event_bus.emit("ON_COURSE_ARCHIVE", {"local_folder_name": "Mon_Log_Test"})
    caplog.clear()
    with patch.object(cli, "_execute_cmd", return_value=(0, "ok", "")):
        with caplog.at_level(logging.INFO):
            event_bus.emit("ON_COURSE_HARD_DELETE", {
                "local_folder_name": "Mon_Log_Test",
                "notebooklm_id": "nb_log_1",
            })
            purge_logs = [rec.message for rec in caplog.records]
            assert any("[PURGE]" in msg and COLOR_RED in msg for msg in purge_logs)
