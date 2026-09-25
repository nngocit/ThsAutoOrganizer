# tests/test_drain_once.py — Test chế độ drain (GitHub Actions / Termux)

from unittest.mock import patch

from local_agent.drain_once import CLOUD_ACTIONS, build_poller, main
from local_agent.firestore_poller import FirestorePoller


def _poller() -> FirestorePoller:
    return FirestorePoller("nlm_task_queue")


def test_cloud_actions_exclude_local_only_actions():
    """Chế độ cloud KHÔNG đăng ký handler cần ổ đĩa PC / Drive token."""
    assert "source_add" in CLOUD_ACTIONS
    assert "chat_query" in CLOUD_ACTIONS
    assert "artifact_download" not in CLOUD_ACTIONS
    assert "reconcile_local" not in CLOUD_ACTIONS


def test_build_poller_registers_cloud_actions():
    poller = build_poller()
    for action in CLOUD_ACTIONS:
        assert action in poller._handlers


def test_process_task_returns_skipped_ext():
    """_process_task phải trả status để run_once tổng hợp được."""
    poller = _poller()
    poller.register("source_add", lambda t: "skipped_ext")

    with patch.object(poller, "_mark_task") as mock_mark:
        status = poller._process_task({"id": "t1", "action": "source_add"})

    assert status == "skipped_ext"
    mock_mark.assert_any_call("t1", "processing")
    mock_mark.assert_any_call("t1", "skipped_ext", result="skipped_ext")


def test_process_task_returns_no_handler():
    poller = _poller()
    with patch.object(poller, "_mark_task") as mock_mark:
        status = poller._process_task({"id": "t2", "action": "khong_ton_tai"})

    assert status == "no_handler"
    mock_mark.assert_called_once()


def test_run_once_aggregates_statuses():
    poller = _poller()
    tasks = [{"id": "a", "action": "x"}, {"id": "b", "action": "x"}, {"id": "c", "action": "x"}]

    with patch.object(poller, "_get_pending_tasks", return_value=tasks), \
         patch.object(poller, "_process_task", side_effect=["done", "failed", "skipped_ext"]):
        summary = poller.run_once()

    assert summary == {"processed": 3, "done": 1, "failed": 1, "skipped": 1, "no_handler": 0}


def test_run_until_idle_stops_when_queue_empty():
    poller = _poller()
    empty = {"processed": 0, "done": 0, "failed": 0, "skipped": 0, "no_handler": 0}
    one = dict(empty, processed=2, done=2)

    with patch.object(poller, "run_once", side_effect=[one, empty]) as mock_once:
        total = poller.run_until_idle(max_passes=10, idle_sleep=0)

    assert mock_once.call_count == 2
    assert total["processed"] == 2
    assert total["passes"] == 2


def test_run_until_idle_respects_max_passes():
    poller = _poller()
    always = {"processed": 1, "done": 1, "failed": 0, "skipped": 0, "no_handler": 0}

    with patch.object(poller, "run_once", return_value=always) as mock_once:
        total = poller.run_until_idle(max_passes=3, idle_sleep=0)

    assert mock_once.call_count == 3
    assert total["processed"] == 3


def test_main_dry_run_ok_and_does_not_call_api():
    cfg = {"worker_url": "https://example.workers.dev", "agent_secret": "secret",
           "local_base_path": "/tmp/mon_hoc"}

    with patch("local_agent.drain_once.load_config", return_value=cfg), \
         patch("local_agent.drain_once.sync_remote_config") as mock_sync:
        assert main(["--dry-run"]) == 0

    mock_sync.assert_not_called()


def test_main_dry_run_fails_when_secret_missing():
    with patch("local_agent.drain_once.load_config", return_value={"worker_url": "https://x"}):
        assert main(["--dry-run"]) == 2


def test_main_returns_2_when_config_file_missing():
    with patch("local_agent.drain_once.load_config", side_effect=FileNotFoundError("nope")):
        assert main(["--dry-run"]) == 2


def test_main_returns_1_when_task_failed():
    cfg = {"worker_url": "https://x", "agent_secret": "s"}
    summary = {"processed": 1, "done": 0, "failed": 1, "skipped": 0,
               "no_handler": 0, "passes": 1}

    with patch("local_agent.drain_once.load_config", return_value=cfg), \
         patch("local_agent.drain_once.sync_remote_config", return_value=cfg), \
         patch("local_agent.drain_once.build_poller") as mock_build:
        mock_build.return_value.run_until_idle.return_value = summary
        assert main([]) == 1


def test_main_returns_0_when_all_done():
    cfg = {"worker_url": "https://x", "agent_secret": "s"}
    summary = {"processed": 2, "done": 2, "failed": 0, "skipped": 0,
               "no_handler": 0, "passes": 1}

    with patch("local_agent.drain_once.load_config", return_value=cfg), \
         patch("local_agent.drain_once.sync_remote_config", return_value=cfg), \
         patch("local_agent.drain_once.build_poller") as mock_build:
        mock_build.return_value.run_until_idle.return_value = summary
        assert main([]) == 0
