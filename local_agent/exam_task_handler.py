# local_agent/exam_task_handler.py — Trạm Ôn Thi handler (<150 dòng)
# exam_generate: 50 trắc nghiệm = `nlm quiz create --count 50` + `nlm download quiz --format json`
# 5 tự luận = `nlm notebook query` với prompt yêu cầu JSON (§7). Kết quả -> post_exam_set.

import json
import logging
import re
import tempfile
from pathlib import Path

from . import api_client
from .nlm_task_handler import _nlm_available, _parse_nlm_json, _run_nlm

logger = logging.getLogger(__name__)

ESSAY_PROMPT = (
    "Dựa trên các nguồn trong notebook, hãy tạo {n} câu hỏi tự luận phản biện. "
    'Trả về ĐÚNG một mảng JSON, mỗi phần tử có dạng: '
    '{{"q": "<câu hỏi>", "hint": "<gợi ý trả lời>", "ref": "<nguồn tham chiếu>"}}. '
    "Không thêm giải thích nào ngoài JSON."
)


def _norm_flashcard(item: dict) -> dict:
    return {"q": str(item.get("q") or item.get("question") or ""),
            "a": str(item.get("a") or item.get("answer") or ""),
            "ref": str(item.get("ref") or item.get("source") or "")}


def _parse_quiz_json(path: Path) -> list[dict]:
    """Đọc file quiz JSON do nlm download quiz xuất -> list flashcard {q,a,ref}."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Không đọc được quiz JSON %s: %s", path, e)
        return []
    raw = data if isinstance(data, list) else (data.get("questions")
                                               or data.get("flashcards") or [])
    return [_norm_flashcard(x) for x in raw if isinstance(x, dict)]


def _parse_essays(answer: str, count: int) -> list[dict]:
    """Tách mảng JSON tự luận từ câu trả lời NLM -> [{q,hint,ref}]."""
    match = re.search(r"\[.*\]", answer, re.DOTALL)
    if not match:
        return []
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    essays = []
    for x in raw[:count] if isinstance(raw, list) else []:
        if isinstance(x, dict) and (x.get("q") or x.get("question")):
            essays.append({"q": str(x.get("q") or x.get("question") or ""),
                           "hint": str(x.get("hint") or x.get("a") or ""),
                           "ref": str(x.get("ref") or "")})
    return essays


def _gen_flashcards(notebook_id: str, count: int) -> list[dict]:
    """§7: nlm quiz create <NB> --count N --difficulty 3 --confirm --json -> download quiz."""
    rc, stdout, stderr = _run_nlm(
        ["quiz", "create", notebook_id, "--count", str(count),
         "--difficulty", "3", "--confirm", "--json"], timeout=600)
    if rc != 0:
        raise RuntimeError(f"nlm quiz create lỗi (code={rc}): {stderr or stdout}")
    _parse_nlm_json(stdout)

    out = Path(tempfile.mkdtemp(prefix="ths_quiz_")) / "quiz.json"
    rc, stdout, stderr = _run_nlm(
        ["download", "quiz", notebook_id, "--format", "json",
         "--output", str(out)], timeout=300)
    if rc != 0:
        raise RuntimeError(f"nlm download quiz lỗi (code={rc}): {stderr or stdout}")
    return _parse_quiz_json(out)


def _gen_essays(notebook_id: str, count: int) -> list[dict]:
    """5 câu tự luận qua nlm notebook query với prompt JSON (§7)."""
    rc, stdout, stderr = _run_nlm(
        ["notebook", "query", notebook_id, ESSAY_PROMPT.format(n=count),
         "--json", "--new-conversation", "--timeout", "180"], timeout=210)
    if rc != 0:
        logger.warning("nlm query tự luận lỗi (code=%d): %s — essays=[]", rc, stderr or stdout)
        return []
    answer = str(_parse_nlm_json(stdout).get("answer") or stdout)
    return _parse_essays(answer, count)


def handle_exam_generate(task: dict) -> None:
    """Xử lý action='exam_generate' (§2). Lỗi -> raise (poller mark failed)."""
    if not _nlm_available():
        raise RuntimeError("nlm CLI không tìm thấy")

    uid = task.get("uid", "")
    course_id = task.get("course_id", "")
    notebook_id = task.get("notebook_id", "")
    flashcard_count = int(task.get("flashcard_count", 50))
    essay_count = int(task.get("essay_count", 5))

    if not (uid and course_id and notebook_id):
        raise ValueError("exam_generate thiếu uid/course_id/notebook_id")

    flashcards = _gen_flashcards(notebook_id, flashcard_count)[:100]   # Worker cap 100
    if not flashcards:
        raise RuntimeError("Quiz rỗng — NLM không sinh được câu hỏi")
    essays = _gen_essays(notebook_id, essay_count)[:20]                # Worker cap 20

    title = task.get("title") or f"Đề ôn thi {flashcard_count} câu"
    api_client.post_exam_set(uid=uid, course_id=course_id, title=title,
                             flashcards=flashcards, essays=essays,
                             source_job_id=task.get("id", ""))
    logger.info("exam_generate OK: course=%s, %d flashcard + %d tự luận",
                course_id, len(flashcards), len(essays))
