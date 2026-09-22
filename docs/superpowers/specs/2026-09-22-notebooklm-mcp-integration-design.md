# Thiết Kế Tích Hợp NotebookLM MCP & AI Study Hub Cho ThsAutoOrganizer

> **Tài liệu đặc tả kiến trúc & thiết kế chi tiết (Design Spec Doc)**  
> **Ngày khởi tạo:** 22/09/2026  
> **Trạng thái:** Chờ phê duyệt (Pending Approval)  
> **Tác giả:** Antigravity AI Assistant & Kỹ sư trưởng hệ thống  

---

## 1. Bối Cảnh & Mục Tiêu Hệ Thống

### 1.1. Hiện trạng
Dự án **ThsAutoOrganizer** đã hoàn thiện các tính năng nền tảng:
- Thu thập, lọc trùng SHA-256 và phân loại tài liệu đa chuyên ngành Thạc sĩ (14 chuyên ngành, cấu trúc 4 thư mục chuẩn: `01_Giao_Trinh`, `02_Slide`, `03_Tai_Lieu_Tham_Khao`, `04_On_Thi`).
- Lưu trữ cục bộ kết hợp đồng bộ 2 chiều lên Google Drive cá nhân.
- Giao diện Web Dashboard chuẩn phong cách học thuật tối giản (Obsidian Minimalist Academic).

Tuy nhiên, toàn bộ kho tài liệu sau khi được phân loại hiện đang ở trạng thái **tĩnh** (static storage). Để phục vụ nghiên cứu, làm bài tập lớn, chuẩn bị đề cương ôn thi hay làm tiểu luận, người dùng vẫn phải mở từng tài liệu, đọc thủ công hoặc tự copy từng phần tài liệu sang các công cụ AI khác.

### 1.2. Mục tiêu tích hợp (Workflow 4 Bước Toàn Diện)
Tích hợp **Google NotebookLM Plus** thông qua giao thức **MCP (Model Context Protocol)** với kiến trúc Native Python Hub để hoàn thiện vòng lặp khép kín 4 bước:

1. **Bước 1: Thu thập & Phân loại qua Web ThsAutoOrganizer**  
   - Người dùng tải tài liệu (slide, giáo trình, đề cương, bài tập) từ điện thoại/máy tính lên Web.
   - ThsAutoOrganizer băm mã SHA-256, lọc trùng, nhận diện đúng môn học và lưu vào thư mục chuẩn + sync Google Drive.
2. **Bước 2: Pipeline Ngầm Nạp Nguồn vào NotebookLM Plus (Auto-Ingestion)**  
   - Ngay sau khi file được phân loại thành công, background worker ngầm của ThsAutoOrganizer tự động gọi lệnh đẩy tài liệu vào đúng Notebook tương ứng trên NotebookLM Plus mà không làm chậm trải nghiệm của người dùng.
   - Tự động map môn học với Notebook (Auto-Match & Cache).
3. **Bước 3: Truy vấn & Báo cáo Siêu Tốc từ AntiGravity IDE**  
   - Tích hợp MCP Server `notebooklm-mcp-cli` vào AntiGravity IDE.
   - Trong quá trình lập trình hoặc viết bài luận, người dùng có thể chat trực tiếp với Agent trong IDE:  
     `"@notebooklm Hãy trích xuất 3 luận điểm chính về NQ 27 từ Notebook Triết học kèm số trang trích dẫn."`
   - Agent truy vấn qua MCP, nhận về câu trả lời có tính căn cứ tuyệt đối kèm **Citations (nguồn tài liệu, số trang/đoạn)**.
4. **Bước 4: Xuất Bản Output Ngược Lại Web ThsAutoOrganizer (AI Study Hub)**  
   - Dữ liệu tóm tắt, đề cương ôn thi, câu hỏi trắc nghiệm (Quiz), phân tích bài giảng được lưu trữ vào CSDL SQLite (`ai_insights`).
   - Hiển thị trực quan trên Tab mới **"🧠 AI Study Hub"** trên Web Dashboard, hỗ trợ tương tác 2 chiều (vừa nhận dữ liệu từ Agent, vừa cho phép hỏi đáp nhanh ngay trên Web).

---

## 2. Kiến Trúc Tổng Thể (Full-Stack Architecture)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             NGƯỜI DÙNG THẠC SĨ                              │
└───────────────────────┬─────────────────────────────▲───────────────────────┘
                        │ (1. Tải tài liệu)           │ (4. Học tập & Xem Quiz)
                        ▼                             │
┌─────────────────────────────────────────────────────┴───────────────────────┐
│                       THSAUTOORGANIZER WEB DASHBOARD                        │
│  - Web UI (Flask + Vanilla CSS/JS phong cách Obsidian Minimalist Academic)  │
│  - Tab mới: [🧠 AI Study Hub] (Xem Quiz, Tóm tắt, Citations, Q&A)          │
└───────────────────────┬─────────────────────────────▲───────────────────────┘
                        │                             │
                        ▼ (Lưu file & Trigger)        │ (Đọc & Ghi Insights)
┌─────────────────────────────────────────────────────┴───────────────────────┐
│                    THSAUTOORGANIZER BACKEND & DATABASE                      │
│  - `processor.py`: Phân loại & băm SHA-256                                  │
│  - `database.py`: SQLite `organizer.db`                                     │
│      ├── `courses` (bổ sung trường `notebooklm_id`)                         │
│      ├── `ai_insights` (lưu Quiz, Summary, Outline, Citations)              │
│      └── `notebooklm_sync_log` (lịch sử & trạng thái nạp nguồn)             │
│  - `src/notebooklm_sync.py`: Background Worker gọi CLI `nlm`               │
└───────────────────────┬─────────────────────────────▲───────────────────────┘
                        │                             │
                        ▼ (2. nlm source add)         │ (POST /api/ai/insights)
┌───────────────────────────────────────┐             │
│       GOOGLE NOTEBOOKLM PLUS          │             │
│  - Sổ tay theo từng môn học           │             │
│  - Gemini 1.5 Pro RAG Engine          │             │
│  - Grounded Citations                 │             │
└───────────────────▲───────────────────┘             │
                    │                                 │
                    │ (3. Query via MCP)              │
┌───────────────────┴─────────────────────────────────┴───────────────────────┐
│                        ANTIGRAVITY AGENT / IDE                              │
│  - MCP Server: `nlm mcp` (khai báo trong `mcp_config.json`)                 │
│  - Công cụ MCP: `nlm_query`, `nlm_list_notebooks`, `nlm_add_source`        │
│  - Hỗ trợ câu lệnh Chat prompt chuyên sâu & xuất bản trực tiếp về Web      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Thiết Kế Chi Tiết Từng Thành Phần

### 3.1. Phân hệ MCP Server cho AntiGravity IDE
* **Engine lựa chọn:** `notebooklm-mcp-cli` (mã nguồn mở Python, repo chuẩn `jacob-bd/gemini-notebook-mcp-cli`).
* **Cơ chế xác thực (Authentication):**
  - Chạy lệnh CLI xác thực ban đầu: `nlm login`
  - Đăng nhập tài khoản Google (có gói NotebookLM Plus). Session token được lưu trữ an toàn trong máy người dùng (`%USERPROFILE%\.notebooklm` hoặc thư mục cấu hình chuẩn).
* **Cấu hình MCP AntiGravity:**
  - File cấu hình: `~/.gemini/config/mcp_config.json` (hoặc workspace `.agents/mcp_config.json`):
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
* **Các Tool Call Agent có thể sử dụng:**
  - `nlm_list_notebooks`: Lấy danh sách sổ tay môn học trên tài khoản.
  - `nlm_query`: Gửi câu hỏi kèm `notebook_id`, nhận câu trả lời có tính căn cứ cao kèm mảng `citations` (tiêu đề nguồn, số trang, đoạn văn bản gốc).
  - `nlm_add_source`: Thêm tệp/URL vào sổ tay từ IDE.

---

### 3.2. CSDL SQLite & Schema Migrations (`src/database.py`)

#### 1. Cập nhật Bảng `courses`
Thêm cột để lưu trữ ID sổ tay NotebookLM tương ứng với môn học:
```sql
ALTER TABLE courses ADD COLUMN notebooklm_id TEXT;
```

#### 2. Tạo Bảng `ai_insights` (Lưu trữ kết quả từ NotebookLM)
```sql
CREATE TABLE IF NOT EXISTS ai_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    insight_type TEXT NOT NULL CHECK(insight_type IN ('quiz', 'summary', 'outline', 'qa')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,         -- Nội dung Markdown hoặc JSON cấu trúc câu hỏi
    citations TEXT,                -- JSON chuỗi trích dẫn (source title, page, quote)
    created_by TEXT DEFAULT 'agent', -- 'agent' hoặc 'web_user'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_insights_course ON ai_insights(course_id);
CREATE INDEX IF NOT EXISTS idx_ai_insights_type ON ai_insights(insight_type);
```

#### 3. Tạo Bảng `notebooklm_sync_log` (Theo dõi tiến độ nạp nguồn)
```sql
CREATE TABLE IF NOT EXISTS notebooklm_sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER,
    course_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    notebooklm_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('pending', 'syncing', 'synced', 'failed', 'skipped')),
    error_message TEXT,
    synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_nlm_sync_status ON notebooklm_sync_log(status);
```

---

### 3.3. Dịch Vụ Đồng Bộ Ngầm (`src/notebooklm_sync.py`)

Module `NotebookLMSyncManager` đảm nhiệm toàn bộ tương tác giữa backend ThsAutoOrganizer và CLI/API `nlm`:
1. **Quản lý Ánh xạ Notebook (`ensure_notebook_for_course`):**
   - Khi cần nạp file cho môn học (ví dụ: *Triết học*):
     - Kiểm tra cột `notebooklm_id` trong bảng `courses`.
     - Nếu chưa có: Gọi lệnh `nlm notebook list` để đối soát xem trên NotebookLM đã có sổ tay trùng tên chưa.
     - Nếu đã có: Lưu ID vào CSDL. Nếu chưa: Gọi `nlm notebook create "Triết học"` để tạo mới, sau đó lưu ID vào CSDL.
2. **Nạp Nguồn Không Gây Chặn (Non-blocking Background Ingestion):**
   - Sử dụng `concurrent.futures.ThreadPoolExecutor(max_workers=2)`.
   - Khi một file được xử lý xong ở `processor.py` hoặc upload xong:
     - Kiểm tra định dạng hỗ trợ của NotebookLM (PDF, DOCX, TXT, MD, MP3/Audio).
     - Ghi nhận trạng thái `pending` vào `notebooklm_sync_log`.
     - Đẩy task vào ThreadPool thực thi `nlm source add <notebook_id> <local_file_path>`.
     - Thành công: Cập nhật `synced` kèm timestamp. Thất bại: Ghi `failed` và nội dung lỗi.
3. **API Truy Vấn Trực Tiếp (`query_notebook`):**
   - Gọi `nlm query <notebook_id> "<prompt>"` và trích xuất câu trả lời kèm Citations có cấu trúc để phục vụ Web Dashboard.

---

### 3.4. API Endpoints Mới (`src/web_server.py`)

| Phương thức | Đường dẫn | Chức năng | Phục vụ cho |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/ai/insights` | Lấy danh sách insights (hỗ trợ filter `course_id`, `type`) | Web UI (AI Study Hub) |
| `POST` | `/api/ai/insights` | Thêm insight mới (tiêu đề, nội dung, citations, type) | AntiGravity Agent & Web |
| `DELETE` | `/api/ai/insights/<id>` | Xóa một insight | Web UI |
| `POST` | `/api/ai/query` | Gửi câu hỏi nhanh trực tiếp đến NotebookLM của môn học | Web UI |
| `GET` | `/api/notebooklm/status` | Kiểm tra tình trạng kết nối CLI `nlm`, phiên login, danh sách sổ tay | Web UI Settings & Status |
| `POST` | `/api/notebooklm/sync-pending` | Bấm nút cưỡng bức nạp lại tất cả các file bị lỗi hoặc chờ sync | Web UI |

---

### 3.5. Giao Diện Người Dùng: Tab "🧠 AI Study Hub"

Thiết kế giao diện tuân thủ phong cách **Obsidian Minimalist Academic**:
1. **Thanh Header & Bộ lọc Thông minh:**
   - Dropdown chọn Môn học (liên kết với chuyên ngành đang học).
   - Filter Tabs: `Tất cả` | `Đề cương ôn tập` | `Trắc nghiệm Quiz` | `Tóm tắt bài giảng` | `Hỏi đáp nhanh`.
   - Badge hiển thị trạng thái kết nối NotebookLM Plus (Xanh lá: Đã kết nối & đồng bộ | Vàng: Có tệp đang chờ nạp | Xám: Cần login).
2. **Khu vực Trắc nghiệm Tương tác (Interactive Quiz Player):**
   - Khi chọn xem một bộ Quiz, giao diện render câu hỏi trắc nghiệm sinh động, cho phép bấm chọn đáp án A/B/C/D, kiểm tra đúng/sai tức thì và hiển thị giải thích chi tiết trích dẫn từ bài giảng.
3. **Thẻ Bài Học & Khối Trích Dẫn (Citations Drawer):**
   - Thẻ Markdown render công thức toán học/tiêu đề rõ ràng.
   - Nút bấm `[📎 Trích dẫn nguồn (Nguồn & Số trang)]`: Khi bấm mở một bảng drawer trích dẫn chính xác trang tài liệu nào trong NotebookLM đã cung cấp dữ liệu này.
4. **Hộp Hỏi Đáp Siêu Tốc (Quick Research Box):**
   - Ô nhập câu hỏi nhanh ngay trên Web để sinh viên tra cứu khi đang học bài trên máy tính hoặc điện thoại mà không cần mở terminal hay IDE.

---

## 4. Xử Lý Lỗi & Khả Năng Chịu Lỗi (Error Handling & Resilience)

1. **Chưa Đăng Nhập hoặc Hết Hạn Cookie (`nlm login` required):**
   - Bắt mã lỗi authentication từ CLI/Library.
   - Không làm sập tiến trình web; ghi log cảnh báo và hiển thị trạng thái thân thiện trên Web UI: *"Cần đăng nhập NotebookLM: Mở terminal chạy `nlm login`"*.
2. **Tệp Không Thuộc Định Dạng NotebookLM Hỗ Trợ:**
   - Hệ thống tự động bỏ qua (status `skipped`) đối với các file mã nguồn (.py, .zip, .exe), chỉ nạp các file tài liệu chuẩn (.pdf, .docx, .txt, .md, .pptx).
3. **Mạng Chậm hoặc Google Rate Limit:**
   - ThreadPool chạy tách biệt hoàn toàn với Flask Web Server, không gây đơ hoặc gián đoạn luồng upload tài liệu của người dùng.
   - Khi gặp timeout, sync log lưu trạng thái `failed` và tự động cho phép bấm nút "Thử lại tất cả" trên Web.

---

## 5. Kế Hoạch Kiểm Thử (Verification Plan)

### 5.1. Kiểm thử Tự động (Automated Tests)
* **`tests/test_database.py`:**
  - Kiểm tra migration bảng `courses` thêm cột `notebooklm_id`.
  - Kiểm tra thêm/sửa/xóa bảng `ai_insights` và `notebooklm_sync_log`.
* **`tests/test_notebooklm_sync.py`:**
  - Mock lệnh CLI `nlm` để kiểm tra các hàm: `ensure_notebook_for_course`, `sync_file_to_notebook`, `query_notebook`.
  - Kiểm tra xử lý ngoại lệ khi chưa đăng nhập và khi CLI gặp lỗi timeout.
* **`tests/test_web_server.py`:**
  - Test các API endpoints: `GET /api/ai/insights`, `POST /api/ai/insights`, `POST /api/ai/query`, `GET /api/notebooklm/status`.

### 5.2. Kiểm thử Tích hợp Thủ công (Manual Verification)
1. Cài đặt package `notebooklm-mcp-cli` và cấu hình `mcp_config.json`.
2. Chạy `nlm login` để đăng nhập tài khoản Google thực tế.
3. Tải thử 1 file PDF bài giảng môn học trên Web ThsAutoOrganizer -> Xác nhận file được tự động nạp lên NotebookLM Plus.
4. Trong khung chat AntiGravity, gõ prompt truy vấn NotebookLM -> Xác nhận câu trả lời có trích dẫn số trang chính xác.
5. Đẩy kết quả về Web và mở Tab "AI Study Hub" trên giao diện Web -> Xác nhận hiển thị đầy đủ và tương tác mượt mà.
