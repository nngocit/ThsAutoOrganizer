# AUDIT BASELINE — T1 (trước khi teammate sửa code)

> **Ngày:** 23/09/2026 · **Auditor:** `audit` (AUDIT LEAD) · **Task:** `task_0001`
> **Phạm vi:** snapshot codebase tại commit `8f0b5cd` (branch `main`) + vùng làm việc có 5 file đang dirty.
> **Nguồn sự thật:** `docs/superpowers/specs/2026-09-23-phase2-4-api-contract.md` (§1–§7) + `2026-09-22-full-cloud-design-spec.md`.
> **Nguyên tắc:** KHÔNG tin báo cáo teammate; mọi kết luận dưới đây đều kèm `file:line` + kết quả lệnh thật. KHÔNG sửa code nguồn.

### Lệnh kiểm chứng đã chạy (kết quả thật)
`python -m pytest -q` → **80 passed in 21.80s** · `python -m compileall -q local_agent scripts` → exit 0 nhưng in `Can't list 'scripts'` · `node --check` toàn bộ `cloudflare/workers/src/**/*.js` → **17 files, 0 failures** · `nlm --version` → **0.11.6** · `git ls-files`/`git log --oneline` → read-only, bằng chứng ở §3 · `nlm <group> --help` → bằng chứng ở §4.

Working tree lúc audit (`git status --porcelain`): 6 file dirty (`config.json`, `api.js`, `app.js`, `workers/src/index.js`, `workers/src/lib/firebase.js`, `local_agent/config_loader.py`) + untracked `--output`, `.wrangler/`, `database.db`, `temp_test_slide.pptx`, `data/artifacts/`, spec mới. ⇒ Đây là **baseline đóng băng**; teammate đã bắt đầu ghi file sau thời điểm này.

---

## 1. `[DONE]` — Đã có và chạy được

**Workers** (`cloudflare/workers/src/`)
- Entry + mount 5 router + `/health` + 404 + onError: `index.js:35-39`, `:30-32`, `:42-44`, `:47-50`; cron `scheduled` khớp `'0 2 * * *'` `:55-60` + `wrangler.toml:10`
- Auth: `verifyIdToken` (kiểm `aud` + `exp`) `lib/auth.js:12-40`; `requireAuth:55-70`; `requireAgentAuth:76-85`
- Firestore REST client (tự ký JWT RS256) `lib/firebase.js:8-48`; `firestoreGet/Set/List/Delete` `:84,96,125,135`; `fromFirestoreDoc:69`; `toFirestoreDoc` stringify mảng/object `:63` — **đúng quy ước §2**
- CORS whitelist helper `lib/cors.js:4-28` (`withCors:36`, `optionsResponse:50`)
- Upload init `routes/files/upload_init.js:72-136` (validate ext `:85-88`); upload complete `upload_complete.js:40-110` (regex sha256 `:51`, chống duplicate `:15-22`); list `list.js:21-71`
- Cascade bước 1/2/3 + chống xoá 2 lần: `delete.js:106-108`, `:111-113`, `:116`, `:99-101`; helpers `:11-30,:33-52,:55-81`
- Cron hard delete: ghi `file_deletion_logs` có `backup_cloud_link` **trước** khi xoá `cron/hard_delete.js:39-52`; queue agent `:55-66`; xoá `archived_files` `:69-72`
- Task queue API + whitelist queue `routes/sync/index.js:19-42,:49-96, VALID_QUEUES:11`
- Insights CRUD `routes/insights/create.js:16-73`; Courses CRUD + link NLM `routes/courses/index.js:14,33,70`
- Rules: user chỉ `users/{uid}/**`; queue/logs `allow: if false` `firebase/firestore.rules:6-24`

**Python Agent** (`local_agent/`)
- Poller 2 queue daemon, mark `processing`→`done`/`failed`, chịu lỗi mạng: `firestore_poller.py:19-121`, `:85,:89,:93`, `:56-58,:71-72`
- Đăng ký 4 action `main.py:57-64`; shutdown sạch `:26-32,:68-69,:81-85`
- `_run_nlm()` có timeout + `encoding="utf-8"` `nlm_task_handler.py:23-46`
- Soft delete `send2trash` + fallback archive `cascade_delete.py:61-83`; hard delete local `:86-111`
- Drive: tạo folder lồng nhau (`parent_id`), `move_to_archive`, hard delete `drive_sync.py:38-62,:65-94,:97-120`
- Config loader (defaults + merge + env override) `config_loader.py:23-71`; deps `requirements.txt:1,11`

**Frontend Pages** (`cloudflare/pages/src/`)
- `apiFetch`/`buildHeaders`/`computeSHA256` `js/api.js:16-47,:128-134`; 4 API object `:53,68,93,110`
- 3 tab + filter `index.html:37-42,:65-80`; dashboard card/badge/xoá `js/pages/dashboard.js:31-56,:78-87`
- Study Hub + citation drawer + quiz player `js/pages/study_hub.js:14-44`, `js/components/quiz_player.js`; upload 3 phase `js/components/file_upload.js`


---

## 2. `[MISSING/FIX]` — Thiếu / sai so với hợp đồng

### 2.1 Workers — route & lib chưa tồn tại
| # | Hạng mục hợp đồng | Trạng thái | Bằng chứng |
|---|---|---|---|
| W1 | `lib/folders.js` (FOLDER_MAP, OUTPUT_FOLDER, NO_LOOP_FOLDERS, HARD_DELETE_DAYS, `isOutputFolder`) | **THIẾU** | `lib/` chỉ có `auth.js`, `cors.js`, `firebase.js`. `FOLDER_MAP` bị **copy trùng** trong `routes/files/upload_init.js:15-21`; `SUPPORTED_EXTENSIONS` copy ở `upload_init.js:11-13`; `HARD_DELETE_DAYS=90` hard-code ở `delete.js:57` và `cron/hard_delete.js:34` |
| W2 | `requireAuthOrAgent(handler)` | **THIẾU** | `lib/auth.js` chỉ có `requireAuth:55` + `requireAgentAuth:76` |
| W3 | `POST /api/files/register` (agent) | **THIẾU** | `routes/files/index.js:12-21` chỉ mount upload/list/delete |
| W4 | `POST /api/files/check-hash` (auth-or-agent) | **THIẾU** | Không có `check_hash.js`; logic tương tự nằm phía user trong `upload_complete.js:15-22` (list 200 doc rồi lọc) |
| W5 | `GET /api/files` filter `review_status`, `is_output`, `source_kind` | **THIẾU** | `list.js:26-45` chỉ filter subject/status/document_type/course_id |
| W6 | Chat sessions + messages + agent-reply/agent-fail + `/api/chat/sources` (Phase 3) | **THIẾU TOÀN BỘ** | Không có `routes/chat/**`; `index.js:35-39` không mount `/api/chat` |
| W7 | `lib/citations.js` + `POST /api/ai/citations/format` | **THIẾU** | Không có `lib/citations.js`; `index.js:37` chỉ mount insights |
| W8 | Review 3 trạng thái: `GET /api/files/review`, `POST /api/files/:id/review` | **THIẾU** | Không có field `review_status` ở bất kỳ đâu: `upload_init.js:106-123` tạo doc **không** set `review_status`/`source_kind`/`local_path` |
| W9 | Deep research async: `POST/GET /api/ai/research`, `/:jobId`, `PATCH`, `/:jobId/sources` | **THIẾU** | Không có `research_jobs` + không route |
| W10 | Artifacts: `POST /api/ai/artifact/download`, `/complete`, `GET /api/ai/artifacts` | **THIẾU** | Không có route; `is_output` chỉ được set 1 lần ở `upload_init.js:92,114` |
| W11 | Exam: `POST /api/exam/sets/generate`, `POST/GET/DELETE /api/exam/sets`, `/attempt` | **THIẾU** | Không có `exam_sets` + không route |
| W12 | `delete.js` **bước 3 `step3_local_softdelete`** (queue `soft_delete_local` kèm `local_path`) | **THIẾU** | `delete.js:103-118` chỉ có step1/step2/step3_firestore; bước 4 **chỉ là comment** (`:118`) — response không có key `step4_scheduled_hard_delete` |
| W13 | Cron `hard_delete` task kèm `local_path` + `filename` | **SAI/THIẾU** | `cron/hard_delete.js:57-65` payload chỉ có `drive_file_id`; `local_path`/`filename` **không** được gửi ⇒ agent **không thể** xoá file local (dù `drive_sync.py:114-118` đã sẵn sàng đọc `local_path`) |
| W14 | NO-LOOP lớp 2 tại `upload_complete.js` | **VI PHẠM** | `upload_complete.js:84-98` queue `source_add` **vô điều kiện** khi có `course_id`, **không** kiểm tra `is_output` ⇒ file trong `04_Ket_Qua_Xuat_Ban` vẫn bị nạp vào NotebookLM |
| W15 | NO-LOOP lớp 1 tại `upload_init.js` | **YẾU** | `upload_init.js:92` `isOutput = docType === 'ket_qua'` — dựa vào `document_type` client gửi, **không** dựa prefix `folder_path` như hợp đồng §1 ⇒ client chọn `document_type=giao_trinh` + folder `04_...` sẽ lọt |
| W16 | `PATCH` bị chặn ở CORS tầng ngoài | **SAI** | `index.js:22` `allowMethods` **thiếu `PATCH`** (chỉ GET/POST/PUT/DELETE/OPTIONS) dù `lib/cors.js:24` có PATCH ⇒ preflight cho `PATCH /api/chat/sessions/:id` (hợp đồng §3.2) sẽ fail từ browser |
| W17 | CORS wildcard đè whitelist | **RỦI RO** | `index.js:20-24` dùng `origin:'*'` (mở toàn bộ) trong khi `lib/cors.js:4-11` giữ whitelist; `withCors` gọi sau sẽ ghi đè ⇒ chính sách CORS không nhất quán |
| W18 | `X-Agent-Secret` thiếu trong `Access-Control-Allow-Headers` | **RỦI RO** | `index.js:23` + `lib/cors.js:25` chỉ khai `Content-Type, Authorization` |
### 2.2 Python Agent — file & lệnh sai
| # | Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|---|
| A1 | `local_agent/constants.py` | **THIẾU** | Không tồn tại; `poll_interval_seconds`/`drive_archive_folder` hard-code default ở `config_loader.py:12-16` |
| A2 | `local_agent/file_watcher.py` (watchdog) | **THIẾU** | Không tồn tại dù `requirements.txt:1` đã khai `watchdog` |
| A3 | `local_agent/api_client.py` | **THIẾU** | Không tồn tại; poller gọi HTTP trực tiếp (`firestore_poller.py:53,70`) — **không** có API cho `agent_fail`, `patch_research`, `post_exam_set`, `artifact_complete`, `format_citations` |
| A4 | `chat_task_handler.py`, `research_task_handler.py`, `artifact_task_handler.py`, `exam_task_handler.py` | **THIẾU** | Không tồn tại; `main.py:57-64` chỉ đăng ký 4 action |
| A5 | `soft_delete_local` handler | **THIẾU** | `main.py:63-64` chỉ đăng ký `move_to_archive` + `hard_delete`; dispatcher `drive_sync.py:129-132` **không** có nhánh `soft_delete_local` ⇒ task loại này `raise ValueError` (`drive_sync.py:135`) rồi bị mark `failed` |
| A6 | `cascade_delete.resolve_local_path()` | **THIẾU** | `cascade_delete.py` không có hàm này |
| A7 | **`nlm source add` SAI CÚ PHÁP** | **SAI — CHẶN CHỨC NĂNG** | `nlm_task_handler.py:87-90`: `["source","add"] + ["--notebook", id] + [file]`. CLI thật (`nlm source add --help`): `Usage: nlm source add [OPTIONS] {notebook_id}` — `notebook_id` là **ARGUMENT bắt buộc**, **KHÔNG có** flag `--notebook`; file phải truyền qua `--file`. Lệnh hiện tại sẽ lỗi `No such option: --notebook` ⇒ **mọi task `source_add` fail** |
| A8 | **`nlm source remove` KHÔNG TỒN TẠI** | **SAI — CHẶN CHỨC NĂNG** | `nlm_task_handler.py:122`: `["source","remove"]`. `nlm source --help` liệt kê: list/add/get/describe/content/rename/**delete**/stale/sync — **không có `remove`**. Phải là `nlm source delete <id> --confirm` |
| A9 | `handle_source_add` không dùng `--wait`/`--json` ⇒ `source_id` rỗng | **SAI** | `nlm_task_handler.py:92` không có `--wait` (không chờ ingest) và không `--json` (không parse được source ID). `routes/sync/index.js:83-86` lưu `notebooklm_source_id = result \|\| ''`, nhưng `firestore_poller.py:89` mark `done` **không kèm `result`** ⇒ **`notebooklm_source_id` luôn rỗng** ⇒ tới bước 1 cascade, `queueNLMRemove` sẽ `skipped: no_source_id` (`delete.js:12`) |
| A10 | `source_add` đọc `task["file_path"]` | **SAI** | `nlm_task_handler.py:66,79` đọc `file_path`, nhưng payload queue do Worker tạo (`upload_complete.js:88-97`) **không có** `file_path`/`local_path` ⇒ rơi nhánh `source_target = filename` (`:82`) ⇒ `nlm` nhận **tên file trần**, gần như chắc chắn fail |
| A11 | `drive_sync.py` chưa upload file local theo `folder_path` | **THIẾU** | `_find_or_create_folder` có sẵn (`drive_sync.py:38-62`, hỗ trợ `parent_id`), nhưng dispatcher `:129-132` không có action upload/register |
| A12 | Fallback archive tạo `_Archive_Trash_90Days/` **bên trong** cây tài liệu | **RỦI RO VÒNG LẶP** | `cascade_delete.py:75-79`: `archive_base = path.parent / archive_folder_name` — archive nằm cùng cấp file gốc, tức **trong** cây mà watcher sẽ theo dõi |

### 2.3 Frontend · Scripts · Migration
| # | Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|---|
| F1 | `src/js/constants.js` | **THIẾU** | `pages/src/js/` chỉ có `api.js`, `app.js`, `pages/`, `components/` |
| F2 | `chatApi`, `researchApi`, `artifactApi`, `examApi`, `reviewApi`, `citationsApi` | **THIẾU** | `api.js` chỉ export `authApi:53`, `filesApi:68`, `coursesApi:93`, `insightsApi:110` |
| F3 | `realtime.js`, `pages/chat.js`, `pages/review.js`, `pages/exam.js`, `pages/artifacts.js` | **THIẾU** | Không tồn tại |
| F4 | Badge `review_status` + `⛔ NO-LOOP` ở dashboard | **THIẾU** | `dashboard.js:17-22` chỉ có `NLM_BADGE_MAP`; `renderFileCard:31-56` không render review/output |
| F5 | 4 tab mới trong `index.html` | **THIẾU** | `index.html:37-42` chỉ có 3 tab |
| F6 | `scripts/build.js` + `package.json` build→dist | **THIẾU** | `pages/package.json:5-8` chỉ có `dev` + `deploy src --project-name=ths-organizer` (deploy **`src`**, không phải `dist`) |
| S1 | Thư mục `scripts/` | **KHÔNG TỒN TẠI** | `python -m compileall -q local_agent scripts` in `Can't list 'scripts'` |
| S2 | `scripts/migrate_sqlite_to_firestore.py` (Phase 1 bắt buộc) | **THIẾU** | Không tồn tại. Lưu ý: `config.json:4` trỏ `data\files.db` nhưng **không có** `data/files.db`; chỉ có `database.db` **0 byte** ở root ⇒ **không có dữ liệu SQLite để migrate** — cần lead xác nhận trước khi viết script |
| S3 | `nlm query` — **đính chính §7** | **§7 SAI** | §7:282 khẳng định "`nlm query` KHÔNG TỒN TẠI". Thực đo: `nlm query --help` → **exit 0**, `Usage: nlm query [OPTIONS] COMMAND [ARGS]...` + subcommand `notebook`; **và** `nlm notebook --help` cũng có `query`. ⇒ **tồn tại CẢ HAI dạng** (alias). §7:289 dùng `nlm notebook query` là **đúng**; nhưng khẳng định ở §7:282 là **sai** — không cần sửa code theo hướng "không có `nlm query`" |

---

## 3. SAFETY & LOOP CHECK

### 3.1 Cascade delete — đúng 4 bước? Đúng thứ tự?
Hợp đồng §3.8 yêu cầu thứ tự: **AI trước → Drive → Firestore + local → hẹn hard delete 90 ngày**.

| Bước hợp đồng | Hiện trạng | Bằng chứng | Đánh giá |
|---|---|---|---|
| 1. `step1_nlm_remove` (queue `nlm_task_queue`/`source_remove`, non-blocking) | CÓ | `delete.js:106-108` + `queueNLMRemove:11-30` | ✅ đúng thứ tự |
| 2. `step2_drive_archive` (queue `move_to_archive`) | CÓ | `delete.js:111-113` + `queueDriveArchive:33-52` | ✅ đúng thứ tự |
| 3. `step3_firestore` (sync) **+ `step3_local_softdelete`** (queue `soft_delete_local` kèm `local_path`) | **CHỈ CÓ PHẦN SYNC** | `delete.js:116` + `softDeleteFirestore:55-81`. **KHÔNG** queue `soft_delete_local`; `local_path` không hề được đọc/ghi trong `delete.js` | ❌ **THIẾU BƯỚC 3 (local soft delete)** |
| 4. `step4_scheduled_hard_delete` (`hard_delete_at = +90d` + upsert `archived_files`) | CÓ (gộp vào bước 3) | `delete.js:57` tính `hardDeleteAt`; `:63` ghi vào file doc; `:68-78` upsert `archived_files` | ⚠️ **Hành vi đúng, hình thức sai**: `:118` chỉ là **comment**, response **không** có key `step4_scheduled_hard_delete` ⇒ không thể assert bước 4 |

**Kết luận 3.1**: 4 bước **đúng thứ tự** (AI → Drive → Firestore → hẹn 90 ngày) nhưng **thiếu hẳn việc xoá mềm file trên PC**. Hệ quả thực tế: file đã biến mất khỏi Drive + Firestore nhưng **vẫn nằm nguyên trên ổ H:**; và vì `local_path` không được lưu ở **bất kỳ đâu** (`upload_init.js:106-123` không set), cron về sau **cũng không thể** xoá local ⇒ **"xoá" là không trọn vẹn**.

### 3.2 Cron `hard_delete.js` có xoá file LOCAL vĩnh viễn không?
**KHÔNG.** `cron/hard_delete.js:57-65` tạo task `hard_delete` với payload chỉ `id, action, uid, file_id, drive_file_id, status, created_at` — **thiếu `local_path` và `filename`** (hợp đồng §3.8 yêu cầu rõ).
Phía agent **đã sẵn sàng**: `drive_sync.py:114-118` đọc `task["local_path"]` rồi gọi `hard_delete_file()` (`cascade_delete.py:86-111`), nhưng nhận chuỗi rỗng nên **bỏ qua** ⇒ file local tồn tại **vĩnh viễn**, vượt cả thời hạn 90 ngày. Đây là **lỗi chặn hợp đồng**, không chỉ là thiếu tính năng.

### 3.3 Nguy cơ vòng lặp vô tận với `04_Ket_Qua_Xuat_Ban/`
Hợp đồng §1 yêu cầu **3 lớp phòng thủ**. Đo thực tế:

| Lớp | Yêu cầu | Hiện trạng | Kết luận |
|---|---|---|---|
| 1 | `upload_init.js`/`files/register.js`: `is_output = folder_path bắt đầu bằng OUTPUT_FOLDER` | `upload_init.js:92`: `isOutput = docType === 'ket_qua'` — **không** so prefix `folder_path`; `files/register.js` chưa tồn tại | ❌ **CHƯA ĐẠT** |
| 2 | `upload_complete.js`/`files/register.js`: **KHÔNG** queue `source_add` khi `is_output === true` | `upload_complete.js:84-98` queue `source_add` khi có `course_id`, **không** đọc `is_output` (field **đã có** trong doc từ `upload_init.js:114` nhưng không dùng) | ❌ **VI PHẠM TRỰC TIẾP** |
| 3 | `file_watcher.py`: bỏ qua `NO_LOOP_FOLDERS` + `~$*` + `.tmp` + `<1000 bytes` + duplicate `sha256` | `local_agent/file_watcher.py` **CHƯA TỒN TẠI** | ⚪ **N/A hôm nay, 0% sẵn sàng** |

**Đánh giá loop**: Hôm nay **chưa** xảy ra vì (a) watcher chưa tồn tại, (b) `/api/ai/artifact/complete` chưa tồn tại. Nhưng khi Phase 4 hoàn thành, chuỗi sau sẽ tạo **vòng lặp vô tận**:
`artifact_download` → tải `.pptx` vào `04_Ket_Qua_Xuat_Ban/` → watcher thấy file mới → thiếu lớp 3 → `POST /api/files/register` (thiếu lớp 1) → `upload_complete`/register queue `source_add` (thiếu lớp 2) → NLM ingest → sinh artifact mới → ghi lại `04_...` → **quay lại điểm đầu**.
- **Bằng chứng gián tiếp có thật**: file rỗng tên `--output` ở **root repo** (untracked, 0 byte) — dấu vết một lệnh `nlm download ... --output <path>` bị PowerShell tách tham số sai. Cho thấy đường ghi artifact vào filesystem **đã từng chạy**: đường dẫn đầu ra phải là **tuyệt đối**, không dùng `--output` trần.
- **Rủi ro loop thứ hai**: `cascade_delete.py:75-79` tạo `_Archive_Trash_90Days/` **bên trong** thư mục môn ⇒ nếu watcher chỉ chặn theo **cụm tiền tố cố định** mà không chặn mọi thư mục tên `_Archive_Trash_90Days` ở **mọi độ sâu** + không chặn hậu tố `__YYYYMMDD_HHMMSS` (`cascade_delete.py:27-30`), file trong archive sẽ bị quét lại ⇒ **loop thứ hai**.

### 3.4 Rà soát secret bị commit (`git ls-files` + `git log`, read-only)
| Mục | Kết quả | Bằng chứng |
|---|---|---|
| `config.json` có bị track? | **CÓ — ĐANG BỊ TRACK** | `git ls-files \| findstr` → `config.json`. `.gitignore:6` đã ignore nhưng ignore **không** áp dụng cho file đã track ⇒ vẫn nằm trong index (khớp §6.6 hợp đồng) |
| Giá trị `agent_secret` có trong lịch sử git? | **KHÔNG** (0 kết quả) | `git --no-pager log -p -- config.json \| Select-String 'agent_secret'` → **0 dòng**. Bản commit của `config.json` cũ hơn lần thêm key `agent_secret` (hiện đang dirty ở working tree). **Mức độ lộ: chưa lộ ra GitHub** |
| Secret yếu bị commit ở nơi khác? | **CÓ — RỦI RO CAO** | `local_agent/config_loader.py:11` hard-code default `"agent_secret": "my_***_123"` (placeholder yếu, 19 ký tự). File **được track** ⇒ secret mặc định **đã nằm trong git history**; ai đọc repo cũng biết. Nếu `wrangler secret put AGENT_SECRET` không set giá trị khác, kẻ tấn công chỉ cần `X-Agent-Secret` là gọi được **toàn bộ** `/api/tasks/:queue` (đọc task + PATCH `done/failed` của mọi user) |
| `config.json` chứa gì? | Thông tin hạ tầng + secret yếu | `config.json:2` root folder local, `:3` email chủ tài khoản, `:27` Worker URL, `:28` `agent_secret` ⇒ lộ cả cấu trúc đường dẫn máy trạm |
| Các file nhạy cảm khác | Không bị track | `findstr` không trả `token.json`/`credentials.json`/`*.pptx`/`*.exe`; `.gitignore:41-46` đã chặn `credentials.json`, `token.json`, `*firebase-adminsdk*.json` |
| File rác/nặng chưa ignore | **CÓ** | `git status --porcelain` → untracked: `temp_test_slide.pptx` (18.3 MB), `database.db` (0 B), `--output` (0 B), `.wrangler/`, `cloudflare/pages/.wrangler/`, `data/artifacts/` ⇒ **khớp đúng danh sách §6.6 cần bổ sung vào `.gitignore`** |
| Commit gần nhất | `8f0b5cd security: add config.json to .gitignore to protect agent_secret` | `git --no-pager log --oneline -8` |

### 3.5 Task treo ở `processing` + kiểm tra ownership (IDOR)
- **Rủi ro treo `processing` CÓ THẬT**: `firestore_poller.py:85` mark `processing` **trước** khi chạy handler. Nếu tiến trình bị kill / mất mạng ngay sau đó — hoặc chính `_mark_task(..., 'failed')` ở `:93` cũng thất bại do mất mạng — task **kẹt vĩnh viễn ở `processing`**, vì `GET /api/tasks/:queue` chỉ trả `status === 'pending'` (`routes/sync/index.js:34`) và **không có** timeout/requeue/reclaim ở Worker lẫn agent. Hợp đồng §4 yêu cầu "**không bao giờ** để task treo ở `processing`" ⇒ **CHƯA ĐẠT**. (Xác suất thấp/hiếm nhưng hậu quả là mất task im lặng — không có alert.)
- **Kiểm tra IDOR tầng hiện tại**: các route hiện có **đều đúng** — `delete.js:91` và `list.js:33` truy cập `users/${user.uid}/...`, `uid` lấy từ token đã verify (`auth.js:34`), **không** nhận `uid` từ client ⇒ **không có IDOR**.
- ⚠️ **Cảnh báo cho Phase 3/4**: nhiều route **mới** trong hợp đồng nhận `uid` **trong body** (`/api/files/register`, `/api/ai/artifact/complete`, `/api/exam/sets`, `agent-reply`…). Với `requireAgentAuth` (shared secret dùng chung, `auth.js:76-85`), **mọi** request agent đều có thể ghi vào **bất kỳ** `users/{uid}` nào ⇒ không có phân quyền theo user. Rủi ro chấp nhận được **chỉ khi** `AGENT_SECRET` mạnh + không lộ (xem §3.4) — hiện secret đang là placeholder yếu ⇒ **rủi ro thực tế CAO**.

---

## 4. Ghi chú kỹ thuật — `nlm` CLI THẬT (v0.11.6)

Bằng chứng: `nlm --version` → `nlm version 0.11.6`; tất cả dòng dưới đây đọc trực tiếp từ `--help` đã chạy trên máy này (không suy đoán, không copy tài liệu).

### 4.1 Group lệnh có thật (từ `nlm --help`)
`login, auth, notebook, label, note, source, chats, chat, studio, research, alias, config, download, share, export, skill, setup, doctor, batch, cross, pipeline, tag, usage, audio, report, quiz, flashcards, mindmap, slides, infographic, video, data-table, create, list, get, delete, add, rename, status, describe, query, sync, content, stale, configure, set, show, install, uninstall, update`

**KHÔNG tồn tại** (đã đo, exit code 1): `nlm artifact`, `nlm mcp`.
**Tồn tại dạng alias**: `nlm query notebook` ≡ `nlm notebook query` (cả hai `--help` đều exit 0).

### 4.2 Bảng lệnh + flag ĐÃ KIỂM CHỨNG
| Mục đích | LỆNH THẬT (đã đo) | Ghi chú cho teammate `agent` |
|---|---|---|
| Thêm source | `nlm source add <NOTEBOOK_ID> --file "<ABS_PATH>" --wait --wait-timeout 600 --json` | `notebook_id` là **ARGUMENT**; flag `--url/-u`, `--text/-t`, `--drive/-d`, `--youtube/-y`, `--title`, `--type` |
| Gỡ source | `nlm source delete <SOURCE_ID> [<ID2>…] --confirm --json` | **KHÔNG có `source remove`**; bắt buộc `--confirm/-y` để bỏ prompt |
| Liệt kê source | `nlm source list <NOTEBOOK_ID> --json` | có `--json` |
| Chat hỏi đáp | `nlm query notebook <NOTEBOOK_ID> "<q>" --json [--source-ids a,b] [--timeout 180] [--conversation-id <id>] [--new-conversation]` | `--source-ids` nhận **comma-separated**; `--timeout` **float**, default 120 |
| Deep research | `nlm research start "<query>" --mode deep --notebook-id <NB> --source web [--force]` → `nlm research status <NB> [--task-id <id>] --max-wait 0` (1 lần) → `nlm research import <NB> [TASK_ID] [--indices a,b] [--cited-only]` | `research start`: mode default `fast` (~30s, ~10 nguồn); **`deep` chỉ hỗ trợ `--source web`**; `--auto-import/--wait-and-import` có tồn tại |
| Artifact — slide | `nlm download slide-deck <NOTEBOOK_ID> --format pptx --output "<ABS>.pptx" [--id <artifact_id>]` | format default **`pdf`**, phải ép `--format pptx` |
| Artifact — tất cả | `nlm download all [notebook_id] --output-dir "<dir>" --slide-format pptx --interactive-format json --skip-existing --json` | có thêm `--types video,slide_deck,mind_map,report`, `--all-notebooks/-a` |
| Artifact — quiz/flashcards | `nlm download quiz <NB> --format json --output "<ABS>.json"` / `nlm download flashcards <NB> --format json --output "<ABS>.json"` | format: `json\|markdown\|html`; các lệnh khác: `audio, video, report, mind-map, data-table, infographic, file` |
| Trạng thái artifact | `nlm studio status <NOTEBOOK_ID> --json --mcp-compatible [--artifact-id <id>] [--limit N]` | `--mcp-compatible` dùng envelope + `artifact_id` |
| Quiz 50 câu | `nlm quiz create <NB> --count 50 --difficulty 3 --confirm --json` | `--count` default **2**; `--difficulty` là **INT 1–5** (không phải easy/hard) |
| Flashcard | `nlm flashcards create <NB> --difficulty hard [--focus "<prompt>"] [--source-ids a,b] --confirm --json` | `--difficulty` ở đây là **CHUỖI** `easy/medium/hard` — **KHÁC kiểu** với `quiz create`; `--focus` dùng để yêu cầu 5 câu tự luận |
| Phiên chat cũ (orphan) | `nlm chats list <NOTEBOOK> --json --limit 20` | còn có `chats get`, `chats export` (markdown/json), `chats to-note` |
| Xuất sang Google Docs/Sheets | `nlm export artifact\|to-docs\|to-sheets` | dùng khi cần link cloud |

### 4.3 Kết luận §4 (rủi ro chức năng thật)
1. `nlm artifact ...` **không tồn tại** → hợp đồng gốc (đặc tả cũ) sai; §7 đã đính chính **đúng** cho mục này.
2. `nlm source remove` **không tồn tại** → §7 **đúng**; code hiện tại `nlm_task_handler.py:122` **sai** ⇒ cascade bước 1 **không bao giờ** thành công theo ý định.
3. `nlm query` **tồn tại** → §7:282 khẳng định ngược lại là **SAI** (đã đo, exit 0). Dù vậy khuyến nghị dùng `nlm notebook query` như §7:289 (đúng, ổn định hơn).
4. `nlm mcp` **không tồn tại** → `.agents/mcp_config.json` **hỏng** (không liên quan hợp đồng Phase 2–4 nhưng ảnh hưởng tích hợp AntiGravity/MCP).
5. **Bẫy `--difficulty` khác kiểu giữa `quiz create` (int) và `flashcards create` (string)** — teammate `agent` rất dễ truyền sai; đây là lỗi sẽ chỉ lộ ra ở runtime, **không** lộ qua `compileall`.
6. Mọi lệnh cần **đường dẫn tuyệt đối** cho `--output`/`--output-dir` (bằng chứng: file rác `--output` ở root repo — xem §3.3).

---

## 5. `[NEXT ACTION]` — Việc cần làm theo thứ tự ưu tiên

| # | Ưu tiên | Việc | Chủ trì | Điều kiện hoàn thành |
|---|---|---|---|---|
| N1 | 🔴 P0 — blocker dữ liệu | **Sửa cú pháp `nlm` trong `local_agent/nlm_task_handler.py`**: `source add <nb_id> --file <abs> --wait --json` (A7), `source delete <id> --confirm` (A8) | `agent` | Chạy tay 1 lệnh `nlm source add` thật, thu được source_id; note lại vào báo cáo |
| N2 | 🔴 P0 — an toàn | **`delete.js`: thêm `step3_local_softdelete`** queue `soft_delete_local` kèm `local_path`, và set `local_path` + `is_output` + `source_kind` + `review_status` khi tạo file doc (W8/W12) | `api` | `DELETE /api/files/:id` trả `steps` có **đủ 4 key** `step1…step4` |
| N3 | 🔴 P0 — an toàn | **`cron/hard_delete.js`: gửi kèm `local_path` + `filename`** trong task `hard_delete` (W13) | `api` | Task trong `drive_task_queue` có 2 field đó |
| N4 | 🔴 P0 — vòng lặp | **Bịt NO-LOOP lớp 2 trước khi tạo `file_watcher.py`**: `upload_complete.js` không queue `source_add` khi `is_output === true`; `upload_init.js` tính `is_output` theo **prefix `folder_path`** (W14/W15) | `api` | Test: upload file có `folder_path=04_Ket_Qua_Xuat_Ban` ⇒ `nlm_task_queue` **không** có task mới |
| N5 | 🔴 P0 — an toàn | **Nâng cấp `AGENT_SECRET`**: xoá default yếu khỏi `config_loader.py:11`, sinh secret mạnh ≥32 byte, set qua `wrangler secret put`, `git rm --cached config.json` (§3.4) | `release` (+ `agent` bỏ default) | `/api/tasks/:queue` trả 403 với secret cũ |
| N6 | 🟠 P1 — chặn tính năng | **`index.js:22` thêm `PATCH`** vào `allowMethods` (+ `X-Agent-Secret` vào allow-headers) — nếu không, mọi PATCH từ browser sẽ fail (W16/W18) | `api` | Preflight `PATCH /api/chat/sessions/:id` trả 204 với `Allow-Methods` có PATCH |
| N7 | 🟠 P1 | Tạo `lib/folders.js` + `lib/citations.js` + `requireAuthOrAgent` (W1/W2/W7); refactor các hằng số trùng về 1 nguồn | `api` | `grep FOLDER_MAP` chỉ còn **1** định nghĩa trong workers + 1 trong pages + 1 trong python |
| N8 | 🟠 P1 | Bổ sung `release`/`lease` cho task `processing` (**reclaim sau N phút**) để tuân §4 "không treo `processing`" (§3.5) | `api` + `agent` | Task `processing` quá 15 phút được đưa lại `pending` |
| N9 | 🟡 P2 | Triển khai Phase 3 chat (W6) + Phase 4 (W9/W10/W11) theo hợp đồng §2/§3 | `api` | Mọi route §3.1–§3.7 mount trong `index.js` + `node --check` xanh |
| N10 | 🟡 P2 | `file_watcher.py` + `api_client.py` + các handler mới (A2–A5, A11) — **chỉ sau N4** | `agent` | Watchdog bỏ qua output/archive/temp/<1000B/duplicate |
| N11 | 🟡 P2 | Sửa badge NLM báo sai (F7): thêm endpoint heartbeat thật (agent `last_seen`) hoặc đổi nhãn cho trung thực | `api` + `web` | Badge hiển thị "Agent offline" khi agent tắt (test thật) |
| N12 | 🟢 P3 | Giảm rủi ro XSS token: cân nhắc `sessionStorage` + gọi `authApi.me()` khi khôi phục phiên, xử lý 401 ⇒ `signOut()` (F8) | `web` | F5 sau khi token hết hạn ⇒ tự quay về màn hình đăng nhập |
| N13 | 🟢 P3 | `.agents/mcp_config.json`: đổi sang lệnh thật (`nlm setup` / cập nhật `tests/test_mcp_config.py` để **thực sự kiểm tra subcommand tồn tại**) (S4) | lead + `agent` | Test mới fail nếu `nlm <args>` không tồn tại |
| N14 | 🟢 P3 | Làm rõ `scripts/migrate_sqlite_to_firestore.py` (S2): **không có** `data/files.db` để migrate — xác nhận phạm vi trước khi viết | lead → `agent` | Lead quyết: viết script hay bỏ khỏi phạm vi |
| N15 | 🟢 P3 | `.gitignore` + dọn file rác (`--output`, `temp_test_slide.pptx`, `database.db`, `.wrangler/`) (§3.4) | `release` | `git status` không còn untracked rác |

---

## 6. PHẢN BIỆN 3 VÒNG (brainstorming)

> Không có skill `brainstorming` trong `.superpowers/`/workspace ⇒ tự phản biện 3 vòng theo yêu cầu task.

### Vòng 1 — Liệt kê giả định của hợp đồng & của lead
| Giả định | Nguồn |
|---|---|
| G-A: `nlm artifact download`, `nlm source remove`, `nlm query` **không tồn tại** | lead, §7:282 |
| G-B: "Firestore REST không hỗ trợ WHERE tốt" ⇒ lọc phía Worker là chấp nhận được | `list.js:16-19` |
| G-C: cascade delete hiện tại đã "đủ 4 bước" | `delete.js:1` (header comment) + §3.8 |
| G-D: `is_output` guard đã đủ để chống loop | `upload_init.js:114` |
| G-E: pytest 80 passed ⇒ hệ thống không có lỗi nghiêm trọng | kết quả test |
| G-F: frontend "đã live, CORS + health đã fix" | lead |

### Vòng 2 — Tìm phản ví dụ (đã đo, không suy đoán)
| Giả định | Phản ví dụ | Kết luận |
|---|---|---|
| G-A | `nlm query --help` → **exit 0**, có subcommand `notebook`; `nlm notebook query --help` cũng exit 0 | **G-A SAI một phần** — `nlm query` **tồn tại**; §7:282 cần đính chính. Hai mục còn lại (`artifact`, `source remove`) **đúng** |
| G-B | `upload_complete.js:16` `firestoreList(..., 200)` rồi `docs.some(...)` — nếu user có **>200 file**, duplicate **không bị phát hiện** ⇒ cùng `sha256` được nạp lại vào NLM (nạp trùng, tốn quota Plus). `routes/sync/index.js:29` cũng `Math.min(limit,50)` | **RỦI RO THẬT**: trần 200 doc là giới hạn **im lặng**, không cảnh báo. Cần `POST /api/files/check-hash` (W4) hoặc Firestore `runQuery` |
| G-C | `delete.js:118` là **comment**; grep `soft_delete_local`/`step3_local_softdelete` trong `cloudflare/` → **0 kết quả** | **G-C SAI** — chỉ 3 bước thực thi, thiếu bước local |
| G-D | `upload_complete.js:84-98` **không** đọc `is_output`; `upload_init.js:92` suy `is_output` từ `document_type` do client gửi | **G-D SAI** — guard chỉ tồn tại trên giấy, và có thể bị client qua mặt |
| G-E | Suite xanh nhưng: `tests/test_mcp_config.py:17` chỉ so **chuỗi JSON**, không chạy `nlm`; **không** có test nào cho `delete.js`/`cron`/`firestore_poller` (test suite 12 file đều thuộc `src/*` monolith cũ) | **G-E SAI** — 80 passed **không** chứng minh gì cho tầng Cloud; coverage Cloud ≈ **0%** |
| G-F | `index.js:22` thiếu `PATCH`; `index.js:20-24` `origin:'*'` mâu thuẫn whitelist `cors.js:4-11`; `app.js:101-117` badge giả | **G-F SAI một phần** — "đã fix" không đúng ở mức code: còn 2 vấn đề CORS + 1 badge sai sự thật |

### Vòng 3 — Kết luận & xếp hạng rủi ro (sau phản biện)
1. **Rủi ro chặn tính năng (P0)**: `nlm source add`/`source remove` sai cú pháp ⇒ toàn bộ đồng bộ NotebookLM **không hoạt động**. Đây là **nguyên nhân gốc** dễ bị bỏ sót vì `compileall`/`pytest` đều xanh (không test nào gọi CLI thật).
2. **Rủi ro mất/hỏng dữ liệu (P0)**: thiếu bước 3 local soft delete + cron không có `local_path` ⇒ file local **không bao giờ** bị xoá ⇒ "xoá 90 ngày" chỉ đúng trên cloud, sai trên máy; đồng thời không có `soft_delete_local` handler ⇒ task sẽ bị `failed` (`drive_sync.py:135`).
3. **Rủi ro vòng lặp (P0, tương lai gần)**: cả 3 lớp NO-LOOP đều chưa đạt (2 lớp chưa code, 1 lớp code sai điều kiện). Khi Phase 4 xong, loop sẽ xuất hiện **âm thầm** (tốn quota, rác Firestore) chứ không báo lỗi.
4. **Rủi ro bảo mật (P0)**: default secret yếu trong file được track (`config_loader.py:11`) + `config.json` còn tracked + không phân quyền per-user cho agent ⇒ **chặn deploy** (§6.6).
5. **Rủi ro chất lượng kiểm thử (P1)**: `pytest` xanh là **bằng chứng yếu** cho kiến trúc mới — cần test riêng cho workers (tối thiểu: no-loop guard, 4 key cascade, `is_output`).

### Giới hạn của audit này (trung thực)
- **Chưa có bằng chứng end-to-end**: KHÔNG chạy `wrangler deploy --dry-run` (thuộc T8/`release`) và không gọi mạng thật tới Worker/Firestore ⇒ kết luận runtime dựa trên **đọc code + `--help` thật**. Mọi bằng chứng nlm đến từ **một máy Windows/PowerShell**, `nlm` 0.11.6.
- **Phạm vi hẹp có chủ ý**: không đọc hết 12 file test cũ trong `tests/` ⇒ khẳng định "coverage Cloud ≈ 0%" căn cứ **tên file test** (không file nào nhắc `cloudflare`/`local_agent`/`workers`) — cần xác minh lại ở T8. Snapshot có **6 file dirty** khi audit; teammate đã bắt đầu ghi file mới (`lib/folders.js`, `routes/chat/`…) ⇒ một số `file:line` trong báo cáo này mô tả **baseline trước khi sửa**, dùng để đối chiếu delta.

**Tóm tắt 1 dòng cho lead:** Hệ thống hiện **chạy được** ở mức skeleton (80 test xanh, 17/17 JS hợp lệ, 3/4 bước cascade đúng thứ tự) nhưng **thiếu toàn bộ Phase 3–4** (chat/citation/review/research/artifact/exam/migration/file_watcher) và có **5 lỗi P0 chặn deploy**: (1) sai cú pháp `nlm`, (2) thiếu bước soft-delete local, (3) cron không gửi `local_path`, (4) cả 3 lớp NO-LOOP chưa đạt, (5) secret yếu bị commit + CORS `PATCH` bị chặn.
