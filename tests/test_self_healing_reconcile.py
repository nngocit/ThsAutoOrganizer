"""tests/test_self_healing_reconcile.py — Kiểm thử tự động tính năng Self-Healing & Reconciliation
cho NotebookLMCLIPlugin (Mega Sprint 2).
"""

import json
import logging
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from plugins.base import EventBus, COLOR_PURPLE, COLOR_RED
from plugins.notebooklm_cli import NotebookLMCLIPlugin


@pytest.fixture
def event_bus():
    return EventBus()


# ==============================================================================
# TESTS CHO ON_TRIGGER_RECONCILE (Khám sức khỏe & đối chiếu)
# ==============================================================================

def test_reconcile_detects_missing_notebooks_and_sends_patch(event_bus, caplog):
    """Phát hiện ID có trong DB nhưng không có trên Google NotebookLM, gửi PATCH sync_status='missing_ai'."""
    plugin = NotebookLMCLIPlugin(event_bus)

    # Giả lập NotebookLM hiện chỉ còn cuốn nb_1 (cuốn nb_missing_2 đã bị xóa thủ công)
    active_nlm_list = json.dumps([
        {"id": "nb_1", "title": "Môn 1"}
    ])

    with patch.object(plugin, "_execute_cmd", return_value=(0, active_nlm_list, "")) as mock_cmd, \
         patch.object(plugin, "_send_reconcile_patch") as mock_patch:

        with caplog.at_level(logging.WARNING):
            event_bus.emit("ON_TRIGGER_RECONCILE", {
                "courses": [
                    {"id": "course_1", "notebooklm_id": "nb_1"},
                    {"id": "course_2", "notebooklm_id": "nb_missing_2"},
                ],
                "owner_email": "xuanngocit@gmail.com",
            })

            # Kiểm tra gọi CLI notebook list
            assert mock_cmd.called
            args = mock_cmd.call_args[0][0]
            assert "notebook" in args
            assert "list" in args

            # Kiểm tra gọi PATCH cho cuốn bị xóa tay
            assert mock_patch.called
            mock_patch.assert_called_with(course_id="course_2", missing_id="nb_missing_2", target_uid="")

            # Kiểm tra cảnh báo đỏ
            assert any("State Drift" in rec.message and COLOR_RED in rec.message for rec in caplog.records)


def test_reconcile_all_present_no_patch_needed(event_bus, caplog):
    """Khi tất cả notebook trong DB đều tồn tại trên Google, không gửi PATCH."""
    plugin = NotebookLMCLIPlugin(event_bus)

    active_nlm_list = json.dumps([
        {"id": "nb_1", "title": "Môn 1"},
        {"id": "nb_2", "title": "Môn 2"}
    ])

    with patch.object(plugin, "_execute_cmd", return_value=(0, active_nlm_list, "")) as mock_cmd, \
         patch.object(plugin, "_send_reconcile_patch") as mock_patch:

        with caplog.at_level(logging.INFO):
            event_bus.emit("ON_TRIGGER_RECONCILE", {
                "notebooklm_ids": ["nb_1", "nb_2"],
                "owner_email": "xuanngocit@gmail.com",
            })

            assert mock_cmd.called
            assert not mock_patch.called
            assert any("RECONCILE OK" in rec.message for rec in caplog.records)


# ==============================================================================
# TESTS CHO ON_FORCE_REINDEX (Nạp lại toàn bộ file tài liệu)
# ==============================================================================

def test_force_reindex_scans_docs_and_adds_sources(event_bus, tmp_path, caplog):
    """Quét các file .pdf, .txt, .docx trong thư mục local và nạp lại vào NotebookLM trên Thread ngầm."""
    plugin = NotebookLMCLIPlugin(event_bus)

    # Tạo thư mục và tài liệu giả lập
    course_folder = tmp_path / "Mon_Mang_May_Tinh"
    course_folder.mkdir()
    (course_folder / "slide1.pdf").write_text("dummy pdf", encoding="utf-8")
    (course_folder / "notes.txt").write_text("dummy txt", encoding="utf-8")
    (course_folder / "de_cuong.docx").write_text("dummy docx", encoding="utf-8")
    (course_folder / "image.png").write_text("dummy image", encoding="utf-8")  # Không thuộc target

    with patch.object(plugin, "_execute_cmd", return_value=(0, '{"status": "ok"}', "")) as mock_cmd, \
         patch("plugins.notebooklm_cli.get_config", return_value={"local_base_path": str(tmp_path)}):

        with caplog.at_level(logging.INFO):
            event_bus.emit("ON_FORCE_REINDEX", {
                "notebooklm_id": "nb_reindex_100",
                "local_folder_name": "Mon_Mang_May_Tinh",
                "owner_email": "xuanngocit@gmail.com",
            })

            # Chờ một chút để background thread chạy xong
            time.sleep(0.3)

            # Kiểm tra gọi nlm source add
            assert mock_cmd.called
            all_calls = [call[0][0] for call in mock_cmd.call_args_list]

            # Phải có 3 lần gọi cho 3 file: .pdf, .txt, .docx
            assert len(all_calls) == 3
            added_files = [str(call[call.index("--file") + 1]) for call in all_calls if "--file" in call]
            assert any("slide1.pdf" in f for f in added_files)
            assert any("notes.txt" in f for f in added_files)
            assert any("de_cuong.docx" in f for f in added_files)
            assert not any("image.png" in f for f in added_files)

            # Kiểm tra log màu tím "Đã khôi phục AI Context thành công"
            assert any("Đã khôi phục AI Context thành công" in rec.message and COLOR_PURPLE in rec.message for rec in caplog.records)


def test_force_reindex_ignores_file_already_exists(event_bus, tmp_path, caplog):
    """Bỏ qua lỗi File already exists một cách êm thấm, không dừng tiến trình."""
    plugin = NotebookLMCLIPlugin(event_bus)

    course_folder = tmp_path / "Mon_CSDL"
    course_folder.mkdir()
    (course_folder / "bai1.pdf").write_text("pdf content", encoding="utf-8")

    # Giả lập CLI ném lỗi "File already exists"
    with patch.object(plugin, "_execute_cmd", return_value=(1, "", "Error: File already exists in this notebook")), \
         patch("plugins.notebooklm_cli.get_config", return_value={"local_base_path": str(tmp_path)}):

        with caplog.at_level(logging.INFO):
            event_bus.emit("ON_FORCE_REINDEX", {
                "notebooklm_id": "nb_reindex_200",
                "local_folder_name": "Mon_CSDL",
            })

            time.sleep(0.3)

            # Đã bắt lỗi êm thấm và ghi log bỏ qua
            assert any("Bỏ qua file đã tồn tại" in rec.message for rec in caplog.records)
            assert any("Đã khôi phục AI Context thành công" in rec.message for rec in caplog.records)


def test_reconcile_patch_network_failure_resilience(event_bus, caplog):
    """Khi mạng chập chờn hoặc request PATCH gặp lỗi, plugin không bao giờ bị văng Exception."""
    plugin = NotebookLMCLIPlugin(event_bus)

    with patch.object(plugin, "_execute_cmd", return_value=(0, "[]", "")), \
         patch("requests.patch", side_effect=Exception("Connection refused")), \
         patch("plugins.notebooklm_cli.get_config", return_value={"worker_url": "https://fake.workers.dev"}):

        with caplog.at_level(logging.ERROR):
            event_bus.emit("ON_TRIGGER_RECONCILE", {
                "notebooklm_ids": ["nb_unreachable_1"],
            })

        # Không crash và ghi log lỗi rõ ràng
        assert any("Lỗi khi gửi PATCH reconcile" in rec.message for rec in caplog.records)


def test_reconcile_cli_error_does_not_crash(event_bus, caplog):
    """Khi CLI trả về mã lỗi, on_trigger_reconcile dừng an toàn và log ERROR."""
    plugin = NotebookLMCLIPlugin(event_bus)

    with patch.object(plugin, "_execute_cmd", return_value=(1, "", "Session expired")):
        with caplog.at_level(logging.ERROR):
            event_bus.emit("ON_TRIGGER_RECONCILE", {
                "notebooklm_ids": ["nb_123"],
            })

        assert any("Không thể lấy danh sách sổ" in rec.message for rec in caplog.records)


def test_force_reindex_nonexistent_folder_handled(event_bus, tmp_path, caplog):
    """Khi folder local không tồn tại, log cảnh báo và không văng lỗi."""
    plugin = NotebookLMCLIPlugin(event_bus)

    with patch("plugins.notebooklm_cli.get_config", return_value={"local_base_path": str(tmp_path)}):
        with caplog.at_level(logging.WARNING):
            event_bus.emit("ON_FORCE_REINDEX", {
                "notebooklm_id": "nb_not_found",
                "local_folder_name": "Thu_Muc_Ao_Khong_Ton_Tai",
            })

            time.sleep(0.2)
            assert any("không tồn tại để reindex" in rec.message for rec in caplog.records)


def test_reconcile_empty_payload_handled(event_bus):
    """Payload rỗng không gây lỗi."""
    plugin = NotebookLMCLIPlugin(event_bus)
    event_bus.emit("ON_TRIGGER_RECONCILE", {})
    event_bus.emit("ON_TRIGGER_RECONCILE", {"courses": []})
    event_bus.emit("ON_FORCE_REINDEX", {})
