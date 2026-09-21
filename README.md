# ThacSi HTTT Auto Organizer 🎓📁☁️

> Hệ thống tự động hóa phân loại, lưu trữ lịch sử, trích xuất nội dung và đồng bộ tài liệu học tập Thạc sĩ Hệ thống thông tin (HTTT) từ thư mục Windows 11 lên Google Drive, phục vụ làm nguồn tài liệu chất lượng cao cho NotebookLM Plus.

---

## 1. Tính năng nổi bật

- **Tự động phát hiện (Watcher)**: Sử dụng `watchdog` theo dõi đệ quy thư mục cục bộ, đẩy sự kiện vào hàng đợi đa luồng (`Queue + Worker Thread`).
- **Phát hiện file ổn định (Stable File Detection)**: Chờ file hoàn tất quá trình ghi/sao chép (`stable_file_wait_seconds: 3`), loại trừ file tạm của Office (`~$*`, `.tmp`, v.v.).
- **Phân loại chính xác (Path Classifier)**: Tự động nhận diện Môn học (`Triết học`, `Cơ sở dữ liệu`, `Phương pháp nghiên cứu`) và Loại tài liệu (`Giáo trình`, `Slide`, `Tài liệu tham khảo`, `Ôn thi`) từ cấu trúc thư mục.
- **Trích xuất nội dung (Text Extractor)**: Hỗ trợ trích xuất văn bản từ `.pdf`, `.docx`, `.pptx`, `.txt`, `.md`, sẵn sàng cho AI verification sau này.
- **Chống trùng lặp bằng SHA-256 (Deduplication)**: Tính mã băm SHA-256 nội dung file; bỏ qua nếu tài liệu đã tồn tại, xử lý riêng biệt nếu hai file cùng tên nhưng khác nội dung.
- **Lưu trữ & Quản lý trạng thái (SQLite)**: Lưu đầy đủ lịch sử xử lý, đường dẫn, hash, drive_file_id và nhật ký lỗi tại `data/files.db`.
- **Đồng bộ Google Drive API v3**: Tự động tạo cây thư mục tiếng Việt chuẩn hóa trên Google Drive, cache folder ID để tránh duplicate, hỗ trợ Retry 3 lần khi gặp lỗi mạng.
- **Tương thích NotebookLM Plus**: Chuẩn hóa nguồn tài liệu trên Google Drive để người dùng dễ dàng import vào NotebookLM cá nhân mà không cần can thiệp UI trái phép.

---

## 2. Cấu trúc thư mục nguồn (Source of Truth)

Bạn chỉ cần tạo thư mục học tập trên máy tính (ví dụ: `D:\ThacSi_HTTT`) theo cấu trúc sau:

```text
D:\ThacSi_HTTT
│
├── Triet_Hoc
│   ├── 01_Giao_Trinh
│   ├── 02_Slide
│   ├── 03_Tai_Lieu_Tham_Khao
│   └── 04_On_Thi
│
├── Co_So_Du_Lieu
│   ├── 01_Giao_Trinh
│   ├── 02_Slide
│   ├── 03_Tai_Lieu_Tham_Khao
│   └── 04_On_Thi
│
└── Phuong_Phap_Nghien_Cuu
    ├── 01_Giao_Trinh
    ├── 02_Slide
    ├── 03_Tai_Lieu_Tham_Khao
    └── 04_On_Thi
```

### Bảng đối chiếu Môn học & Loại tài liệu:

| Thư mục môn | Tên hiển thị (Drive/DB) | Thư mục loại | Tên loại (Drive/DB) |
|---|---|---|---|
| `Triet_Hoc` | Triết học | `01_Giao_Trinh` | Giáo trình |
| `Co_So_Du_Lieu` | Cơ sở dữ liệu | `02_Slide` | Slide |
| `Phuong_Phap_Nghien_Cuu` | Phương pháp nghiên cứu | `03_Tai_Lieu_Tham_Khao` | Tài liệu tham khảo |
| *(Dễ dàng thêm môn mới)* | *(Cấu hình trong code/config)* | `04_On_Thi` | Ôn thi |

---

## 3. Cấu trúc dự án

```text
ThsAutoOrganizer/
├── .gitignore             # Loại bỏ virtual env, credentials, tokens, logs, db
├── config.json            # Cấu hình đường dẫn, tham số chờ, dung lượng tối thiểu
├── requirements.txt       # Danh sách thư viện Python
├── README.md              # Tài liệu hướng dẫn sử dụng chi tiết
├── main.py                # Điểm khởi chạy ứng dụng (Watcher, Worker, CLI)
├── data/
│   └── files.db           # SQLite database (tự động tạo)
├── logs/
│   └── app.log            # File log hoạt động (tự động tạo)
├── src/
│   ├── __init__.py
│   ├── classifier.py      # Phân loại Môn học & Loại tài liệu theo đường dẫn
│   ├── extractors.py      # Trích xuất text từ PDF, DOCX, PPTX, TXT, MD
│   ├── database.py        # Quản lý SQLite database (schema, CRUD, indexes)
│   ├── drive.py           # Tích hợp Google Drive API v3 (OAuth2, folder sync, upload)
│   └── processor.py       # Điều phối pipeline xử lý tập tin
└── tests/
    ├── __init__.py
    ├── test_classifier.py # Tests phân loại thư mục
    ├── test_database.py   # Tests SQLite & Deduplication
    ├── test_extractors.py # Tests trích xuất nội dung
    ├── test_processor.py  # Tests điều phối pipeline & lỗi an toàn
    └── test_e2e_pipeline.py # Tests mô phỏng toàn bộ luồng E2E
```

---

## 4. Hướng dẫn cài đặt & Thiết lập trên Windows 11

### Bước 1: Kiểm tra Python (Yêu cầu Python 3.11+)

Mở **PowerShell** hoặc **Windows Terminal**:

```powershell
python --version
```

### Bước 2: Tạo và kích hoạt môi trường ảo (Virtual Environment)

```powershell
# Chuyển vào thư mục dự án
cd "H:\2026\Thac Sy\App\ThsAutoOrganizer"

# Tạo venv
python -m venv .venv

# Kích hoạt venv trên PowerShell
.venv\Scripts\Activate.ps1
```

> **Mẹo**: Nếu gặp lỗi PowerShell chặn script (`ExecutionPolicy`), bạn có thể mở quyền tạm thời bằng lệnh:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

### Bước 3: Cài đặt các thư viện phụ thuộc

```powershell
pip install -r requirements.txt
```

---

## 5. Hướng dẫn thiết lập Google Drive OAuth 2.0

Để chương trình có thể tự động tạo thư mục và upload tài liệu lên Google Drive của bạn:

1. Truy cập vào **[Google Cloud Console](https://console.cloud.google.com/)**.
2. **Tạo Project mới** (ví dụ: `ThacSi-HTTT-Organizer`).
3. Bật API:
   - Vào menu **APIs & Services** → **Library**.
   - Tìm kiếm `Google Drive API` và nhấn **Enable**.
4. Cấu hình màn hình đồng thuận OAuth:
   - Vào **APIs & Services** → **OAuth consent screen**.
   - Chọn **User Type: External** → nhấn **Create**.
   - Điền App name (vd: `ThsAutoOrganizer`) và User support email của bạn.
   - Tại mục **Test users**, thêm chính địa chỉ Gmail cá nhân của bạn.
5. Tạo Client ID:
   - Vào **APIs & Services** → **Credentials** → chọn **Create Credentials** → **OAuth client ID**.
   - Application type: Chọn **Desktop app**.
   - Name: `ThsAutoOrganizer Desktop`.
   - Nhấn **Create**.
6. Tải file xác thực:
   - Nhấn biểu tượng tải xuống (Download JSON) của Client vừa tạo.
   - Đổi tên file thành `credentials.json`.
   - Di chuyển file `credentials.json` vào thư mục gốc của project:
     ```text
     H:\2026\Thac Sy\App\ThsAutoOrganizer\credentials.json
     ```

> ⚠️ **CẢNH BÁO BẢO MẬT**:
> - Tuyệt đối **KHÔNG commit** `credentials.json` hoặc `token.json` lên Git/GitHub!
> - File `.gitignore` của dự án đã được cấu hình tự động loại bỏ các file này.

---

## 6. Cấu hình `config.json`

File cấu hình mặc định:

```json
{
  "root_folder": "D:\\ThacSi_HTTT",
  "database": "data\\files.db",
  "google_drive_root_folder_id": "",
  "create_drive_subfolders": true,
  "process_existing_files_on_start": true,
  "min_file_size_bytes": 1000,
  "stable_file_wait_seconds": 3,
  "log_level": "INFO",
  "supported_extensions": [".pdf", ".docx", ".pptx", ".txt", ".md"]
}
```

- `root_folder`: Thư mục học tập trên máy của bạn (nơi bạn thả tài liệu vào).
- `google_drive_root_folder_id`: Bỏ trống để hệ thống tự tạo thư mục `ThacSi_HTTT` trên Drive gốc của bạn, hoặc dán Folder ID của thư mục Drive có sẵn.
- `process_existing_files_on_start`: Tự động quét và xử lý các file đã có trong thư mục khi khởi động app.
- `stable_file_wait_seconds`: Số giây kiểm tra kích thước file không đổi để xác nhận copy hoàn tất.

---

## 7. Khởi chạy hệ thống

### Chạy watcher chính:

```powershell
python main.py
```

- Trong lần chạy đầu tiên (nếu có `credentials.json`), trình duyệt web sẽ tự động mở để bạn đăng nhập và cấp quyền truy cập Drive. Sau đó, mã xác thực sẽ được lưu vào `token.json` cho các lần chạy sau mà không cần hỏi lại.
- Nếu bạn chưa đặt `credentials.json`, hệ thống sẽ hiển thị cảnh báo `[WAITING] Google OAuth credentials` nhưng **vẫn hoạt động hoàn hảo** cho việc phân loại cục bộ, tính hash SHA-256, trích xuất text và lưu trữ vào SQLite.

### Chạy kiểm thử tự động (Unit & Integration Tests):

```powershell
pytest -v
```

Toàn bộ 29 bài test bao phủ các module:
- `test_classifier.py`: Kiểm tra phân loại đường dẫn, kiểm tra lỗi đường dẫn sai cấu trúc.
- `test_database.py`: Kiểm tra tạo database, chỉ mục, thêm mới, chống trùng lặp SHA-256.
- `test_extractors.py`: Kiểm tra trích xuất text từ các định dạng file.
- `test_processor.py`: Kiểm tra pipeline hoàn chỉnh và xử lý lỗi an toàn.
- `test_e2e_pipeline.py`: Kiểm thử tích hợp end-to-end.

---

## 8. Trải nghiệm người dùng mẫu

Giả sử bạn sao chép file slide bài giảng vào:
```text
D:\ThacSi_HTTT\Triet_Hoc\02_Slide\Bai_05.pptx
```

Hệ thống sẽ ghi log trên console và file `logs/app.log`:
```text
2026-09-21 10:40:00 | INFO  | Detected: Bai_05.pptx
2026-09-21 10:40:03 | INFO  | Subject: Triết học
2026-09-21 10:40:03 | INFO  | Type: Slide
2026-09-21 10:40:04 | INFO  | SHA256: 4f8b9e...3c1a
2026-09-21 10:40:04 | INFO  | Trích xuất nội dung thành công (12500 ký tự).
2026-09-21 10:40:05 | INFO  | Uploading to Google Drive...
2026-09-21 10:40:07 | INFO  | Upload successful
2026-09-21 10:40:07 | INFO  | Drive file id: 1aB2cD3eF4gH...
2026-09-21 10:40:07 | INFO  | Completed
```

Tài liệu sẽ xuất hiện trên Google Drive theo cấu trúc:
```text
ThacSi_HTTT/
└── Triết học/
    └── Slide/
        └── Bai_05.pptx
```

Nếu bạn copy lại chính file đó (hoặc file khác nhưng nội dung giống hệt):
```text
2026-09-21 10:42:15 | INFO  | Detected: Bai_05.pptx
2026-09-21 10:42:18 | INFO  | SHA256: 4f8b9e...3c1a
2026-09-21 10:42:18 | INFO  | Duplicate detected by SHA256
2026-09-21 10:42:18 | INFO  | Skip upload
```

---

## 9. Tích hợp với NotebookLM Plus

Sau khi tài liệu đã được tự động phân loại và đưa lên Google Drive:
1. Mở [NotebookLM](https://notebooklm.google.com/) với tài khoản Google AI Plus của bạn.
2. Tạo Notebook cho môn học (ví dụ: *Triết học Thạc sĩ*).
3. Nhấn **Add source** → Chọn **Google Drive**.
4. Chọn trực tiếp thư mục `ThacSi_HTTT / Triết học / Slide` hoặc từng file bài giảng bạn cần học.
5. Tận hưởng nguồn học tập thông minh và có hệ thống!
