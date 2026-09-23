# tests/test_plugins_event_driven.py — Kiểm thử tự động bộ 3 Plugin Event-Driven (<200 dòng)
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from plugins.base import EventBus, PluginBase
from plugins.firestore_poller import FirestorePollerPlugin
from plugins.notebooklm_cli import NotebookLMCLIPlugin
from plugins.local_storage import LocalStoragePlugin


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="test_local_storage_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


class TestEventBus:
    def test_emit_and_subscribe(self, bus: EventBus):
        received = []
        bus.on("TEST_EVENT", lambda p: received.append(p))
        bus.emit("TEST_EVENT", {"hello": "world"})
        assert len(received) == 1
        assert received[0] == {"hello": "world"}

    def test_exception_isolation(self, bus: EventBus):
        received = []

        def broken_handler(p):
            raise RuntimeError("Crash!")

        bus.on("EVENT", broken_handler)
        bus.on("EVENT", lambda p: received.append(p))

        # Emit không được crash dù có handler ném ngoại lệ
        bus.emit("EVENT", {"status": "ok"})
        assert len(received) == 1
        assert received[0] == {"status": "ok"}

    def test_unsubscribe(self, bus: EventBus):
        received = []
        handler = lambda p: received.append(p)
        bus.on("EV", handler)
        bus.emit("EV", 1)
        bus.off("EV", handler)
        bus.emit("EV", 2)
        assert received == [1]


class TestFirestorePollerPlugin:
    def test_poll_course_create(self, bus: EventBus):
        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.id = "task_001"
        mock_doc.to_dict.return_value = {
            "action": "course_create",
            "display_name": "Triết học Mác",
            "local_folder_name": "01_Triet_Hoc",
            "status": "pending",
        }
        mock_db.collection.return_value.where.return_value.stream.return_value = [mock_doc]

        poller = FirestorePollerPlugin(bus, db=mock_db, poll_interval=1.0)

        emitted = []
        bus.on("ON_COURSE_CREATE", lambda p: emitted.append(p))

        poller.poll_once()

        # Kiểm tra đã update status='processing'
        mock_db.collection.return_value.document.return_value.update.assert_called()
        # Kiểm tra sự kiện đã phát ra bus
        assert len(emitted) == 1
        assert emitted[0]["id"] == "task_001"
        assert emitted[0]["display_name"] == "Triết học Mác"

    def test_poll_source_add(self, bus: EventBus):
        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.id = "task_002"
        mock_doc.to_dict.return_value = {
            "action": "source_add",
            "file_url": "https://example.com/test.pdf",
            "notebooklm_id": "nb_123",
            "local_folder_name": "02_Toan",
            "status": "pending",
        }
        mock_db.collection.return_value.where.return_value.stream.return_value = [mock_doc]

        poller = FirestorePollerPlugin(bus, db=mock_db)
        emitted = []
        bus.on("ON_SOURCE_ADD", lambda p: emitted.append(p))

        poller.poll_once()

        assert len(emitted) == 1
        assert emitted[0]["id"] == "task_002"
        assert emitted[0]["notebooklm_id"] == "nb_123"

    def test_on_task_completed(self, bus: EventBus):
        mock_db = MagicMock()
        poller = FirestorePollerPlugin(bus, db=mock_db)

        # Phát sự kiện TASK_COMPLETED
        bus.emit("TASK_COMPLETED", {"task_id": "task_001", "plugin": "AI_CLI"})

        # Xác nhận cập nhật status='completed' trên doc Firestore
        doc_mock = mock_db.collection.return_value.document.return_value
        doc_mock.update.assert_called()
        call_args = doc_mock.update.call_args[0][0]
        assert call_args["status"] == "completed"
        assert call_args["completed_by"] == "AI_CLI"


class TestNotebookLMCLIPlugin:
    @patch("subprocess.run")
    def test_on_course_create_success(self, mock_run, bus: EventBus):
        mock_run.return_value = MagicMock(returncode=0, stdout='{"notebook_id": "nb_created_456"}', stderr="")

        cli_plugin = NotebookLMCLIPlugin(bus)
        completed_events = []
        bus.on("TASK_COMPLETED", lambda p: completed_events.append(p))

        # Phát sự kiện ON_COURSE_CREATE
        bus.emit("ON_COURSE_CREATE", {
            "id": "task_create_1",
            "display_name": "Kinh tế lượng",
        })

        assert mock_run.called
        assert len(completed_events) == 1
        assert completed_events[0]["task_id"] == "task_create_1"
        assert completed_events[0]["notebooklm_id"] == "nb_created_456"

    @patch("subprocess.run")
    def test_on_source_add_success(self, mock_run, bus: EventBus):
        mock_run.return_value = MagicMock(returncode=0, stdout='{"source_id": "src_789"}', stderr="")

        cli_plugin = NotebookLMCLIPlugin(bus)
        completed_events = []
        bus.on("TASK_COMPLETED", lambda p: completed_events.append(p))

        # Phát sự kiện ON_SOURCE_ADD
        bus.emit("ON_SOURCE_ADD", {
            "id": "task_add_2",
            "notebooklm_id": "nb_123",
            "file_url": "https://example.com/bai_giang.pdf",
        })

        assert mock_run.called
        assert len(completed_events) == 1
        assert completed_events[0]["task_id"] == "task_add_2"
        assert completed_events[0]["source_id"] == "src_789"


class TestLocalStoragePlugin:
    def test_on_course_create_folder(self, bus: EventBus, temp_dir: str):
        storage_plugin = LocalStoragePlugin(bus, base_path=temp_dir)

        bus.emit("ON_COURSE_CREATE", {
            "id": "task_create_folder",
            "local_folder_name": "03_Co_So_Du_Lieu",
        })

        expected_path = os.path.join(temp_dir, "03_Co_So_Du_Lieu")
        assert os.path.exists(expected_path)
        assert os.path.isdir(expected_path)

    @patch("requests.get")
    def test_on_source_add_download(self, mock_get, bus: EventBus, temp_dir: str):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.iter_content.return_value = [b"Chunk 1 ", b"Chunk 2"]
        mock_response.__enter__.return_value = mock_response
        mock_get.return_value = mock_response

        storage_plugin = LocalStoragePlugin(bus, base_path=temp_dir)

        # Chạy trực tiếp worker để không phụ thuộc timing của Thread
        storage_plugin._download_worker(
            file_url="https://drive.google.com/test.pdf",
            folder_name="01_Mon_A",
            filename="document.pdf",
            payload={"id": "task_dl_1"}
        )

        expected_file = os.path.join(temp_dir, "01_Mon_A", "document.pdf")
        assert os.path.exists(expected_file)
        with open(expected_file, "rb") as f:
            content = f.read()
        assert content == b"Chunk 1 Chunk 2"


class TestEndToEndEventDrivenFlow:
    @patch("subprocess.run")
    @patch("requests.get")
    def test_three_way_sync_flow(self, mock_get, mock_run, bus: EventBus, temp_dir: str):
        """Kiểm tra toàn bộ luồng 3 chiều mà không có lời gọi trực tiếp giữa các plugin."""
        mock_run.return_value = MagicMock(returncode=0, stdout='{"notebook_id": "nb_e2e_999"}', stderr="")
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"Sample PDF"]
        mock_resp.__enter__.return_value = mock_resp
        mock_get.return_value = mock_resp

        mock_db = MagicMock()
        doc1 = MagicMock(id="task_e2e_1")
        doc1.to_dict.return_value = {
            "action": "course_create",
            "display_name": "Hệ thống thông tin quản lý",
            "local_folder_name": "04_HTTTQL",
            "status": "pending",
        }
        mock_db.collection.return_value.where.return_value.stream.return_value = [doc1]

        # Khởi tạo 3 Plugin
        poller = FirestorePollerPlugin(bus, db=mock_db)
        ai_cli = NotebookLMCLIPlugin(bus)
        storage = LocalStoragePlugin(bus, base_path=temp_dir)

        # 1. Poller quét và phát ON_COURSE_CREATE
        poller.poll_once()

        # 2. LocalStorage tự tạo thư mục (không gọi ai_cli hay poller)
        expected_dir = os.path.join(temp_dir, "04_HTTTQL")
        assert os.path.exists(expected_dir)

        # 3. AI CLI tự sinh TASK_COMPLETED và Poller tự cập nhật completed
        assert mock_run.called
        update_calls = mock_db.collection.return_value.document.return_value.update.call_args_list
        assert any(c[0][0].get("status") == "completed" for c in update_calls)
