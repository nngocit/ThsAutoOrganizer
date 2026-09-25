"""tests/test_owner_email_isolation.py — Test định danh đa người dùng cho NotebookLM."""

from unittest.mock import patch, MagicMock
import pytest
from plugins.base import EventBus
from plugins.notebooklm_cli import NotebookLMCLIPlugin
from local_agent.nlm_task_handler import handle_course_create, _run_nlm


def test_plugin_uses_profile_when_matched(tmp_path):
    """Khi task có owner_email khớp với profile trong config, truyền cờ --profile."""
    bus = EventBus()
    plugin = NotebookLMCLIPlugin(bus)

    mock_config = {
        "nlm_profiles": {
            "xuanngocit@gmail.com": "default",
        }
    }

    with patch("plugins.notebooklm_cli.get_config", return_value=mock_config), \
         patch.object(plugin, "_execute_cmd", return_value=(0, '{"id": "nb_123"}', "")) as mock_cmd:

        plugin.on_course_create({
            "id": "task_abc_1",
            "display_name": "Kiem Thu Phan Mem",
            "owner_email": "xuanngocit@gmail.com",
        })

        assert mock_cmd.called
        called_args = mock_cmd.call_args[0][0]
        assert "--profile" in called_args
        idx = called_args.index("--profile")
        assert called_args[idx + 1] == "default"


def test_plugin_warns_when_owner_email_differs_or_unmapped(caplog):
    """Khi task có owner_email không khớp profile nào, ném warning session mặc định."""
    bus = EventBus()
    plugin = NotebookLMCLIPlugin(bus)

    mock_config = {
        "nlm_profiles": {
            "xuanngocit@gmail.com": "default",
        }
    }

    with patch("plugins.notebooklm_cli.get_config", return_value=mock_config), \
         patch.object(plugin, "_execute_cmd", return_value=(0, '{"id": "nb_123"}', "")), \
         caplog.at_level("WARNING"):

        plugin.on_course_create({
            "id": "task_abc_2",
            "display_name": "He Chuyen Gia",
            "owner_email": "other_student@gmail.com",
        })

        assert any("Task thuộc về other_student@gmail.com, đang xử lý bằng Local Session mặc định của máy" in msg for msg in caplog.messages)


def test_nlm_task_handler_warns_when_owner_email_differs(caplog):
    """local_agent/nlm_task_handler cũng ném warning session mặc định khi email khác."""
    mock_config = {
        "nlm_profiles": {
            "xuanngocit@gmail.com": "default",
        },
        "local_base_path": "H:\\2026\\Thac Sy\\Mon_Hoc",
    }

    with patch("local_agent.nlm_task_handler.get_config", return_value=mock_config), \
         patch("local_agent.config_loader.get", side_effect=lambda k, d=None: mock_config.get(k, d)), \
         patch("local_agent.nlm_task_handler._nlm_available", return_value=True), \
         patch("local_agent.nlm_task_handler._run_nlm", return_value=(0, '{"id": "nb_xyz"}', "")), \
         patch("os.makedirs"), \
         caplog.at_level("WARNING"):

        handle_course_create({
            "id": "task_xyz",
            "display_name": "Mang May Tinh",
            "local_folder_name": "Mon_MangMayTinh",
            "owner_email": "stranger@gmail.com",
        })

        assert any("Task thuộc về stranger@gmail.com, đang xử lý bằng Local Session mặc định của máy" in msg for msg in caplog.messages)
