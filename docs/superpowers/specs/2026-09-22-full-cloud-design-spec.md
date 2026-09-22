# Full Cloud Design Spec — ThsAutoOrganizer v2.0

> **Tài liệu đặc tả kiến trúc kỹ thuật (Design Spec Doc)**
> **Ngày khởi tạo:** 22/09/2026
> **Trạng thái:** Đã phê duyệt (Approved)
> **Tác giả:** Antigravity AI Assistant & Kỹ sư trưởng hệ thống

---

## 1. Tổng Quan Kiến Trúc Full Cloud

### 1.1. Mục tiêu chuyển đổi

Chuyển đổi ThsAutoOrganizer từ kiến trúc **Python local monolith** (single `web_server.py` 6,115 dòng)
sang kiến trúc **Full Cloud phân tán** với ba tầng tách biệt hoàn toàn:

| Tầng | Công nghệ | Trách nhiệm |
|------|-----------|-------------|
| **Frontend** | Cloudflare Pages (Vanilla HTML/CSS/JS) | Giao diện SPA, Google Sign-In, upload UI |
| **API** | Cloudflare Workers (Hono v4, ES Modules) | REST API, Auth, Firestore CRUD, Task Queue |
| **Local Agent** | Python 3.13 (Windows) | Drive sync, NLM CLI, File watcher, Cascade delete |

### 1.2. Nguyên tắc thiết kế SOLID

- **MAX 200–250 dòng/file** — bắt buộc, không ngoại lệ
- **1 file = 1 route hoặc 1 service** (Single Responsibility)
- **Xóa `src/web_server.py`** hoàn toàn sau khi migrate
- **Không commit secrets** — tất cả dùng `wrangler secret put`

---

## 2. Kiến Trúc Chi Tiết

### 2.1. Sơ đồ luồng dữ liệu

```
┌──────────────────────────────────────────────────────────────────┐
│                    NGƯỜI DÙNG THẠC SĨ                            │
│              (Máy tính / iPad / Điện thoại)                      │
└───────┬─────────────────────────────────────▲────────────────────┘
        │ HTTPS                               │ HTTPS
        ▼                                     │
┌───────────────────────┐          ┌──────────────────────────────┐
│  CLOUDFLARE PAGES     │          │  CLOUDFLARE WORKERS           │
│  ths-organizer.       │◄────────►│  ths-organizer-api.           │
│  pages.dev            │  fetch() │  workers.dev                  │
│                       │          │                               │
│  - index.html         │          │  /api/auth/login              │
│  - css/main.css       │          │  /api/files/upload/init       │
│  - js/app.js          │          │  /api/files/upload/complete   │
│  - js/pages/          │          │  /api/files/ (list)           │
│  - js/components/     │          │  DELETE /api/files/:id        │
└───────────────────────┘          │  /api/ai/insights (CRUD)      │
                                   │  /api/courses (CRUD)          │
        ┌──────────────────────────│  /api/tasks/:queue (poll)     │
        │ Direct upload            └──────────────┬───────────────┘
        │ (bypass Worker)                         │ Firestore REST
        ▼                                         ▼
┌───────────────────┐              ┌──────────────────────────────┐
│  GOOGLE DRIVE     │              │  FIREBASE FIRESTORE           │
│  (File storage)   │              │                               │
│  - Per-user Drive │              │  users/{uid}/files            │
│  - _Archive_90d/  │              │  users/{uid}/courses          │
└───────────────────┘              │  users/{uid}/ai_insights      │
                                   │  nlm_task_queue               │
        ▲                          │  drive_task_queue             │
        │                          │  archived_files               │
        │ Drive API                │  file_deletion_logs           │
        │ nlm CLI                  └──────────────────────────────┘
        │                                         │
┌───────┴──────────────────────────────┐          │ HTTP poll
│  PYTHON LOCAL AGENT (Windows)        │◄─────────┘
│  local_agent/main.py                 │
│                                      │
│  - firestore_poller.py (10s poll)    │
│  - drive_sync.py (upload/archive)    │
│  - nlm_task_handler.py (nlm CLI)     │
│  - cascade_delete.py (Recycle Bin)   │
│  - file_watcher.py (Watchdog)        │
└──────────────────────────────────────┘
```

---

## 3. Hybrid Upload Architecture (Giải quyết giới hạn 100MB Workers)

### 3.1. Vấn đề

Cloudflare Workers giới hạn **100MB per request** — không đủ cho file PDF, PPTX học thuật
có thể lên tới 200MB.

### 3.2. Giải pháp: 3-Phase Upload

**Phase 1: Init Upload Session** (Client → Worker, ~1KB)
```
POST /api/files/upload/init
Authorization: Bearer <google_id_token>
Content-Type: application/json

{
  "filename": "Slide_Triet_Hoc_Chuong1.pptx",
  "size_bytes": 52428800,
  "subject": "Triết học",
  "document_type": "slide",
  "course_id": "uuid-course-123"
}
```

Worker thực hiện:
1. Verify Google ID Token → lấy `{uid, email}`
2. Tạo Google Drive **Resumable Upload Session** URL bằng user's access token
3. Tạo Firestore document với `status: "pending_upload"`
4. Trả về `upload_url` (Google Drive), `doc_id`

```json
{
  "doc_id": "uuid-doc-456",
  "upload_url": "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&upload_id=xxx",
  "expires_at": "2026-09-22T19:31:45Z"
}
```

**Phase 2: Direct Upload to Google Drive** (Client → Google Drive, bypasses Worker)
```
PUT <upload_url>
Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation
Content-Length: 52428800

<binary file data>
```
→ File bytes KHÔNG đi qua Cloudflare Worker → Không giới hạn kích thước

SHA-256 được tính phía client bằng **Web Crypto API**:
```javascript
const buffer = await file.arrayBuffer();
const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
const sha256 = Array.from(new Uint8Array(hashBuffer))
  .map(b => b.toString(16).padStart(2, '0')).join('');
```

**Phase 3: Complete Upload** (Client → Worker, ~500B)
```
POST /api/files/upload/complete
Authorization: Bearer <google_id_token>
Content-Type: application/json

{
  "doc_id": "uuid-doc-456",
  "sha256": "a3f2b1...",
  "drive_file_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
}
```

Worker thực hiện:
1. Verify token
2. Kiểm tra SHA-256 duplicate trong Firestore
3. Nếu duplicate: `409 {status: "duplicate"}`, xóa Drive file vừa upload
4. Nếu OK: Update Firestore `status: "uploaded"`, lưu `sha256`, `drive_file_id`
5. Queue `nlm_task_queue` task `source_add`

### 3.3. So sánh phương án

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|------------|
| Direct Worker upload | Đơn giản, 1 request | Giới hạn 100MB |
| **Hybrid 3-Phase** ✅ | Không giới hạn kích thước, SHA-256 phía client | Phức tạp hơn một chút |
| Python agent upload | Không giới hạn | Cần agent chạy, không hỗ trợ mobile |

---

## 4. Safe Cascade Delete 4 Bước

Khi người dùng xóa file từ Web UI, Worker thực thi theo thứ tự ưu tiên:

```
Bước 1: Gỡ source NotebookLM (Non-blocking queue)
  → Worker ghi task {action: "source_remove", source_id} vào nlm_task_queue
  → Python local agent nhận task, chạy: nlm source remove <source_id>
  → Nếu timeout: ghi lỗi vào log, KHÔNG block các bước tiếp theo

Bước 2: Soft Delete trên Google Drive (Non-blocking queue)
  → Worker ghi task {action: "move_to_archive", drive_file_id} vào drive_task_queue
  → Python local agent dời file sang _Archive_Trash_90Days/ trên Drive

Bước 3: Soft Delete trong Firestore (Synchronous — ngay lập tức)
  → Worker cập nhật: users/{uid}/files/{id} → status: "archived"
  → Ghi thêm vào: archived_files/{id} (flat collection cho cron query)
  → Ghi: hard_delete_at = now + 90 ngày

Bước 4: Hard Delete sau 90 ngày (Cron Worker tự động)
  → Cron "0 2 * * *" chạy lúc 02:00 UTC hàng ngày
  → Query archived_files với hard_delete_at <= now()
  → Xóa Firestore doc + ghi audit log vào file_deletion_logs
  → Python agent nhận task hard_delete → xóa Drive file vĩnh viễn
```

---

## 5. Cấu Trúc Thư Mục Tài Liệu Chuẩn

```
H:\2026\Thac Sy\Mon_Hoc\
├── {Môn học}/
│   ├── 01_Giao_Trinh_Goc/        ← PDF giáo trình chính thức
│   ├── 02_Slide_Giang_Day/       ← PPTX/PDF slide bài giảng
│   ├── 03_Tai_Lieu_Tham_Khao/
│   │   ├── 01_Bai_Bao_Khoa_Hoc/ ← DOI-verified papers
│   │   └── 02_Unverified_Web/    ← Web content chưa kiểm chứng
│   ├── 04_Ket_Qua_Xuat_Ban/      ← is_output: true (NO-LOOP GUARD)
│   └── _Archive_Trash_90Days/    ← Soft deleted files
```

**Flag `is_output: true`**: Files trong `04_Ket_Qua_Xuat_Ban/` KHÔNG được re-classify
hay sync ngược lại. Đây là NO-LOOP GUARD để tránh vòng lặp xử lý.

---

## 6. Firebase Firestore Schema

### Collection `users/{uid}/files`
```typescript
{
  id: string;                    // UUID
  sha256: string;                // SHA-256 hash (client-computed)
  filename: string;
  subject: string;               // "Triết học", "Toán KHCL", ...
  document_type: string;         // "giao_trinh" | "slide" | "bai_bao" | "unverified_web" | "ket_qua"
  folder_path: string;           // "01_Giao_Trinh_Goc" | ...
  course_id: string;             // FK → users/{uid}/courses/{id}
  status: string;                // "pending_upload" | "uploaded" | "archived"
  is_output: boolean;            // true = NO-LOOP GUARD
  size_bytes: number;
  drive_file_id: string;
  notebooklm_source_id: string;  // ID source trên NotebookLM (dùng để remove)
  notebooklm_sync_status: string;// "pending" | "synced" | "skipped" | "failed"
  archived_at?: string;          // ISO timestamp nếu đã archived
  hard_delete_at?: string;       // ISO timestamp cho cron delete
  user_email: string;
  created_at: string;            // ISO timestamp
  updated_at: string;
}
```

### Collection `users/{uid}/courses`
```typescript
{
  id: string;
  name: string;                  // "Triết học Mác-Lênin"
  code: string;                  // "TH01"
  subject_key: string;           // Key để map với thư mục
  major: string;                 // "Hệ thống thông tin"
  notebooklm_id: string;         // Notebook ID trên NotebookLM Plus
  created_at: string;
  updated_at: string;
}
```

### Collection `users/{uid}/ai_insights`
```typescript
{
  id: string;
  course_id: string;
  insight_type: string;          // "quiz" | "summary" | "outline" | "qa"
  title: string;
  content: string;               // Markdown hoặc JSON (quiz)
  citations: string;             // JSON array [{source, page, quote}]
  created_by: string;            // "agent" | "web_user"
  created_at: string;
  updated_at: string;
}
```

### Collection `nlm_task_queue` (global, server-only)
```typescript
{
  action: "source_add" | "source_remove";
  notebook_id?: string;
  source_id?: string;
  file_path?: string;            // Local path cho source_add
  uid: string;
  file_id: string;               // FK → users/{uid}/files/{id}
  status: "pending" | "processing" | "done" | "failed";
  error?: string;
  created_at: string;
  processed_at?: string;
}
```

### Collection `drive_task_queue` (global, server-only)
```typescript
{
  action: "move_to_archive" | "hard_delete";
  drive_file_id: string;
  uid: string;
  file_id: string;
  status: "pending" | "done" | "failed";
  error?: string;
  created_at: string;
}
```

### Collection `file_deletion_logs` (global, server-only, permanent)
```typescript
{
  original_doc_path: string;
  filename: string;
  sha256: string;
  user_email: string;
  drive_file_id: string;
  archived_at: string;
  hard_deleted_at: string;
  backup_cloud_link: string;     // Drive link trước khi xóa
}
```

---

## 7. API Endpoints

| Method | Path | Auth | Chức năng |
|--------|------|------|-----------|
| POST | `/api/auth/login` | No | Google ID Token → user profile |
| GET | `/api/auth/me` | Yes | Current user info |
| POST | `/api/files/upload/init` | Yes | Tạo Drive upload session |
| POST | `/api/files/upload/complete` | Yes | Hoàn tất upload, lưu metadata |
| GET | `/api/files` | Yes | List files (filter: subject, status) |
| DELETE | `/api/files/:id` | Yes | Safe Cascade Delete 4 bước |
| GET | `/api/courses` | Yes | List courses |
| POST | `/api/courses` | Yes | Create course |
| PUT | `/api/courses/:id/notebooklm` | Yes | Link NotebookLM notebook |
| GET | `/api/ai/insights` | Yes | List insights (filter: course_id, type) |
| POST | `/api/ai/insights` | Yes | Create insight |
| DELETE | `/api/ai/insights/:id` | Yes | Delete insight |
| GET | `/api/tasks/:queue` | Agent | Lấy pending tasks cho Python agent |
| PATCH | `/api/tasks/:queue/:id` | Agent | Mark task done/failed |
| GET | `/health` | No | Health check |

---

## 8. Cấu Trúc File Workers (SOLID, <200 lines/file)

```
cloudflare/workers/src/
├── index.js                           # Entry point + cron handler (<60 lines)
├── lib/
│   ├── cors.js                        # CORS middleware (<50 lines)
│   ├── firebase.js                    # Firestore REST client (<150 lines)
│   └── auth.js                        # Google token verify + requireAuth (<80 lines)
├── routes/
│   ├── auth/
│   │   └── index.js                   # POST /login, GET /me (<100 lines)
│   ├── files/
│   │   ├── index.js                   # Mount upload + list (<40 lines)
│   │   ├── upload_init.js             # POST /upload/init (<150 lines)
│   │   ├── upload_complete.js         # POST /upload/complete (<150 lines)
│   │   ├── list.js                    # GET / (<120 lines)
│   │   └── delete.js                  # DELETE /:id (4-step) (<200 lines)
│   ├── courses/
│   │   └── index.js                   # CRUD courses (<150 lines)
│   ├── insights/
│   │   ├── index.js                   # Mount routes (<50 lines)
│   │   ├── list.js                    # GET / (<100 lines)
│   │   ├── create.js                  # POST / (<120 lines)
│   │   └── remove.js                  # DELETE /:id (<60 lines)
│   └── sync/
│       └── index.js                   # GET+PATCH /tasks/:queue/:id (<150 lines)
└── cron/
    └── hard_delete.js                 # 90-day hard delete job (<150 lines)
```

---

## 9. Cấu Trúc Python Local Agent (SOLID, <200 lines/file)

```
local_agent/
├── __init__.py
├── main.py                 # Entry point (<80 lines)
├── config_loader.py        # Load config.json (<80 lines)
├── firestore_poller.py     # Poll task queues mỗi 10s (<150 lines)
├── cascade_delete.py       # Windows Recycle Bin / archive (<150 lines)
├── nlm_task_handler.py     # nlm CLI source_add/remove (<150 lines)
├── drive_sync.py           # Drive upload/archive/delete (<200 lines)
└── file_watcher.py         # Watchdog local file changes (<150 lines)
```

---

## 10. Kế Hoạch Kiểm Thử

### Automated
- `pytest -v` — giữ nguyên toàn bộ test suite cũ (không regression)
- Bloat check: không file nào >250 lines

### Manual
1. Pages login → Dashboard hiển thị danh sách files
2. Upload 50MB PPTX → Phase 1/2/3 hoàn tất → Firestore có document
3. DELETE file → 4 bước cascade → Drive có task pending
4. `POST /api/ai/insights` → xuất hiện ngay trên AI Study Hub
5. `nlm login` → upload → nlm_task_queue có source_add task
6. Cron: `wrangler cron trigger` → file_deletion_logs có entry

---

## 11. Tích Hợp NotebookLM MCP

Giữ nguyên cấu hình `.agents/mcp_config.json`:
```json
{
  "mcpServers": {
    "notebooklm": {
      "command": "nlm",
      "args": ["mcp"]
    }
  }
}
```

Sau khi migrate Full Cloud, `POST /api/ai/insights` từ AntiGravity Chat sẽ ghi vào
Firestore thay vì SQLite — kết quả hiển thị ngay trên `https://ths-organizer.pages.dev`.
