# local_agent/research_task_handler.py — Deep Research handler (<200 dòng)
# §7: `nlm research start --mode deep --source web` -> poll `research status --max-wait 0`
# -> `research import` -> tải PDF nguồn -> post_research_sources. PATCH tiến độ định kỳ.
# Mọi lỗi: PATCH status='failed' + raise (không treo processing).

import hashlib
import logging
import time
from pathlib import Path

import requests

from . import api_client
from .config_loader import get
from .nlm_task_handler import _nlm_available, _parse_nlm_json, _run_nlm

logger = logging.getLogger(__name__)

POLL_SECONDS = 20
MAX_WAIT_SECONDS = 30 * 60       # deep research tối đa 30 phút
MAX_PDF_DOWNLOADS = 20
PDF_TIMEOUT = 60


def _patch(job_id: str, uid: str = "", **kwargs) -> None:
    try:
        api_client.patch_research(job_id, uid=uid, **kwargs)
    except RuntimeError as e:
        logger.warning("patch_research lỗi (bỏ qua): %s", e)


def _download_pdf(url: str, dest_dir: Path, index: int) -> dict | None:
    """Tải 1 PDF về dest_dir. Trả dict metadata hoặc None nếu không phải PDF/lỗi."""
    try:
        resp = requests.get(url, timeout=PDF_TIMEOUT, stream=True,
                            headers={"User-Agent": "ThsAutoOrganizer-Agent/2.0"})
        ctype = resp.headers.get("Content-Type", "").lower()
        if resp.status_code != 200 or ("pdf" not in ctype and not url.lower().endswith(".pdf")):
            return None
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"research_{index:02d}_{int(time.time())}.pdf"
        sha = hashlib.sha256()
        size = 0
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(65536):
                fh.write(chunk)
                sha.update(chunk)
                size += len(chunk)
        return {"filename": dest.name, "local_path": str(dest.resolve()),
                "sha256": sha.hexdigest(), "size_bytes": size}
    except requests.RequestException as e:
        logger.warning("Tải PDF thất bại %s: %s", url, e)
        return None


def _extract_sources(data: dict) -> list[dict]:
    """Tách danh sách nguồn từ JSON của nlm research status/import."""
    raw = data.get("sources") or data.get("imported_sources") or data.get("results") or []
    sources: list[dict] = []
    for s in raw if isinstance(raw, list) else []:
        if not isinstance(s, dict):
            continue
        sources.append({
            "title": s.get("title") or s.get("name") or "",
            "url": s.get("url") or s.get("link") or "",
            "authors": s.get("authors") or "",
            "year": s.get("year") or "",
            "publisher": s.get("publisher") or "",
            "doi": s.get("doi") or "",
        })
    return sources



def handle_research_start(task: dict) -> None:
    """Xử lý action='research_start' (§2). Lỗi -> PATCH failed + raise."""
    job_id = task.get("job_id", "")
    notebook_id = task.get("notebook_id", "")
    query = task.get("query", "")
    mode = task.get("mode", "deep")
    uid = task.get("uid", "")

    try:
        if not _nlm_available():
            raise RuntimeError("nlm CLI không tìm thấy")
        if not (job_id and notebook_id and query):
            raise ValueError("research_start thiếu job_id/notebook_id/query")
        if mode != "deep":
            logger.warning("mode=%s: CLI 0.11.6 chỉ hỗ trợ deep (--source web) — ép về deep", mode)

        _patch(job_id, uid=uid, status="running", progress="Khởi động deep research")

        # §7: nlm research start "<query>" --mode deep --notebook-id <NB> --source web [--force]
        rc, stdout, stderr = _run_nlm(
            ["research", "start", query, "--mode", "deep",
             "--notebook-id", notebook_id, "--source", "web", "--json"], timeout=120)
        if rc != 0:
            raise RuntimeError(f"nlm research start lỗi (code={rc}): {stderr or stdout}")
        nlm_task_id = _parse_nlm_json(stdout).get("task_id", "")

        # Poll trạng thái theo chu kỳ: nlm research status <NB> --max-wait 0 --json
        deadline = time.time() + int(get("deep_research_max_seconds", MAX_WAIT_SECONDS))
        status_data: dict = {}
        while time.time() < deadline:
            time.sleep(POLL_SECONDS)
            rc, stdout, stderr = _run_nlm(
                ["research", "status", notebook_id, "--max-wait", "0", "--json"], timeout=60)
            if rc != 0:
                logger.warning("research status lỗi tạm (code=%d): %s", rc, stderr or stdout)
                continue
            status_data = _parse_nlm_json(stdout)
            state = str(status_data.get("status", "")).lower()
            found = _extract_sources(status_data)
            _patch(job_id, uid=uid, status="running",
                   progress=f"Đang nghiên cứu ({state or 'running'})",
                   sources_found=len(found) or None)
            if state in ("completed", "complete", "done", "succeeded"):
                break
            if state in ("failed", "error"):
                raise RuntimeError(f"nlm research failed: {stderr or stdout}")
        else:
            raise RuntimeError(f"Deep research timeout sau {MAX_WAIT_SECONDS}s")

        # §7: import nguồn vào notebook
        _patch(job_id, uid=uid, status="running", progress="Import nguồn vào notebook")
        import_args = ["research", "import", notebook_id]
        if nlm_task_id:
            import_args.append(nlm_task_id)
        import_args += ["--cited-only", "--json"]
        rc, stdout, stderr = _run_nlm(import_args, timeout=300)
        if rc != 0:
            raise RuntimeError(f"nlm research import lỗi (code={rc}): {stderr or stdout}")
        sources = _extract_sources(_parse_nlm_json(stdout)) or _extract_sources(status_data)

        # Tải PDF các nguồn (tối đa MAX_PDF_DOWNLOADS) về _Research_Inbox
        inbox = Path(get("local_base_path", ".")) / "_Research_Inbox" / job_id
        payload: list[dict] = []
        for i, src in enumerate(sources[:MAX_PDF_DOWNLOADS]):
            entry: dict = {"filename": src["title"] or f"source_{i}", "url": src["url"],
                           "title": src["title"], "authors": src["authors"],
                           "year": src["year"], "publisher": src["publisher"],
                           "doi": src["doi"], "drive_file_id": "", "sha256": "",
                           "local_path": "", "size_bytes": 0}
            if src["url"]:
                pdf = _download_pdf(src["url"], inbox, i)
                if pdf:
                    entry.update({k: pdf[k] for k in
                                  ("filename", "local_path", "sha256", "size_bytes")})
            payload.append(entry)

        if payload:
            api_client.post_research_sources(job_id, payload, uid=uid)
        _patch(job_id, uid=uid, status="done", progress="Hoàn tất", sources_found=len(payload))
        logger.info("research_start OK: job=%s, %d nguồn", job_id, len(payload))
    except Exception as exc:
        if job_id:
            _patch(job_id, uid=uid, status="failed", error=str(exc))
        raise
