# [Tài liệu Đặc tả Kiến trúc] Module Global Settings & System Logs Dashboard

- **Ngày ban hành:** 2026-09-23
- **Tác giả:** Business Analyst (AI Pair Programmer)
- **Dự án:** ThsAutoOrganizer (Cloudflare Workers + Firestore + Python Local Agent)
- **Trạng thái:** Chờ duyệt (Pending Review)

---

## 1. Bối cảnh & Vấn đề Cần giải quyết

1. **Vấn đề cấu hình cứng (Hardcoded Paths):**
   - Hiện tại đường dẫn thư mục quét tài liệu (`local_base_path`) và ID thư mục gốc Google Drive (`google_drive_root_folder_id`) đang nằm phân tán trong file `config.json` trên máy cá nhân.
   - Giao diện Web (Cloudflare Pages) không thể xem hoặc điều chỉnh thư mục này, dẫn đến việc người dùng không biết Agent đang quét ổ đĩa nào và không thể đổi thư mục từ xa.
2. **Vấn đề thiếu quan sát sự cố (Lack of Observability):**
   - Khi có sự cố xảy ra (ví dụ: Google Drive chặn quyền, URL tài liệu bị lỗi, NLM CLI quá thời gian timeout, môn học chưa có notebook ID), lỗi chỉ in ra cửa sổ Terminal của Local Agent.
   - Người dùng làm việc trên Web hoàn toàn "mù" thông tin về các tác vụ thất bại, không biết hệ thống đang dính lỗi gì để khắc phục.

---

## 2. Thiết kế Module 1: Global Settings (`system_config`)

### 2.1. Cấu trúc Tài liệu Firestore
- **Đường dẫn Document:** `users/{uid}/system_config/current`
- **Các trường dữ liệu (Schema):**

| Tên trường | Kiểu dữ liệu | Bắt buộc | Mô tả |
|:---|:---:|:---:|:---|
| `local_base_path` | `string` | Có | Đường dẫn thư mục tài liệu trên máy tính (VD: `H:\2026\Thac Sy\Mon_Hoc`) |
| `google_drive_root_folder_id` | `string` | Có | ID thư mục gốc trên Google Drive (VD: `12YHJZzM04Uq0rSKcg-pQGwdFMqKrXE3X`) |
| `google_drive_root_name` | `string` | Không | Tên thư mục gốc để hiển thị trực quan (VD: `ThacSi_HTTT`) |
| `file_watcher_enabled` | `boolean` | Có | Bật/tắt tự động quét file mới trên máy tính (Mặc định: `true`) |
| `auto_sync_nlm` | `boolean` | Có | Bật/tắt tự động đồng bộ vào NotebookLM (Mặc định: `true`) |
| `poll_interval_seconds` | `number` | Có | Tần số Agent kiểm tra hàng đợi (Mặc định: `10`) |
| `supported_extensions` | `array` | Có | Danh sách đuôi file cho phép: `['.pdf', '.docx', '.pptx', '.txt', '.md', '.mp3']` |
| `updated_at` | `string` | Có | Thời điểm cập nhật ISO 8601 gần nhất |
| `updated_by` | `string` | Không | Email hoặc UID của người thực hiện cập nhật |

### 2.2. Cơ chế Đồng bộ 3 Chiều
- **Web UI:** Đọc qua `GET /api/settings/config`; Cập nhật qua `PUT /api/settings/config`.
- **Worker:** Đọc/Ghi trực tiếp collection `users/{uid}/system_config/current`.
- **Local Agent:** Khi khởi động, nạp cấu hình từ Cloud qua `GET /api/settings/config`. Định kỳ mỗi chu kỳ poll kiểm tra `updated_at`; nếu có thay đổi đường dẫn `local_base_path`, Agent tự động tái khởi động `FileWatcher` theo đường dẫn mới mà người dùng không cần can thiệp Terminal.

---

## 3. Thiết kế Module 2: System Logs Dashboard (`system_logs`)

### 3.1. Cấu trúc Tài liệu Firestore
- **Đường dẫn Collection:** `users/{uid}/system_logs`
- **Cấu trúc Log Document:**

| Tên trường | Kiểu dữ liệu | Mô tả |
|:---|:---:|:---|
| `id` | `string` | Khóa chính dạng UUID (VD: `log_e8f29...`) |
| `timestamp` | `string` | Thời gian ghi nhận sự cố ISO 8601 |
| `level` | `string` | Phân loại mức độ: `ERROR`, `WARNING`, `INFO`, `CRITICAL` |
| `source` | `string` | Nguồn gốc: `local_agent`, `worker`, `web_ui` |
| `module` | `string` | Phân hệ phát sinh: `nlm_task_handler`, `drive_sync`, `file_watcher` |
| `action` | `string` | Thao tác đang làm: `source_add`, `upload_file`, `download_file` |
| `subject` | `string` | Tên môn học liên quan (VD: `Triết học`) |
| `file_name` | `string` | Tên file bị ảnh hưởng (VD: `De_Cuong.pdf`) |
| `message` | `string` | Thông báo sự cố ngắn gọn hiển thị trên bảng điều khiển |
| `error_detail` | `string` | Chi tiết kỹ thuật / Stack trace để tra cứu sâu |
| `context` | `map` | Ngữ cảnh: `{ task_id, notebook_id, drive_file_id, local_path, url }` |
| `resolved` | `boolean` | Trạng thái xử lý sự cố (Mặc định: `false`) |

### 3.2. Luồng Xử lý Dữ liệu Lỗi
1. Khi Local Agent gặp lỗi (trong Try/Catch của các tác vụ: NLM CLI lỗi, Drive API lỗi, File Watcher lỗi):
   - Thay vì chỉ ghi ra console, Agent tự động gọi `POST /api/logs` đẩy dữ liệu lỗi lên Cloud.
2. Worker nhận payload, lưu doc vào `users/{uid}/system_logs/{id}`.
3. Web UI có bảng điều khiển tại tab **⚙ Cài đặt**:
   - Tự động nạp danh sách sự cố gần nhất (`GET /api/logs?limit=50`).
   - Hiển thị trực quan theo màu sắc (Đỏ cho `ERROR`, Vàng cho `WARNING`).
   - Có bộ lọc theo môn học, mức độ, và nút "Xem chi tiết" / "Đã xử lý".
