#!/usr/bin/env python3
# scripts/migrate_sqlite_to_firestore.py — Phase 1: SQLite -> Firestore (<250 dòng)
# CLI: --db data/files.db --service-account <json> --uid <uid> [--email] [--dry-run] [--limit N]
# Idempotent: doc id cố định (m_<sha256[:20]>, mig_<id>) — GET trước, tồn tại thì SKIP.

import argparse
import json
import sqlite3
import sys
from pathlib import Path

SCOPE = "https://www.googleapis.com/auth/datastore"
FS_BASE = "https://firestore.googleapis.com/v1/projects/{pid}/databases/(default)/documents"

FOLDER_MAP = {
    "giao_trinh": "01_Giao_Trinh_Goc",
    "slide": "02_Slide_Giang_Day",
    "bai_bao": "03_Tai_Lieu_Tham_Khao/01_Bai_Bao_Khoa_Hoc",
    "unverified_web": "03_Tai_Lieu_Tham_Khao/02_Unverified_Web",
    "ket_qua": "04_Ket_Qua_Xuat_Ban",
}
OUTPUT_FOLDER = "04_Ket_Qua_Xuat_Ban"
DEFAULT_REVIEW = {"giao_trinh": "approved", "slide": "approved", "bai_bao": "approved",
                  "unverified_web": "unreviewed", "ket_qua": "approved"}


def _val(v):
    """Python scalar -> Firestore Value."""
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


def _doc(fields: dict) -> dict:
    return {"fields": {k: _val(v) for k, v in fields.items()}}


def _infer_doc_type(path: str) -> str:
    norm = (path or "").replace("\\", "/")
    return next((t for t, f in FOLDER_MAP.items() if f in norm), "giao_trinh")


class Migrator:
    def __init__(self, db_path: str, session, pid: str, uid: str,
                 dry_run: bool = False, limit: int = 0):
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.http, self.dry_run, self.limit = session, dry_run, limit
        self.root = FS_BASE.format(pid=pid)
        self.base = self.root + f"/users/{uid}"
        self._tables = {r[0] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}

    # ---------- Firestore REST ----------
    def put(self, coll_url: str, doc_id: str, fields: dict) -> str:
        """Ghi doc idempotent. Trả 'done' | 'skip'. Raise nếu lỗi HTTP."""
        url = f"{coll_url}/{doc_id}"
        if self.dry_run:
            return "done"
        if self.http.get(url, timeout=30).status_code == 200:
            return "skip"
        resp = self.http.patch(url, json=_doc(fields), timeout=30)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"PATCH {doc_id} -> {resp.status_code}: {resp.text[:200]}")
        return "done"

    def rows(self, table: str, order: str = "id") -> list[sqlite3.Row]:
        if table not in self._tables:
            return []
        sql = f"SELECT * FROM {table} ORDER BY {order}"
        if self.limit:
            sql += f" LIMIT {int(self.limit)}"
        return self.db.execute(sql).fetchall()

    def coll(self, *parts: str) -> str:
        return f"{self.base}/{'/'.join(parts)}"

    # ---------- Các bảng ----------
    def migrate_courses(self):
        for r in self.rows("majors"):
            yield "courses", f"mig_{r['id']}", {
                "name": r["name"], "code": r["code"], "folder_name": r["folder_name"],
                "description": r["description"], "kind": "major",
                "migrated_from": "majors", "created_at": r["created_at"]}
        for r in self.rows("subjects"):
            yield "courses", f"mig_s_{r['id']}", {
                "name": r["name"], "code": r["code"], "folder_name": r["folder_name"],
                "keywords": r["keywords"], "notebook_id": r["notebooklm_id"] or "",
                "major_id": f"mig_{r['major_id']}", "kind": "subject",
                "migrated_from": "subjects", "created_at": r["created_at"]}

    def migrate_files(self):
        for r in self.rows("files"):
            doc_type = _infer_doc_type(r["path"])
            folder = next((f for f in FOLDER_MAP.values() if f in r["path"].replace("\\", "/")), "")
            yield "files", f"m_{r['sha256'][:20]}", {
                "filename": Path(r["path"]).name, "subject": r["subject"],
                "document_type": doc_type, "folder_path": folder, "sha256": r["sha256"],
                "drive_file_id": r["drive_file_id"] or "", "status": r["status"],
                "local_path": r["path"], "source_kind": "local_scan",
                "is_output": folder.startswith(OUTPUT_FOLDER),
                "review_status": DEFAULT_REVIEW.get(doc_type, "unreviewed"),
                "created_at": r["created_at"], "updated_at": r["updated_at"]}

    def migrate_insights(self):
        for r in self.rows("ai_insights"):
            yield "ai_insights", f"mig_{r['id']}", {
                "course_id": f"mig_s_{r['subject_id']}", "insight_type": r["insight_type"],
                "title": r["title"], "content": r["content"],
                "citations": r["citations"] or "[]", "created_by": r["created_by"],
                "created_at": r["created_at"]}

    def migrate_chat_sessions(self):
        for r in self.rows("ai_chat_sessions"):
            yield "ai_chat_sessions", f"mig_{r['id']}", {
                "course_id": f"mig_s_{r['subject_id']}", "title": r["title"],
                "conversation_id": r["conversation_id"] or "", "origin": "cli",
                "status": "active", "created_at": r["created_at"], "updated_at": r["updated_at"]}

    def migrate_chat_messages(self):
        for r in self.rows("ai_chat_messages"):
            yield f"chat_sessions/mig_{r['session_id']}/messages", f"mig_{r['id']}", {
                "session_id": f"mig_{r['session_id']}", "role": r["role"],
                "content": r["content"], "citations": r["citations"] or "[]",
                "status": "done", "created_at": r["created_at"]}

    def migrate_web_sources(self):
        for r in self.rows("web_research_sources"):
            d = dict(r)
            sha = (d.get("sha256") or d.get("url") or f"row{d.get('id')}")[:20]
            yield "web_research_sources", f"m_{sha}", {
                "filename": d.get("filename") or d.get("title") or "web_source",
                "document_type": "unverified_web", "folder_path": FOLDER_MAP["unverified_web"],
                "url": d.get("url", ""), "review_status": "unreviewed",
                "source_kind": "deep_research", "is_output": False, "status": "migrated"}

    def migrate_sync_logs(self):
        for r in self.rows("notebooklm_sync_log"):
            yield "notebooklm_sync_logs", f"mig_{r['id']}", {
                "file_path": r["file_path"], "notebooklm_id": r["notebooklm_id"] or "",
                "status": r["status"], "error_message": r["error_message"] or "",
                "synced_at": r["synced_at"] or "", "created_at": r["created_at"]}

    def migrate_deletion_logs(self):
        for r in self.rows("file_deletion_logs"):
            d = dict(r)
            yield "file_deletion_logs", f"mig_{d.get('id')}", {k: v for k, v in d.items() if k != "id"}


# (label, generator, collection | None = lấy path từ generator, global?)
MIGRATIONS = [
    ("majors+subjects -> courses", Migrator.migrate_courses, "courses", False),
    ("files -> files", Migrator.migrate_files, "files", False),
    ("ai_insights", Migrator.migrate_insights, "ai_insights", False),
    ("ai_chat_sessions", Migrator.migrate_chat_sessions, "chat_sessions", False),
    ("ai_chat_messages -> messages", Migrator.migrate_chat_messages, None, False),
    ("web_research_sources -> files", Migrator.migrate_web_sources, "files", False),
    ("notebooklm_sync_log", Migrator.migrate_sync_logs, "notebooklm_sync_logs", False),
    ("file_deletion_logs (global)", Migrator.migrate_deletion_logs, "file_deletion_logs", True),
]


def _find_uid_by_email(session, pid: str, email: str) -> str:
    """Quét collection users tìm doc có email khớp (profile/data.email)."""
    url = FS_BASE.format(pid=pid) + "/users"
    resp = session.get(url, params={"pageSize": 300}, timeout=30)
    resp.raise_for_status()
    for doc in resp.json().get("documents", []):
        f = doc.get("fields", {})
        prof = f.get("profile", {}).get("mapValue", {}).get("fields", {})
        data = prof.get("data", {}).get("mapValue", {}).get("fields", {})
        found = (f.get("email", {}).get("stringValue", "")
                 or data.get("email", {}).get("stringValue", "")
                 or prof.get("email", {}).get("stringValue", ""))
        if found.lower() == email.lower():
            return doc["name"].rsplit("/", 1)[-1]
    raise SystemExit(f"[ERROR] Không tìm thấy uid cho email: {email}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrate SQLite -> Firestore (Phase 1)")
    ap.add_argument("--db", default="data/files.db")
    ap.add_argument("--service-account", required=True)
    ap.add_argument("--uid", default="")
    ap.add_argument("--email", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not Path(args.db).exists():
        print(f"[ERROR] DB không tồn tại: {args.db}")
        return 1

    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    sa = json.loads(Path(args.service_account).read_text(encoding="utf-8"))
    creds = service_account.Credentials.from_service_account_file(
        args.service_account, scopes=[SCOPE])
    session = AuthorizedSession(creds)
    pid = sa["project_id"]

    if not args.uid and not args.email:
        print("[ERROR] Cần --uid hoặc --email để xác định user đích.")
        return 1
    uid = args.uid or _find_uid_by_email(session, pid, args.email)

    mig = Migrator(args.db, session, pid, uid, dry_run=args.dry_run, limit=args.limit)
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Migrate {args.db} -> users/{uid} (project={pid})")
    exit_code = 0
    for label, gen_fn, coll, is_global in MIGRATIONS:
        done = skip = err = 0
        try:
            for table, doc_id, fields in gen_fn(mig):
                if is_global:
                    coll_url = f"{mig.root}/{coll}"
                elif coll is None:
                    coll_url = mig.coll(*table.split("/"))
                else:
                    coll_url = mig.coll(coll)
                try:
                    result = mig.put(coll_url, doc_id, fields)
                    done += result == "done"
                    skip += result == "skip"
                except Exception as e:  # noqa: BLE001
                    err += 1
                    print(f"  [ERROR] {label}/{doc_id}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] {label}: {e}")
            exit_code = 1
            continue
        if err:
            tag, exit_code = "[ERROR]", 1
        else:
            tag = "[SKIP]" if (done == 0 and skip > 0) else "[DONE]"
        print(f"{tag} {label}: created={done}, skipped={skip}, errors={err}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

