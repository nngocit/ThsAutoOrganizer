# local_agent/chat_task_handler.py — Chat AI handler (<150 dòng)
# chat_query -> `nlm notebook query` (§7, KHÔNG có `nlm query`) -> Citation Engine
# qua Worker -> agent_reply. Mọi lỗi -> agent_fail + raise (không treo processing).

import json
import logging

from . import api_client
from .nlm_task_handler import _nlm_available, _parse_nlm_json, _run_nlm

logger = logging.getLogger(__name__)

QUERY_TIMEOUT = 180


def _extract_answer(data: dict) -> tuple[str, str, list]:
    """Tách (answer, conversation_id, citations) từ JSON output của nlm notebook query."""
    answer = (data.get("answer") or data.get("response") or data.get("text")
              or data.get("result") or "")
    conv_id = data.get("conversation_id") or data.get("conversationId") or ""
    raw_cits = data.get("citations") or data.get("references") or []
    citations: list[dict] = []
    for c in raw_cits if isinstance(raw_cits, list) else []:
        if not isinstance(c, dict):
            continue
        citations.append({
            "source_id": c.get("source_id") or c.get("sourceId") or "",
            "source_name": c.get("source_name") or c.get("sourceName") or "",
            "page": c.get("page") or c.get("page_number") or 0,
            "quote": c.get("quote") or c.get("text") or "",
            "title": c.get("title") or "",
        })
    return str(answer), str(conv_id), citations


def _format_via_worker(citations: list[dict], style: str) -> str:
    """Citation Engine qua Worker (§3.3). Trả citation_style thực dùng."""
    if not citations:
        return "none"
    try:
        result = api_client.format_citations(citations, style or "auto")
        return result.get("style", style or "auto")
    except RuntimeError as e:
        logger.warning("format_citations lỗi (bỏ qua, Worker sẽ format lại): %s", e)
        return style or "auto"


def handle_chat_query(task: dict) -> None:
    """Xử lý action='chat_query' (§2). Lỗi nào cũng agent_fail trước khi raise."""
    session_id = task.get("session_id", "")
    message_id = task.get("message_id", "")
    job_id = task.get("id", "")
    notebook_id = task.get("notebook_id", "")
    prompt = task.get("prompt", "")
    style = task.get("citation_style", "auto")
    uid = task.get("uid", "")

    def _fail(error: str) -> None:
        try:
            api_client.agent_fail(session_id, job_id=job_id, message_id=message_id, error=error, uid=uid)
        except RuntimeError as e:
            logger.error("Không báo agent_fail được về Worker: %s", e)

    try:
        if not _nlm_available():
            raise RuntimeError("nlm CLI không tìm thấy")
        if not (notebook_id and prompt):
            raise ValueError("chat_query thiếu notebook_id hoặc prompt")

        # §7: nlm notebook query <NB_ID> "<prompt>" --json [--source-ids] [--conversation-id]
        args = ["notebook", "query", notebook_id, prompt, "--json",
                "--timeout", str(QUERY_TIMEOUT)]
        source_ids = task.get("source_ids") or "[]"
        if isinstance(source_ids, str):
            source_ids = json.loads(source_ids) if source_ids.startswith("[") else []
        if source_ids:
            args += ["--source-ids", ",".join(str(s) for s in source_ids)]
        conv_id = task.get("conversation_id", "")
        if conv_id:
            args += ["--conversation-id", conv_id]

        returncode, stdout, stderr = _run_nlm(args, timeout=QUERY_TIMEOUT + 30)
        if returncode != 0:
            raise RuntimeError(f"nlm notebook query lỗi (code={returncode}): {stderr or stdout}")

        data = _parse_nlm_json(stdout)
        answer, new_conv_id, citations = _extract_answer(data)
        if not answer:
            answer = stdout or "(NLM không trả nội dung)"

        used_style = _format_via_worker(citations, style)
        api_client.agent_reply(
            session_id, job_id=job_id, message_id=message_id,
            content=answer + (f"\n\n<!-- conversation_id:{new_conv_id} -->" if new_conv_id else ""),
            citations=citations, citation_style=used_style, model="notebooklm", uid=uid)
        logger.info("chat_query OK: session=%s, %d citations", session_id, len(citations))
    except Exception as exc:
        _fail(str(exc))
        raise
