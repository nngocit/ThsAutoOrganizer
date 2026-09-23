#!/usr/bin/env python3
# scripts/backfill_migrated_docs.py — Va du lieu da migrate tu SQLite (<200 dong)
#
# Sua cac khuyet diem cua migration v1:
#   - Thieu field `id` (client dung s.id -> GET /sessions/undefined 404 loop)
#   - Chat session thieu message_count / last_message_at / notebook_id
#   - Files thieu notebooklm_sync_status / size_bytes / course_id; status UPPERCASE
#   - File Triet hoc da co that trong notebook NLM -> danh 'synced' + source_id
#
# Idempotent: chi patch field con thieu. Ho tro --dry-run.
# QUAN TRONG: PATCH phai kem updateMask.fieldPaths — neu khong Firestore REST
# se REPLACE toan bo document va mat cac field khac.

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCOPE = "https://www.googleapis.com/auth/datastore"
FS_BASE = "https://firestore.googleapis.com/v1/projects/{pid}/databases/(default)/documents"
# ext NLM khong nhan (anh) -> danh dau 'skipped' thay vi 'pending' mai mai
NLM_UNSUPPORTED = {".jpg", ".jpeg", ".png"}


def _val(v):
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    return {"stringValue": str(v)}


def _fields(doc):
    out = {}
    for k, v in (doc.get("fields") or {}).items():
        for t, val in v.items():
            out[k] = val
    return out


class Backfill:
    def __init__(self, sa_path: str, uid: str, email: str, dry_run: bool):
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account

        sa = json.loads(Path(sa_path).read_text(encoding="utf-8"))
        creds = service_account.Credentials.from_service_account_file(sa_path, scopes=[SCOPE])
        self.http = AuthorizedSession(creds)
        self.base = FS_BASE.format(pid=sa["project_id"])
        self.uid, self.email, self.dry_run = uid, email, dry_run
        self.stats = {"patched": 0, "skipped": 0, "errors": 0}

    # ---------- Firestore REST ----------
    def lscoll(self, path, page_size=300):
        r = self.http.get(f"{self.base}/{path}", params={"pageSize": page_size}, timeout=30)
        r.raise_for_status()
        return r.json().get("documents", [])

    def patch(self, path: str, fields: dict, label: str):
        """PATCH merge voi updateMask — KHONG BAO GIO patch khong mask."""
        if not fields:
            self.stats["skipped"] += 1
            return
        if self.dry_run:
            print(f"  [DRY] {label}: {sorted(fields.keys())}")
            self.stats["patched"] += 1
            return
        params = [("updateMask.fieldPaths", k) for k in fields]
        body = {"fields": {k: _val(v) for k, v in fields.items()}}
        r = self.http.patch(f"{self.base}/{path}", params=params, json=body, timeout=30)
        if r.status_code not in (200, 201):
            self.stats["errors"] += 1
            print(f"  [ERROR] {label}: {r.status_code} {r.text[:200]}")
            return
        print(f"  [OK] {label}: {sorted(fields.keys())}")
        self.stats["patched"] += 1

    # ---------- NotebookLM ----------
    def nlm_sources(self, notebook_id: str) -> dict:
        """filename -> source_id (qua nlm CLI; {} neu loi)."""
        try:
            r = subprocess.run(["nlm", "source", "list", notebook_id, "--json"],
                               capture_output=True, text=True, timeout=60, encoding="utf-8")
            data = json.loads(r.stdout) if r.returncode == 0 else []
            return {s.get("title", ""): s.get("id", "") for s in data}
        except Exception as e:  # noqa: BLE001
            print(f"  [WARN] nlm source list loi: {e}")
            return {}


    # ---------- Cac buoc ----------
    def run(self):
        u = f"users/{self.uid}"
        courses = {d["name"].rsplit("/", 1)[-1]: _fields(d) for d in self.lscoll(f"{u}/courses")}
        name_to_course = {f.get("name"): cid for cid, f in courses.items()}

        print("== courses: them field id ==")
        for cid, f in courses.items():
            if not f.get("id"):
                self.patch(f"{u}/courses/{cid}", {"id": cid}, f"course/{cid}")

        print("== ai_insights: them field id ==")
        for d in self.lscoll(f"{u}/ai_insights"):
            iid = d["name"].rsplit("/", 1)[-1]
            self.patch(f"{u}/ai_insights/{iid}", {"id": iid}, f"insight/{iid}")

        print("== files: id + status + size + course_id + nlm status ==")
        nlm_cache: dict[str, dict] = {}
        for d in self.lscoll(f"{u}/files"):
            fid = d["name"].rsplit("/", 1)[-1]
            f = _fields(d)
            patch: dict = {}
            if not f.get("id"):
                patch["id"] = fid
            status = str(f.get("status") or "").lower()
            if status and status != f.get("status"):
                patch["status"] = status
            lp = f.get("local_path") or ""
            if not f.get("size_bytes") and lp and Path(lp).exists():
                patch["size_bytes"] = str(Path(lp).stat().st_size)
            if not f.get("course_id") and f.get("subject") in name_to_course:
                patch["course_id"] = name_to_course[f["subject"]]
            if "notebooklm_sync_status" not in f:
                fn = f.get("filename") or ""
                ext = Path(fn).suffix.lower()
                if ext in NLM_UNSUPPORTED:
                    patch["notebooklm_sync_status"] = "skipped"
                else:
                    nb = courses.get(patch.get("course_id", f.get("course_id", "")), {}).get("notebook_id", "")
                    if nb:
                        # Kiem tra file da co that trong notebook chua (match filename)
                        if nb not in nlm_cache:
                            nlm_cache[nb] = self.nlm_sources(nb)
                        sid = nlm_cache[nb].get(fn, "")
                        if sid:
                            patch["notebooklm_sync_status"] = "synced"
                            patch["notebooklm_source_id"] = sid
                        else:
                            patch["notebooklm_sync_status"] = "pending"
                    else:
                        patch["notebooklm_sync_status"] = "pending"
            self.patch(f"{u}/files/{fid}", patch, f"file/{fid} ({str(f.get('filename'))[:40]})")

        print("== chat_sessions + messages ==")
        for d in self.lscoll(f"{u}/chat_sessions"):
            sid = d["name"].rsplit("/", 1)[-1]
            f = _fields(d)
            msgs = self.lscoll(f"{u}/chat_sessions/{sid}/messages")
            created = [_fields(m).get("created_at", "") for m in msgs]
            patch = {"id": sid} if not f.get("id") else {}
            if "message_count" not in f:
                patch["message_count"] = len(msgs)
            if not f.get("last_message_at") and created:
                patch["last_message_at"] = max(created)
            if "selected_source_ids" not in f:
                patch["selected_source_ids"] = "[]"
            nb = courses.get(f.get("course_id", ""), {}).get("notebook_id", "")
            if not f.get("notebook_id") and nb:
                patch["notebook_id"] = nb
            if "orphan_warning" not in f:
                patch["orphan_warning"] = not (f.get("notebook_id") or nb)
            if not f.get("user_email") and self.email:
                patch["user_email"] = self.email
            self.patch(f"{u}/chat_sessions/{sid}", patch, f"session/{sid}")
            for m in msgs:
                mid = m["name"].rsplit("/", 1)[-1]
                if not _fields(m).get("id"):
                    self.patch(f"{u}/chat_sessions/{sid}/messages/{mid}", {"id": mid}, f"msg/{mid}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill du lieu migrate (idempotent)")
    ap.add_argument("--service-account",
                    default="firebase/thsautoorganizer-firebase-adminsdk-fbsvc-b679e7b735.json")
    ap.add_argument("--uid", default="105293426482467926778")
    ap.add_argument("--email", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    email = args.email
    cfg = Path("config.json")
    if not email and cfg.exists():
        email = json.loads(cfg.read_text(encoding="utf-8-sig")).get("root_account_email", "")

    bf = Backfill(args.service_account, args.uid, email, args.dry_run)
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Backfill users/{args.uid} (email={email})")
    bf.run()
    s = bf.stats
    print(f"\n[{'DRY' if args.dry_run else 'DONE'}] patched={s['patched']}, "
          f"skipped={s['skipped']}, errors={s['errors']}")
    return 1 if s["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
