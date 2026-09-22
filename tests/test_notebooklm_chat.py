"""Unit tests for NotebookLM multi-turn chat and studio artifacts."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.database import Database
from src.notebooklm_sync import NotebookLMSyncManager


def test_database_chat_crud(tmp_path: Path):
    """Kiểm tra các thao tác CRUD phiên chat và tin nhắn trong Database."""
    db = Database(tmp_path / "test_chat.db")
    db.initialize()

    # 1. Tạo session
    session_id = db.create_chat_session(subject_id=1, title="Thảo luận NQ 27", conversation_id="conv-123")
    assert session_id > 0

    # 2. Lấy session
    session = db.get_chat_session(session_id)
    assert session is not None
    assert session["title"] == "Thảo luận NQ 27"
    assert session["conversation_id"] == "conv-123"

    # 3. Lấy theo conversation_id
    by_conv = db.get_chat_session_by_conversation_id("conv-123")
    assert by_conv is not None
    assert by_conv["id"] == session_id

    # 4. Lưu tin nhắn
    msg1 = db.save_chat_message(session_id, role="user", content="Xin chào")
    msg2 = db.save_chat_message(session_id, role="assistant", content="Chào bạn, tôi là Gemini", citations='[{"source":"A.pdf"}]')
    assert msg1 > 0
    assert msg2 > 0

    # 5. Lấy danh sách tin nhắn
    messages = db.get_chat_messages(session_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert "Gemini" in messages[1]["content"]

    # 6. Lấy danh sách sessions có kèm đếm tin nhắn
    sessions = db.get_chat_sessions(subject_id=1)
    assert len(sessions) == 1
    assert sessions[0]["message_count"] == 2

    # 7. Cập nhật session
    db.update_chat_session(session_id, title="Thảo luận NQ 27 (Đã đổi tên)")
    updated = db.get_chat_session(session_id)
    assert updated["title"] == "Thảo luận NQ 27 (Đã đổi tên)"

    # 8. Xóa session (CASCADE xóa tin nhắn)
    deleted = db.delete_chat_session(session_id)
    assert deleted is True
    assert db.get_chat_session(session_id) is None
    assert len(db.get_chat_messages(session_id)) == 0


def test_query_notebook_with_conversation_id(tmp_path: Path):
    """Kiểm tra query_notebook truyền đúng cờ --conversation-id."""
    db = Database(tmp_path / "test_query.db")
    db.initialize()
    mgr = NotebookLMSyncManager(database=db)

    with patch.object(mgr, "_run_cli") as mock_cli:
        mock_cli.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "answer": "Câu trả lời tiếp theo",
                "conversation_id": "conv-456",
                "citations": ["Trang 10"],
            }),
            stderr="",
        )
        res = mgr.query_notebook("nb-1", "Hỏi câu 2", conversation_id="conv-456")
        assert res["success"] is True
        assert res["conversation_id"] == "conv-456"
        assert res["answer"] == "Câu trả lời tiếp theo"

        # Kiểm tra CLI args
        call_args = mock_cli.call_args[0][0]
        assert "--conversation-id" in call_args
        assert "conv-456" in call_args


def test_sync_chats_from_notebook(tmp_path: Path):
    """Kiểm tra đồng bộ lịch sử hội thoại từ NotebookLM vào SQLite."""
    db = Database(tmp_path / "test_sync.db")
    db.initialize()
    mgr = NotebookLMSyncManager(database=db)

    with patch.object(mgr, "_run_cli") as mock_cli:
        def side_effect(args, **kwargs):
            if args[0] == "chats" and args[1] == "list":
                return MagicMock(returncode=0, stdout=json.dumps({
                    "sessions": [{"conversation_id": "cid-abc", "preview": "Hỏi về triết học"}]
                }))
            elif args[0] == "chats" and args[1] == "get":
                return MagicMock(returncode=0, stdout=json.dumps({
                    "transcript": [
                        {"turn": 1, "query": "NQ 27 là gì?", "answer": "Nghị quyết Trung ương 6"},
                    ]
                }))
            return MagicMock(returncode=1, stdout="", stderr="error")

        mock_cli.side_effect = side_effect
        sync_res = mgr.sync_chats_from_notebook("nb-abc", subject_id=1)
        assert sync_res["success"] is True
        assert sync_res["sessions"] == 1
        assert sync_res["messages"] == 2

        # Kiểm tra trong DB
        sessions = db.get_chat_sessions(1)
        assert len(sessions) == 1
        msgs = db.get_chat_messages(sessions[0]["id"])
        assert len(msgs) == 2
        assert msgs[0]["content"] == "NQ 27 là gì?"
        assert msgs[1]["content"] == "Nghị quyết Trung ương 6"


def test_sync_studio_artifacts(tmp_path: Path):
    """Kiểm tra đồng bộ và tải Studio Artifacts."""
    db = Database(tmp_path / "test_art.db")
    db.initialize()
    mgr = NotebookLMSyncManager(database=db)
    download_dir = tmp_path / "artifacts"

    with patch.object(mgr, "_run_cli") as mock_cli:
        def side_effect(args, **kwargs):
            if args[0] == "studio" and args[1] == "status":
                return MagicMock(returncode=0, stdout=json.dumps([
                    {
                        "id": "slide-xyz-1234",
                        "type": "slide_deck",
                        "status": "completed",
                        "custom_instructions": "Slide 3 luận điểm NQ 27",
                    }
                ]))
            elif args[0] == "download" and args[1] == "slide-deck":
                out_idx = args.index("--output") + 1
                out_path = Path(args[out_idx])
                out_path.write_bytes(b"PPTX-CONTENT")
                return MagicMock(returncode=0, stdout="Downloaded", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="error")

        mock_cli.side_effect = side_effect
        artifacts = mgr.sync_studio_artifacts("nb-abc", download_dir=download_dir)
        assert len(artifacts) == 1
        assert artifacts[0]["type"] == "slide_deck"
        assert artifacts[0]["filename"] == "slide_deck_slide-xy.pptx"
        assert artifacts[0]["download_url"] is not None
        assert (download_dir / "slide_deck_slide-xy.pptx").exists()


def test_web_server_chat_api(tmp_path: Path):
    """Kiểm tra các HTTP endpoints liên quan đến Chat đa phiên trên Web Server."""
    import urllib.request
    import urllib.error
    from src.web_server import start_web_server

    db = Database(tmp_path / "web_chat_test.db")
    db.initialize()
    # Tạo môn học mẫu
    sub_id = db.add_subject(major_id=1, code="TH01", name="Triết học", folder_name="Triet_Hoc")
    db.update_subject_notebooklm_id(sub_id, "nb-triet")

    mock_nlm = MagicMock()
    mock_nlm.query_notebook.return_value = {
        "success": True,
        "answer": "Trả lời về Triết học",
        "citations": [{"text": "Sách Triết:10"}],
        "conversation_id": "conv-test-999",
    }
    mock_nlm.sync_chats_from_notebook.return_value = {"success": True, "sessions": 1, "messages": 2}
    mock_nlm.sync_studio_artifacts.return_value = []

    server = start_web_server(
        port=0,
        database=db,
        drive_manager=None,
        config_path=tmp_path / "cfg.json",
        nlm_sync_manager=mock_nlm,
    )
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. POST /api/ai/chat/sessions
        req = urllib.request.Request(
            f"{base_url}/api/ai/chat/sessions",
            data=json.dumps({"subject_id": 1, "title": "Phiên 1"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            session_id = data["session_id"]

        # 2. GET /api/ai/chat/sessions
        with urllib.request.urlopen(f"{base_url}/api/ai/chat/sessions?subject_id=1") as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert len(data["sessions"]) == 1
            assert data["sessions"][0]["id"] == session_id

        # 3. POST /api/ai/chat/send
        req = urllib.request.Request(
            f"{base_url}/api/ai/chat/send",
            data=json.dumps({"session_id": session_id, "prompt": "Câu hỏi số 1"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data["answer"] == "Trả lời về Triết học"
            assert data["conversation_id"] == "conv-test-999"

        # 4. GET /api/ai/chat/messages
        with urllib.request.urlopen(f"{base_url}/api/ai/chat/messages?session_id={session_id}") as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert len(data["messages"]) == 2
            assert data["messages"][0]["role"] == "user"
            assert data["messages"][1]["role"] == "assistant"

        # 5. POST /api/ai/chat/sync-all
        req = urllib.request.Request(
            f"{base_url}/api/ai/chat/sync-all",
            data=json.dumps({"subject_id": 1}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data["chat_sync"]["success"] is True

        # 6. DELETE /api/ai/chat/sessions/{session_id}
        req = urllib.request.Request(
            f"{base_url}/api/ai/chat/sessions/{session_id}",
            method="DELETE",
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True

        # Xác nhận đã xóa
        with urllib.request.urlopen(f"{base_url}/api/ai/chat/sessions?subject_id=1") as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert len(data["sessions"]) == 0

    finally:
        server.shutdown()
        server.server_close()

