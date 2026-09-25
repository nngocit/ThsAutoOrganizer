# tests/test_workflow_cloud_actions.py — Chống "drift" giữa workflow GitHub Actions và local_agent
#
# Workflow NLM Drain có bước "Kiểm tra nhanh hàng đợi" chứa danh sách CLOUD action
# (để bỏ qua run khi hàng đợi không có task nào chạy được trên runner).
# Danh sách này PHẢI khớp CLOUD_ACTIONS trong local_agent/drain_once.py — test này ép buộc điều đó.

import ast
import pathlib
import re

from local_agent.drain_once import CLOUD_ACTIONS

WORKFLOW = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows" / "nlm-drain.yml"


def test_quickcheck_cloud_set_matches_drain_once_cloud_actions():
    """CLOUD = {...} trong workflow phải trùng đúng CLOUD_ACTIONS của drain_once."""
    text = WORKFLOW.read_text(encoding="utf-8")
    m = re.search(r"CLOUD\s*=\s*(\{[^}]*\})", text)
    assert m, "Không tìm thấy dòng 'CLOUD = {...}' trong bước quickcheck của workflow"
    workflow_set = ast.literal_eval(m.group(1))
    assert workflow_set == set(CLOUD_ACTIONS), (
        f"Workflow có {sorted(workflow_set)} nhưng drain_once có {sorted(CLOUD_ACTIONS)} — "
        "cập nhật cả hai chỗ cho khớp."
    )


def test_auto_triggers_enabled():
    """repository_dispatch + schedule phải được BẬT (không còn comment)."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"(?m)^  repository_dispatch:\s*$", text), "repository_dispatch chưa bật"
    assert re.search(r"(?m)^    types: \[nlm-drain\]\s*$", text), "thiếu types: [nlm-drain]"
    assert re.search(r"(?m)^  schedule:\s*$", text), "schedule chưa bật"
    assert re.search(r"(?m)^    - cron: '\*/15 \* \* \* \*'\s*$", text), "thiếu cron */15"


def test_quickcheck_skipped_on_manual_dispatch():
    """Run tay (workflow_dispatch) phải LUÔN chạy đủ — quickcheck chỉ dành cho schedule/dispatch."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "if: github.event_name != 'workflow_dispatch'" in text
    # Mọi bước nặng phải có guard skip để run rỗng không tốn phút Actions
    for step in ["Setup Python 3.12", "Cài dependencies (chỉ 2 gói)",
                 "Khôi phục phiên Google (auth.json) từ Secret", "Drain hàng đợi (source_add → NotebookLM)"]:
        idx = text.find(f"- name: {step}")
        assert idx != -1, f"Không thấy bước {step}"
        block = text[idx:idx + 400]
        assert "steps.quickcheck.outputs.skip != 'true'" in block, f"Bước {step} thiếu guard quickcheck"
