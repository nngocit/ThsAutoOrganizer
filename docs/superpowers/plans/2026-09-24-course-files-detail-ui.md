# Kế Hoạch Triển Khai Giao Diện "Xem Chi Tiết Tệp Tin Môn Học" (Course File Explorer)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng giao diện Modal / Drawer trực quan "Xem chi tiết tệp tin môn học" trên Web UI (Cloudflare Pages), cho phép người dùng click vào bất kỳ môn học nào để xem toàn bộ danh sách tài liệu đã upload, trạng thái xử lý (Drive, NotebookLM, Local), dung lượng, loại tài liệu và link mở trực tiếp trên Google Drive.

**Architecture:** 
1. **Backend (Cloudflare Worker):** Nâng cấp route `GET /api/files` trong `cloudflare/workers/src/routes/files/list.js` để hỗ trợ truy vấn linh hoạt theo `course_id` kết hợp `subject`/`local_folder_name`, đảm bảo không bỏ sót bất kỳ tài liệu nào của môn học.
2. **Frontend (Cloudflare Pages):** 
   - Thêm nút `📂 Xem tệp tin` trên mỗi thẻ môn học tại tab "Quản lý Sổ Hộ Khẩu".
   - Thiết kế Modal `modal-course-files` chuẩn Glassmorphism (Tailwind CSS Dark Theme) gồm Header thông tin môn (NLM ID, Thư mục local, Tổng số file, Dung lượng), Thanh tìm kiếm nhanh & Bộ lọc loại tài liệu, Bảng danh sách file kèm badge trạng thái chi tiết, và nút mở trực tiếp Google Drive.
   - Thêm tính năng phím tắt (ESC đóng modal, click backdrop đóng).
   - Đồng bộ sang `public/index.html` và build `dist/`, sau đó deploy Worker & Pages.

**Tech Stack:** JavaScript (ES Modules, Hono, Tailwind CSS CDN, Cloudflare Workers & Pages).

---

## Global Constraints
- Không làm gián đoạn các luồng upload, reconcile, và poller của Local Agent đang chạy.
- Giữ nguyên thiết kế tối (Dark Mode `bg-slate-950`) đồng bộ với nhận diện thương hiệu ThsAutoOrganizer.
- Bảo toàn 100% test cases (Worker Vitest 32/32 tests, Python Pytest 149/149 tests).

## Review Focus
1. Người dùng có nhiều file hoặc chưa có file nào trong môn học -> Phải có empty state thân thiện kèm nút chuyển nhanh sang tab Kéo thả Upload.
2. File có hoặc không có `drive_view_link` -> Nút mở Drive chỉ hiển thị khi có link hợp lệ.
3. Tìm kiếm file theo tên (search filter) -> Lọc realtime mượt mà, không giật lag.
4. Trạng thái NLM: phân biệt rõ `synced` (Đã nạp NLM), `pending` (Đang nạp AI), `skipped_ext`/`skipped_no_course`.

---

### Task 1: Nâng cấp Backend Worker Route `GET /api/files`

**Files:**
- Modify: `cloudflare/workers/src/routes/files/list.js`
- Test: `cloudflare/workers/tests/routes.test.js`

- [x] **Step 1: Viết test cho `GET /api/files?course_id=...`** trong `cloudflare/workers/tests/routes.test.js`
- [x] **Step 2: Chạy Vitest để xác nhận**
- [x] **Step 3: Cập nhật logic lọc trong `cloudflare/workers/src/routes/files/list.js`** để khi có `course_id`, cho phép khớp `f.course_id === courseId` hoặc khớp `subject / local_folder_name`.
- [x] **Step 4: Chạy lại toàn bộ Worker tests** (`npm test` trong `cloudflare/workers/`)

---

### Task 2: Xây dựng Giao diện Modal & Logic "Chi Tiết Tệp Tin Môn Học" trên Frontend

**Files:**
- Modify: `cloudflare/pages/src/index.html`
- Sync: `public/index.html`

- [x] **Step 1: Thêm Markup Modal `modal-course-files`** vào `cloudflare/pages/src/index.html` với đầy đủ các thành phần:
  - Header: Tên môn học, Thư mục máy, NLM ID, tổng số tệp, tổng dung lượng.
  - Controls: Input tìm kiếm tên file, Dropdown lọc theo loại tài liệu (Tất cả, Giáo trình, Slide, Bài báo, Ấn phẩm).
  - Body: Danh sách thẻ file trực quan với icon theo đuôi file, tên file, badge loại tài liệu, badge trạng thái NLM / Drive, ngày giờ tải lên, và nút link Drive.
  - Empty State: Hiển thị khi môn học chưa có file nào hoặc tìm kiếm không thấy kết quả, có nút "☁️ Nạp tệp tin cho môn này".
- [x] **Step 2: Thêm nút `📂 Xem tệp tin` trên mỗi thẻ môn học** trong hàm `loadCourses()`.
- [x] **Step 3: Viết các hàm Controller JavaScript**:
  - `openCourseFilesModal(courseId)`: Fetch `GET /api/files?course_id=...`, tính toán thống kê, hiển thị modal.
  - `closeCourseFilesModal()`: Ẩn modal.
  - `filterCourseFiles()`: Lọc danh sách file realtime theo search query và document type.
  - `formatBytes(bytes)`: Định dạng dung lượng sang KB/MB/GB.
  - `formatDocTypeBadge(type)`: Tạo badge đẹp mắt theo loại tài liệu.
  - `formatFileStatusBadge(file)`: Tạo badge trạng thái (NLM Synced, Drive Synced, v.v.).
- [x] **Step 4: Đồng bộ sang `public/index.html`** và chạy `node cloudflare/pages/scripts/build.js`.

---

### Task 3: Kiểm thử & Triển khai (Build & Deploy)

**Files:**
- Build & Deploy Cloudflare Pages & Worker

- [x] **Step 1: Chạy toàn bộ test suites** (Vitest 32 tests & Pytest 149 tests).
- [x] **Step 2: Build Cloudflare Pages** (`npm run build` trong `cloudflare/pages`).
- [x] **Step 3: Deploy Cloudflare Worker & Pages** lên production.
- [x] **Step 4: Xác nhận hoạt động trên môi trường thật**.
