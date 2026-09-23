# Hợp Đồng Giao Diện (Interface Contract) — Full-Cloud Phase 2–4

> **Ngày:** 23/09/2026 · **Trạng thái:** FROZEN (đóng băng — mọi teammate code theo tài liệu này)
> **Mục tiêu:** Cho phép 4 nhánh (Workers API / Python Local Agent / Pages Frontend / Audit-Release) phát triển song song mà không xung đột file hay lệch giao diện.
> **Bắt buộc:** MAX 200–250 dòng/file. 1 file = 1 trách nhiệm. Không commit secrets. Không chạy `git` (trừ teammate `release`).

---

## 0. Phân quyền vùng file (FILE OWNERSHIP) — KHÔNG ĐƯỢC GHI NGOÀI VÙNG CỦA MÌNH

| Teammate | Vùng được ghi |
|---|---|
| `audit` | `docs/superpowers/reports/**` (chỉ đọc phần còn lại) |
| `api` | `cloudflare/workers/**` |
| `agent` | `local_agent/**`, `scripts/**` |
| `web` | `cloudflare/pages/**` |
| `release` | `.gitignore`, `cloudflare/*.ps1`, thao tác `git` + `wrangler deploy` |
| lead (Cline) | `docs/superpowers/specs/**`, `README.md` |

---

## 1. Hằng số dùng chung (SINGLE SOURCE OF TRUTH)

Cấu trúc thư mục chuẩn (Local H:\... và Google Drive giống nhau):

```
01_Giao_Trinh_Goc/
02_Slide_Giang_Day/
03_Tai_Lieu_Tham_Khao/01_Bai_Bao_Khoa_Hoc/
03_Tai_Lieu_Tham_Khao/02_Unverified_Web/
04_Ket_Qua_Xuat_Ban/
_Archive_Trash_90Days/
```

| Ngôn ngữ | File hằng số | Ghi chú |
|---|---|---|
| Workers (JS) | `cloudflare/workers/src/lib/folders.js` | export `FOLDER_MAP`, `ARCHIVE_FOLDER`, `OUTPUT_FOLDER`, `NO_LOOP_FOLDERS`, `HARD_DELETE_DAYS`, `SUPPORTED_EXTENSIONS` |
| Python | `local_agent/constants.py` | export cùng tên, snake_case |
| Frontend | `cloudflare/pages/src/js/constants.js` | export cùng tên |

```js
FOLDER_MAP = {
  giao_trinh:     '01_Giao_Trinh_Goc',
  slide:          '02_Slide_Giang_Day',
  bai_bao:        '03_Tai_Lieu_Tham_Khao/01_Bai_Bao_Khoa_Hoc',
  unverified_web: '03_Tai_Lieu_Tham_Khao/02_Unverified_Web',
  ket_qua:        '04_Ket_Qua_Xuat_Ban',
}
OUTPUT_FOLDER   = '04_Ket_Qua_Xuat_Ban'          // NO-LOOP GUARD
ARCHIVE_FOLDER  = '_Archive_Trash_90Days'
NO_LOOP_FOLDERS = ['04_Ket_Qua_Xuat_Ban', '_Archive_Trash_90Days']  // Inflow BỎ QUA
HARD_DELETE_DAYS = 90
SUPPORTED_EXTENSIONS = ['.pdf','.docx','.pptx','.txt','.md','.jpg','.jpeg','.png','.mp3']
```

**Quy tắc chống lặp (No Loop) — 3 lớp phòng thủ, phải có đủ cả 3:**
1. `upload_init.js` / `files/register.js`: `is_output = (folder_path bắt đầu bằng OUTPUT_FOLDER)`.
2. `upload_complete.js` + `files/register.js`: **KHÔNG** queue `source_add` khi `is_output === true`.
3. `local_agent/file_watcher.py`: bỏ qua mọi path bắt đầu bằng `NO_LOOP_FOLDERS`, + `~$*`, `.tmp`, `<1000 bytes`, và duplicate `sha256`.


---

## 2. Mô hình dữ liệu Firestore (mới/bổ sung)

Quy ước JSON: **field kiểu mảng/object được lưu dạng JSON string** (đúng hành vi hiện tại của `lib/firebase.js`). Client/agent khi đọc phải `JSON.parse`, khi ghi `JSON.stringify`.

### `users/{uid}/files/{id}` — bổ sung field
| Field | Kiểu | Giá trị |
|---|---|---|
| `review_status` | string | `unreviewed` \| `approved` \| `rejected` \| `not_applicable` |
| `review_note`, `reviewed_at` | string | Ghi chú + thời điểm duyệt |
| `source_kind` | string | `local_scan` \| `web_upload` \| `deep_research` \| `artifact` |
| `local_path` | string | Đường dẫn tuyệt đối trên PC (rỗng nếu chỉ có trên Drive) |
| `is_output` | boolean | NO-LOOP GUARD (đã tồn tại) |

Quy tắc mặc định khi tạo file doc:
- `document_type in (giao_trinh, slide, bai_bao)` → `review_status = 'approved'`
- `document_type = unverified_web` → `review_status = 'unreviewed'`
- `document_type = ket_qua` → `review_status = 'approved'`, `is_output = true`

### `users/{uid}/chat_sessions/{id}`
```jsonc
{ "id": "", "course_id": "", "notebook_id": "", "title": "",
  "selected_source_ids": "[]",   // JSON string
  "message_count": 0, "last_message_at": "", "status": "active|archived", "origin": "web|cli",
  "orphan_warning": false, "orphan_note": "", "archived_at": "", "created_at": "", "updated_at": "" }
```

### `users/{uid}/chat_sessions/{id}/messages/{mid}`
```jsonc
{ "id": "", "session_id": "", "role": "user|assistant|system", "content": "",
  "citations": "[]",  // JSON string: [{source_id, source_name, page, quote, url, title, authors, year, publisher, doi}]
  "citation_style": "apa7|ieee|harvard|none", "reference_block": "", "model": "notebooklm",
  "nlm_job_id": "", "status": "sent|pending|done|failed", "error": "", "created_at": "" }
```

### `users/{uid}/research_jobs/{id}`
```jsonc
{ "id": "", "course_id": "", "notebook_id": "", "query": "", "mode": "deep|fast",
  "status": "queued|running|done|failed", "progress": "", "sources_found": 0, "sources_imported": 0,
  "task_id": "", "error": "", "created_at": "", "updated_at": "" }
```

### `users/{uid}/exam_sets/{id}`
```jsonc
{ "id": "", "course_id": "", "notebook_id": "", "title": "",
  "flashcards": "[{\"q\":\"\",\"a\":\"\",\"ref\":\"\"}]",  // JSON string — 50 phần tử
  "essays": "[{\"q\":\"\",\"hint\":\"\",\"ref\":\"\"}]",   // JSON string — 5 phần tử
  "attempts": "[]", "source_job_id": "", "created_at": "", "updated_at": "" }
```

### Hàng đợi task (global, server-only)
| Queue | Hành động hợp lệ |
|---|---|
| `nlm_task_queue` | `source_add`, `source_remove`, `chat_query`, `research_start`, `artifact_download`, `exam_generate` |
| `drive_task_queue` | `move_to_archive`, `soft_delete_local`, `hard_delete` |

```jsonc
// chat_query
{ "id":"", "action":"chat_query", "uid":"", "session_id":"", "message_id":"", "notebook_id":"",
  "prompt":"", "source_ids":"[]", "citation_style":"auto", "status":"pending", "created_at":"" }
// research_start
{ "id":"", "action":"research_start", "uid":"", "job_id":"", "notebook_id":"", "query":"",
  "mode":"deep", "status":"pending", "created_at":"" }
// artifact_download
{ "id":"", "action":"artifact_download", "uid":"", "course_id":"", "artifact_id":"", "artifact_name":"",
  "format":"pptx", "target_folder":"04_Ket_Qua_Xuat_Ban", "status":"pending", "created_at":"" }
// exam_generate
{ "id":"", "action":"exam_generate", "uid":"", "course_id":"", "notebook_id":"",
  "flashcard_count":50, "essay_count":5, "status":"pending", "created_at":"" }
// soft_delete_local  (Bước 3 cascade — PC Recycle Bin)
{ "id":"", "action":"soft_delete_local", "uid":"", "file_id":"", "local_path":"",
  "status":"pending", "created_at":"" }
```

---

## 3. Worker API — danh sách route CHÍNH XÁC (Phase 2/3/4)

Auth helper mới trong `lib/auth.js`: `requireAuthOrAgent(handler)` — chấp nhận `Authorization: Bearer <google_id_token>` **hoặc** `X-Agent-Secret`. Dùng cho các route agent gọi vào.

### 3.1 Nạp tài liệu (Dual Inflow — Phase 2)
| Method | Path | Auth | Mô tả |
|---|---|---|---|
| POST | `/api/files/upload/init` | user | (đã có) tạo Drive resumable session + doc `pending_upload` |
| POST | `/api/files/upload/complete` | user | (đã có) **SỬA**: chỉ queue `source_add` khi `is_output !== true` |
| POST | `/api/files/register` | agent | **MỚI** — Local watcher đăng ký file đã upload lên Drive. Body: `{filename, subject, document_type, folder_path?, sha256, drive_file_id, size_bytes, local_path, course_id?}` → tạo/merge file doc, `source_kind:'local_scan'`, `is_output` theo `folder_path`, `review_status` theo quy tắc §2; queue `source_add` **chỉ khi** `!is_output`. Trả `{file_id, is_output, queued_source_add}` |
| POST | `/api/files/check-hash` | auth-or-agent | **MỚI** — Body `{sha256}` → `{duplicate: bool, file_id?, drive_file_id?, filename?}` (bỏ qua doc `pending_upload`/`archived`) |
| GET | `/api/files` | user | (đã có) **SỬA**: thêm filter `review_status`, `is_output`, `source_kind`; trả thêm `review_status`, `is_output` |

### 3.2 Chat Session + Source Selector (Phase 3)
| Method | Path | Auth | Mô tả |
|---|---|---|---|
| GET | `/api/chat/sessions` | user | list session (`?course_id=&status=active|archived`) |
| POST | `/api/chat/sessions` | user | Body `{course_id?, notebook_id?, title?, source_ids?[]}` → 201 `{id}` |
| GET | `/api/chat/sessions/:id` | user | `{session, messages}` (messages: 50 mới nhất) |
| PATCH | `/api/chat/sessions/:id` | user | `{title?, status?, selected_source_ids?[]}` |
| DELETE | `/api/chat/sessions/:id` | user | mặc định **soft**: `status:'archived'`, `archived_at`; `?hard=1` → xoá session + toàn bộ messages |
| GET | `/api/chat/sessions/:id/messages` | user | `?since=<ISO>&limit=100` → `{messages, server_time}` (polling realtime) |
| POST | `/api/chat/sessions/:id/messages` | user | Body `{content, source_ids?[], citation_style?}` → append message `role:'user'`, queue `chat_query` → 202 `{message_id, job_id, status:'queued'}` |
| POST | `/api/chat/sessions/:id/agent-reply` | agent | Body `{job_id, message_id, content, citations[], citation_style?, model?}` → chạy Citation Engine, append message `role:'assistant'` (+`reference_block`), cập nhật session → `{message_id, citation_style, reference_block}` |
| POST | `/api/chat/sessions/:id/agent-fail` | agent | Body `{job_id, message_id, error}` → đánh dấu message `failed` (Orphan Data / lỗi CLI) |
| GET | `/api/chat/sources` | user | `?course_id=` → `{sources:[{file_id, filename, subject, document_type, source_id, review_status, size_bytes, updated_at}]}` — loại `review_status='rejected'` và `status!='uploaded'` |

### 3.3 Citation Engine — `cloudflare/workers/src/lib/citations.js`
- `detectCitationStyle(meta)` → `'apa7'|'ieee'|'harvard'` (có `doi`+`journal` → `ieee`; có `publisher`+`year`, không journal → `apa7`; chỉ `url` → `harvard`).
- `formatReferences(sources, style)` → `{style, references: string[], reference_block: string, inline_markers: string[]}`.
- `buildReferenceBlock(references)` → markdown `## 📚 Danh mục Tham khảo` + danh sách.
- Route: `POST /api/ai/citations/format` (auth-or-agent) Body `{sources:[{title, authors, year, publisher, journal, url, doi, source_id, page}], style:'auto'|'apa7'|'ieee'|'harvard', inline:true}` → `{style, references, reference_block, inline_markers}`.

### 3.4 Kiểm duyệt nguồn (Phase 4 — 3 trạng thái)
| Method | Path | Auth | Mô tả |
|---|---|---|---|
| GET | `/api/files/review` | user | `?status=unreviewed` (mặc định) → `{files, total}` |
| POST | `/api/files/:id/review` | user | Body `{review_status:'approved'|'rejected', note?}` → `approved`: nếu chưa sync thì queue `source_add`; `rejected`: queue `source_remove` (nếu có `notebooklm_source_id`), **KHÔNG** xoá file Drive. Trả `{status, review_status, steps}` |

### 3.5 Deep Research bất đồng bộ (Phase 4)
| Method | Path | Auth | Mô tả |
|---|---|---|---|
| POST | `/api/ai/research` | user | Body `{course_id, notebook_id?, query, mode:'deep'|'fast'}` → 202 `{job_id, task_id, status:'queued'}` + queue `research_start` |
| GET | `/api/ai/research` | user | `?course_id=&status=` → `{jobs}` |
| GET | `/api/ai/research/:jobId` | user | `{job}` |
| PATCH | `/api/ai/research/:jobId` | agent | `{status, progress?, error?, sources_found?}` |
| POST | `/api/ai/research/:jobId/sources` | agent | Body `{sources:[{filename, drive_file_id, sha256, url, title, authors, year, publisher, doi, local_path, size_bytes}]}` → tạo file doc `document_type:'unverified_web'`, `review_status:'unreviewed'`, `folder_path: FOLDER_MAP.unverified_web`, `source_kind:'deep_research'`, `is_output:false`; **KHÔNG** queue `source_add` (chờ duyệt). Cập nhật `sources_imported`. Trả `{imported:[{file_id, filename}], job}` |

> **Quyết định kỹ thuật:** dùng **Firestore queue + Python agent poll** thay cho Cloudflare Queues (giữ tương thích Workers Free tier; ghi rõ trong báo cáo audit).

### 3.6 Artifacts Downloader (Phase 4)
| Method | Path | Auth | Mô tả |
|---|---|---|---|
| POST | `/api/ai/artifact/download` | user | Body `{course_id, artifact_id?, artifact_name?, format:'pptx'|'docx'|'pdf', notebook_id?}` → 202 `{task_id}` + queue `artifact_download` (target `04_Ket_Qua_Xuat_Ban`) |
| POST | `/api/ai/artifact/complete` | agent | Body `{uid, course_id, filename, local_path, drive_file_id, sha256, size_bytes, artifact_name?}` → tạo file doc `document_type:'ket_qua'`, `is_output:true`, `source_kind:'artifact'`, `review_status:'approved'`; **KHÔNG** queue `source_add` (NO-LOOP). Trả `{file_id, is_output:true}` |
| GET | `/api/ai/artifacts` | user | `?course_id=` → `{artifacts:[...]}` (files `is_output === true`) |

### 3.7 Trạm Ôn Thi (Phase 4)
| Method | Path | Auth | Mô tả |
|---|---|---|---|
| POST | `/api/exam/sets/generate` | user | Body `{course_id, notebook_id?, flashcard_count=50, essay_count=5, title?}` → 202 `{job_id, task_id}` + queue `exam_generate` |
| POST | `/api/exam/sets` | agent | Body `{uid, course_id, title, flashcards[], essays[], source_job_id?}` → 201 `{set_id}` (lưu JSON string; cap 100 flashcard / 20 essay) |
| GET | `/api/exam/sets` | user | `?course_id=` → `{sets}` (KHÔNG trả `flashcards`/`essays`; có `flashcard_count`, `essay_count`) |
| GET | `/api/exam/sets/:id` | user | `{set}` đầy đủ (đã `JSON.parse`) |
| DELETE | `/api/exam/sets/:id` | user | `{status:'deleted'}` |
| POST | `/api/exam/sets/:id/attempt` | user | Body `{score, total, answers?}` → append vào `attempts` (giữ 50 lần gần nhất) |

### 3.8 Xoá an toàn (Safe Cascade Delete — SỬA `files/delete.js`)
`DELETE /api/files/:id` trả về đúng 4 bước:
1. `step1_nlm_remove` → queue `nlm_task_queue` `source_remove` (non-blocking).
2. `step2_drive_archive` → queue `drive_task_queue` `move_to_archive` (non-blocking).
3. `step3_firestore` (sync) + **MỚI** `step3_local_softdelete` → queue `drive_task_queue` `soft_delete_local` kèm `local_path` (non-blocking).
4. `step4_scheduled_hard_delete` (sync) → ghi `hard_delete_at = now + 90 ngày`, upsert `archived_files/{fileId}`.

Cron `cron/hard_delete.js` **SỬA**: task `hard_delete` phải kèm `local_path` và `filename` để agent xoá vĩnh viễn cả file local; vẫn ghi 1 dòng `file_deletion_logs` kèm `backup_cloud_link`.

---

## 4. Python Local Agent — file & handler CHÍNH XÁC

| File | Trách nhiệm | Trạng thái |
|---|---|---|
| `local_agent/constants.py` | Hằng số §1 | MỚI |
| `local_agent/file_watcher.py` | Watchdog song song (Local Inflow) | MỚI |
| `local_agent/api_client.py` | HTTP client tới Worker (`X-Agent-Secret`): `check_hash`, `register_file`, `agent_reply`, `agent_fail`, `patch_research`, `post_research_sources`, `artifact_complete`, `post_exam_set`, `format_citations` | MỚI |
| `local_agent/chat_task_handler.py` | `chat_query` → `nlm query` + Citation Engine qua Worker | MỚI |
| `local_agent/research_task_handler.py` | `research_start` → `nlm research start --mode deep` → poll → tải PDF → đăng ký nguồn | MỚI |
| `local_agent/artifact_task_handler.py` | `artifact_download` → `nlm artifact download` → Drive + local `04_Ket_Qua_Xuat_Ban/` | MỚI |
| `local_agent/exam_task_handler.py` | `exam_generate` → 50 flashcard + 5 tự luận (JSON) → `POST /api/exam/sets` | MỚI |
| `local_agent/nlm_task_handler.py` | `source_add` / `source_remove` (SỬA: `source_add` tự resolve `local_path`, fallback tải từ Drive) | SỬA |
| `local_agent/drive_sync.py` | Thêm `handle_soft_delete_local` (send2trash) + upload file local lên Drive theo `folder_path` (tạo folder lồng nhau) | SỬA |
| `local_agent/cascade_delete.py` | Giữ nguyên + thêm `resolve_local_path(subject, folder_path, filename)` | SỬA |
| `local_agent/main.py` | Đăng ký thêm watcher + handler mới | SỬA |

**Quy tắc bắt buộc cho agent:**
- Mọi lệnh `nlm` bọc trong `_run_nlm()` với timeout; lỗi phải báo về Worker (`agent-fail`, `PATCH research status='failed'`) — **không bao giờ** để task treo ở `processing`.
- Không tự xoá file thật ngoài 4 bước cascade; `soft_delete_local` dùng `send2trash` (fallback `_Archive_Trash_90Days/`).
- `file_watcher` chỉ **đăng ký** file vào Worker; Worker mới quyết định queue `source_add`. Watcher bỏ qua output/archive/temp/duplicate.

### Migration SQLite → Firestore (Phase 1, bắt buộc)
`scripts/migrate_sqlite_to_firestore.py` (Python, dùng `google.oauth2.service_account` + `google.auth.transport.requests.AuthorizedSession`, scope `https://www.googleapis.com/auth/datastore`):
- CLI: `--db data/files.db --service-account <json> --uid <firebase_uid> [--email <email>] [--dry-run] [--limit N]`
- Không có `--uid`: quét collection `users` tìm `profile/data.email` khớp `--email` → lấy `uid`.
- Map bảng: `majors` + `subjects` → `users/{uid}/courses/mig_<id>`; `files` → `users/{uid}/files/m_<sha256[:20]>` (idempotent); `ai_insights` → `users/{uid}/ai_insights`; `ai_chat_sessions` + `ai_chat_messages` → `users/{uid}/chat_sessions/{id}` + `/messages`; `web_research_sources` → `users/{uid}/files` (`document_type: unverified_web`); `notebooklm_sync_log` → `users/{uid}/notebooklm_sync_logs`; `file_deletion_logs` → `file_deletion_logs` (global).
- `document_type` suy ra từ `files.path`; `review_status` theo §2; `is_output` = folder bắt đầu bằng `04_Ket_Qua_Xuat_Ban`.
- In báo cáo `[DONE]/[SKIP]/[ERROR]` từng bảng; `--dry-run` chỉ đếm.

---

## 5. Frontend (Cloudflare Pages) — file CHÍNH XÁC

| File | Trách nhiệm |
|---|---|
| `src/js/constants.js` | Hằng số §1 |
| `src/js/api.js` (SỬA) | Thêm `chatApi`, `researchApi`, `artifactApi`, `examApi`, `reviewApi`, `citationsApi` |
| `src/js/realtime.js` (MỚI) | Polling 3s `GET /api/chat/sessions/:id/messages?since=`; dùng Firestore `onSnapshot` nếu `window.__FIREBASE_CONFIG` tồn tại; luôn fallback polling khi lỗi |
| `src/js/pages/chat.js` (MỚI) | Multi-turn chat: tạo/đổi tên/xoá session, chọn source (checkbox = Source Selector), gửi prompt, hiển thị citation + Danh mục Tham khảo |
| `src/js/pages/review.js` (MỚI) | Hàng đợi duyệt nguồn: thẻ vàng `unreviewed` với [✅ Duyệt] / [🗑️ Xoá] |
| `src/js/pages/exam.js` (MỚI) | Trạm ôn thi: tạo đề (50 flashcard + 5 tự luận), cày quiz, lưu điểm |
| `src/js/pages/artifacts.js` (MỚI) | Danh sách `.pptx/.docx` trong `04_Ket_Qua_Xuat_Ban` + nút tải artifact |
| `src/js/pages/dashboard.js` (SỬA) | Thêm badge `review_status`, badge output `⛔ NO-LOOP`, filter |
| `src/index.html` (SỬA) | Thêm tab 💬 Chat AI / ✅ Duyệt nguồn / 📝 Ôn thi / 📦 Artifacts |
| `scripts/build.js` (MỚI) | Build tĩnh: copy `src/**` → `dist/` (bỏ `node_modules`, `.wrangler`) để `npm run build` + `wrangler pages deploy dist` chạy đúng quy trình |
| `package.json` (SỬA) | `"build": "node scripts/build.js"`, `"deploy": "wrangler pages deploy dist --project-name=ths-organizer"` |

Ràng buộc UI: giữ theme Obsidian hiện có (`css/main.css`, `css/components.css`), không thêm framework, ES module thuần.

---

## 6. Kiểm thử & Phát hành (release)

1. `node --check` toàn bộ JS trong `cloudflare/workers/src` + `cloudflare/pages/src/js` (không có bundler).
2. `python -m pytest -q` phải xanh (không regression).
3. `npx wrangler deploy --dry-run` (trong `cloudflare/workers`) phải build thành công.
4. Secrets: `FIREBASE_SERVICE_ACCOUNT` (từ `firebase/thsautoorganizer-firebase-adminsdk-*.json`), `GOOGLE_CLIENT_ID` = `437903639644-img3tmoj4hdji3nkocknmitmk197k3lv.apps.googleusercontent.com`, `AGENT_SECRET` (sinh mới → ghi vào `config.json` local, file này KHÔNG được track git).
5. Deploy: `npx wrangler deploy` (workers) → `npm run build` + `npm run deploy` (pages project `ths-organizer`).
6. Git: bổ sung `.gitignore` (`temp_test_slide.pptx`, `database.db`, `.wrangler/`, `cloudflare/pages/dist/`, `--output`); `git rm --cached config.json` (**SECURITY** — đang bị track dù đã ignore); `git add <đường dẫn cụ thể>` → commit → `git push origin main`.
7. Báo cáo: URL Worker `/health`, URL Pages, commit hash, danh sách secrets đã set (KHÔNG in giá trị).

---

## 7. ĐÍNH CHÍNH QUAN TRỌNG — NLM CLI thực tế (v0.11.6) khác đặc tả gốc

Đã kiểm chứng trực tiếp bằng `--help` trên máy (`C:\Program Files\Python313\Scripts\nlm.exe`, version 0.11.6). **Đặc tả gốc ghi `nlm artifact download` / `nlm source remove` / `nlm query` — BA LỆNH NÀY KHÔNG TỒN TẠI.** Dùng đúng các lệnh dưới đây:

| Mục đích (đặc tả gốc) | LỆNH THẬT (0.11.6) |
|---|---|
| Thêm source | `nlm source add <NOTEBOOK_ID> --file "<path>" --wait --wait-timeout 600 --json` (hoặc `--drive <fileId> --type pdf`, `--url <u>`, `--title <t>`) |
| Gỡ source | `nlm source delete <SOURCE_ID> [<ID2> ...] --confirm --json` (KHÔNG có `source remove`) |
| Liệt kê source | `nlm source list <NOTEBOOK_ID> --json` |
| Chat hỏi đáp | `nlm notebook query <NOTEBOOK_ID> "<câu hỏi>" --json [--source-ids a,b] [--new-conversation] [--conversation-id <id>] [--timeout 180]` |
| Deep research | `nlm research start "<query>" --mode deep --notebook-id <NOTEBOOK_ID> --source web [--force]`; poll `nlm research status <NOTEBOOK_ID> --max-wait 0 --json`; import `nlm research import <NOTEBOOK_ID> [TASK_ID] [--cited-only]` |
| Tải artifact slide (.pptx) | `nlm download slide-deck <NOTEBOOK_ID> --format pptx --output "<path>.pptx"` |
| Tải toàn bộ artifact | `nlm download all <NOTEBOOK_ID> --output-dir "<dir>" --slide-format pptx --interactive-format json --skip-existing --json` |
| Trạng thái artifact | `nlm studio status <NOTEBOOK_ID> --json --mcp-compatible` |
| Quiz trắc nghiệm (50 câu) | `nlm quiz create <NOTEBOOK_ID> --count 50 --difficulty 3 --confirm --json` → `nlm download quiz <NOTEBOOK_ID> --format json --output "<path>.json"` |
| Flashcard | `nlm flashcards create <NOTEBOOK_ID> --difficulty hard [--focus "<prompt>"] --confirm --json` → `nlm download flashcards <NOTEBOOK_ID> --format json --output "<path>.json"` |
| Báo cáo markdown | `nlm download report <NOTEBOOK_ID> --output "<path>.md"` |
| Kiểm tra phiên chat cũ (Orphan Data) | `nlm chats list <NOTEBOOK_ID> --json --limit 20` |

**Suy ra thay đổi hợp đồng (áp dụng ngay):**
- `nlm_task_handler.handle_source_add`: gọi `nlm source add <notebook_id> --file <local_path> --wait --json` (notebook_id là ARGUMENT, không phải `--notebook`) và thêm `--source-id` đầu ra lấy từ JSON để lưu `notebooklm_source_id`.
- `nlm_task_handler.handle_source_remove`: gọi `nlm source delete <source_id> --confirm` (không raise khi lỗi để không chặn cascade).
- `chat_task_handler`: dùng `nlm notebook query` (KHÔNG có `nlm query`); giữ `--conversation-id` để multi-turn thật khi có.
- `research_task_handler`: `nlm research start ... --mode deep --notebook-id ... --source web` (mode `deep` CHỈ hỗ trợ web) → poll `nlm research status --max-wait 0` theo chu kỳ → `nlm research import` → lấy danh sách nguồn để tải PDF.
- `artifact_task_handler`: giữ nguyên route `/api/ai/artifact/download`, nhưng bên dưới gọi `nlm download slide-deck --format pptx` (hoặc `nlm download all`), KHÔNG gọi `nlm artifact ...`.
- `exam_task_handler`: 50 câu trắc nghiệm = `nlm quiz create --count 50`; 5 câu tự luận = `nlm notebook query` với prompt yêu cầu JSON 5 câu phản biện (hoặc `nlm flashcards create --focus`), rồi chuẩn hoá về mảng `flashcards`/`essays`.

Mọi lệnh nlm phải bọc timeout + `encoding="utf-8"`; nếu CLI trả về lỗi thì log rõ ràng và mark task `failed` (KHÔNG để task treo `processing`).
