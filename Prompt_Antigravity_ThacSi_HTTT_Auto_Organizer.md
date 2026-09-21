# Prompt cho Antigravity Local – ThacSi HTTT Auto Organizer

## 1. Vai trò

Bạn là **Senior Python Engineer + Automation Architect**, chuyên xây dựng hệ thống automation trên **Windows 11**, xử lý file, SQLite, Google Drive API và kiến trúc mở rộng AI.

Hãy trực tiếp xây dựng một project Python hoàn chỉnh theo yêu cầu bên dưới.

---

## 2. Mục tiêu hệ thống

Tôi đang học **Thạc sĩ Hệ thống thông tin – định hướng ứng dụng**.

Tôi muốn có một hệ thống tự động:

```text
Người dùng chỉ cần copy/thả file vào:

D:\ThacSi_HTTT\...

        ↓

Python Watcher tự phát hiện file

        ↓

Xác định:
- Môn học
- Loại tài liệu

        ↓

Tính SHA-256 để chống trùng

        ↓

Đọc/extract nội dung tài liệu

        ↓

Upload file lên Google Drive

        ↓

Lưu lịch sử vào SQLite

        ↓

Sau đó dùng Google Drive/NotebookLM Plus làm nguồn học tập
```

### Lưu ý quan trọng

Tôi đang dùng **Google AI Plus / NotebookLM cá nhân**, không phải NotebookLM Enterprise.

Không được giả định rằng tài khoản NotebookLM cá nhân có public API để tự động thêm source vào Notebook.

**Không sử dụng Selenium hoặc Playwright để tự động click NotebookLM UI.**

MVP chỉ cần hoàn thiện:

```text
Windows Folder
→ Python
→ SQLite
→ Google Drive
```

NotebookLM sẽ được sử dụng ở bước sau theo khả năng hiện tại của tài khoản.

---

# 3. Cấu trúc thư mục nguồn

Folder local là **source of truth**.

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

Không để AI tự đoán môn học nếu folder đã xác định rõ.

AI chỉ có thể được bổ sung về sau để **kiểm tra nội dung có khớp folder hay không**.

---

# 4. Mapping

Sử dụng mapping:

```python
SUBJECT_MAP = {
    "Triet_Hoc": "Triết học",
    "Co_So_Du_Lieu": "Cơ sở dữ liệu",
    "Phuong_Phap_Nghien_Cuu": "Phương pháp nghiên cứu"
}

TYPE_MAP = {
    "01_Giao_Trinh": "Giáo trình",
    "02_Slide": "Slide",
    "03_Tai_Lieu_Tham_Khao": "Tài liệu tham khảo",
    "04_On_Thi": "Ôn thi"
}
```

Thiết kế code sao cho sau này dễ thêm môn mới mà không phải sửa nhiều code.

---

# 5. Trải nghiệm người dùng mong muốn

Ví dụ tôi copy:

```text
D:\ThacSi_HTTT\Triet_Hoc\02_Slide\Bai_05.pptx
```

Python tự động:

```text
Phát hiện file
      ↓
Môn = Triết học
Loại = Slide
      ↓
Tính SHA-256
      ↓
Kiểm tra SQLite
      ↓
Nếu chưa có → upload
      ↓
Google Drive:

ThacSi_HTTT
└── Triết học
    └── Slide
        └── Bai_05.pptx
```

Log:

```text
[INFO] Detected: Bai_05.pptx
[INFO] Subject: Triết học
[INFO] Type: Slide
[INFO] SHA256: xxxxxxxxx
[INFO] Uploading to Google Drive...
[INFO] Upload successful
[INFO] Drive file id: xxxxxxxxx
[INFO] Completed
```

Nếu file đã tồn tại theo SHA-256:

```text
[INFO] Duplicate detected by SHA256
[INFO] Skip upload
```

---

# 6. File được hỗ trợ trong MVP

Hỗ trợ:

```text
.pdf
.docx
.pptx
.txt
.md
```

Không cần OCR trong MVP.

Tuy nhiên kiến trúc phải cho phép sau này bổ sung:

```text
Scanned PDF
→ OCR
→ Extract text
→ AI verification
```

---

# 7. File watcher

Sử dụng:

```text
watchdog
```

Watcher phải:

- Theo dõi recursive
- Tự động phát hiện file mới
- Không crash khi một file lỗi
- Chờ file copy hoàn tất trước khi xử lý
- Bỏ qua file tạm
- Bỏ qua extension không hỗ trợ
- Retry khi upload thất bại
- Có log rõ ràng

Ví dụ:

```text
Bai_01.pdf
Bai_02.pptx
Bai_03.docx
```

Nếu tôi copy cả thư mục chứa nhiều file thì hệ thống cũng phải xử lý được.

---

# 8. Stable file detection

Không xử lý ngay khi event `created` xảy ra.

Phải kiểm tra file đã ổn định.

Ví dụ:

```text
File xuất hiện
    ↓
Chờ 3 giây
    ↓
Kiểm tra size
    ↓
Nếu size thay đổi → tiếp tục chờ
    ↓
Nếu size ổn định → xử lý
```

Đưa giá trị này vào config:

```json
"stable_file_wait_seconds": 3
```

---

# 9. SHA-256 Deduplication

Mỗi file phải được tính SHA-256.

Ví dụ:

```text
SHA256(file)
```

SQLite lưu hash.

Nếu:

```text
SHA256 == existing SHA256
```

thì không upload lại.

Quan trọng:

Không dùng filename để chống trùng.

Ví dụ:

```text
Bai1.pdf
```

cùng tên nhưng nội dung khác → vẫn phải xử lý.

---

# 10. SQLite

Dùng SQLite.

Database:

```text
data/files.db
```

Schema tối thiểu:

```text
sha256
path
subject
document_type
drive_file_id
status
error
created_at
```

Nên có thêm:

```text
id
updated_at
```

Có index cho:

```text
sha256
status
```

Các trạng thái có thể gồm:

```text
PENDING
PROCESSING
UPLOADED
DUPLICATE
ERROR
```

Không để lỗi một file làm chết toàn bộ watcher.

---

# 11. Extract text

Tạo module:

```text
src/extractors.py
```

Sử dụng:

```text
PDF     → pypdf
DOCX    → python-docx
PPTX    → python-pptx
TXT     → Python built-in
MD      → Python built-in
```

Interface nên thống nhất, ví dụ:

```python
extract_text(path) -> str
```

Nếu file không extract được:

- ghi log
- lưu ERROR vào SQLite
- không crash chương trình

MVP không cần lưu toàn bộ extracted text vào database.

Nhưng kiến trúc nên cho phép sau này dùng text cho AI verification.

---

# 12. Google Drive

Sử dụng **Google Drive API chính thức**.

Không sử dụng:

```text
Selenium
Playwright
Chrome automation
Cookie hacking
UI automation
```

Authentication dùng OAuth Desktop App.

Project cần:

```text
credentials.json
token.json
```

`credentials.json` do người dùng tự tải từ Google Cloud Console.

Không commit:

```text
credentials.json
token.json
```

vào Git.

Thêm vào `.gitignore`.

---

# 13. Google Drive structure

Drive sẽ có:

```text
ThacSi_HTTT
│
├── Triết học
│   ├── Giáo trình
│   ├── Slide
│   ├── Tài liệu tham khảo
│   └── Ôn thi
│
├── Cơ sở dữ liệu
│   ├── Giáo trình
│   ├── Slide
│   ├── Tài liệu tham khảo
│   └── Ôn thi
│
└── Phương pháp nghiên cứu
    ├── Giáo trình
    ├── Slide
    ├── Tài liệu tham khảo
    └── Ôn thi
```

Nếu folder chưa tồn tại:

```text
→ tự tạo
```

Nếu đã tồn tại:

```text
→ reuse folder
```

Không tạo folder trùng.

Có thể cấu hình root folder bằng:

```json
"google_drive_root_folder_id": ""
```

Nếu để trống thì chương trình có thể tìm/tạo folder:

```text
ThacSi_HTTT
```

---

# 14. config.json

Tạo:

```text
config.json
```

Nội dung mặc định:

```json
{
  "root_folder": "D:\\ThacSi_HTTT",
  "database": "data\\files.db",
  "google_drive_root_folder_id": "",
  "create_drive_subfolders": true,
  "process_existing_files_on_start": true,
  "min_file_size_bytes": 1000,
  "stable_file_wait_seconds": 3
}
```

Không hard-code các path quan trọng trong code.

---

# 15. Project structure

Tạo project:

```text
D:\ThacSi_HTTT_Auto
│
├── main.py
├── config.json
├── requirements.txt
├── README.md
├── .gitignore
├── credentials.json
│
├── data
│   └── files.db
│
├── src
│   ├── __init__.py
│   ├── classifier.py
│   ├── extractors.py
│   ├── database.py
│   ├── drive.py
│   └── processor.py
│
└── tests
    ├── test_classifier.py
    └── test_database.py
```

Nếu `credentials.json` chưa tồn tại thì README phải hướng dẫn người dùng tự đặt file.

Không tạo fake credentials.

---

# 16. classifier.py

Module này chịu trách nhiệm xác định:

```text
subject
document_type
```

Dựa vào path.

Ví dụ:

```text
D:\ThacSi_HTTT\Triet_Hoc\02_Slide\Bai_05.pptx
```

kết quả:

```python
subject = "Triết học"
document_type = "Slide"
```

Nếu path không hợp lệ:

```text
→ raise lỗi rõ ràng
```

Không tự đoán.

Viết unit test cho:

```text
Triet_Hoc / 01_Giao_Trinh
Triet_Hoc / 02_Slide
Co_So_Du_Lieu / 03_Tai_Lieu_Tham_Khao
Phuong_Phap_Nghien_Cuu / 04_On_Thi
```

---

# 17. database.py

Tạo class quản lý SQLite.

Ví dụ:

```python
Database
```

Các method nên có:

```python
initialize()
find_by_sha256()
insert_record()
update_status()
get_record()
```

Không nhúng SQL lung tung trong `main.py`.

Dùng parameterized SQL.

---

# 18. drive.py

Tạo module:

```text
src/drive.py
```

Chịu trách nhiệm:

```text
OAuth
Drive service
Find/create folder
Upload file
```

Ví dụ API:

```python
get_drive_service()
find_or_create_folder()
upload_file()
```

Không để logic watcher trong module Drive.

---

# 19. processor.py

Đây là module orchestration.

Flow:

```text
File
 ↓
Validate
 ↓
Classify
 ↓
Extract text
 ↓
SHA256
 ↓
SQLite lookup
 ↓
Upload Drive
 ↓
Save database
```

Ví dụ:

```python
process_file(path)
```

Nếu lỗi:

```text
SQLite status = ERROR
error = message
```

Watcher vẫn chạy tiếp.

---

# 20. main.py

`main.py` chỉ nên chịu trách nhiệm:

```text
Load config
Initialize database
Scan existing files
Start watchdog
Handle filesystem events
```

Không nên nhồi toàn bộ business logic vào `main.py`.

---

# 21. Process existing files

Nếu:

```json
"process_existing_files_on_start": true
```

thì khi chương trình start:

```text
scan D:\ThacSi_HTTT
```

và xử lý các file hợp lệ chưa có trong database.

Điều này rất quan trọng vì có thể tôi đã copy file trước khi chạy watcher.

---

# 22. Ignore files

Bỏ qua:

```text
.tmp
.temp
.part
.crdownload
~$
.git
.vscode
__pycache__
```

và các file không nằm trong extension hỗ trợ.

---

# 23. Logging

Dùng Python logging.

Log ra:

```text
logs/app.log
```

Nếu cần có console log nữa.

Format dễ đọc:

```text
2026-09-21 10:30:12 | INFO | Detected file: Bai_05.pptx
2026-09-21 10:30:13 | INFO | Subject: Triết học
2026-09-21 10:30:13 | INFO | Type: Slide
2026-09-21 10:30:14 | INFO | SHA256: ...
2026-09-21 10:30:15 | INFO | Upload successful
```

---

# 24. requirements.txt

Tối thiểu:

```text
watchdog
pypdf
python-docx
python-pptx
google-api-python-client
google-auth-httplib2
google-auth-oauthlib
```

Có thể pin version hợp lý nếu cần.

---

# 25. Error handling

Các lỗi cần xử lý:

```text
File đang copy
File bị lock
Permission denied
PDF lỗi
DOCX lỗi
PPTX lỗi
OAuth chưa cấu hình
Network lỗi
Google Drive API lỗi
SQLite lỗi
File bị xóa trong lúc xử lý
```

Nguyên tắc:

```text
Một file lỗi
≠
Toàn bộ chương trình chết
```

Log lỗi rõ ràng.

---

# 26. Retry

Đối với Google Drive/network:

```text
retry 3 lần
```

Có delay giữa các lần retry.

Không retry vô hạn.

---

# 27. Threading / queue

Có thể dùng queue để tránh watchdog event chạy trực tiếp toàn bộ processing.

Kiến trúc ưu tiên:

```text
Watchdog
    ↓
Queue
    ↓
Worker
    ↓
Processor
```

MVP có thể dùng một worker.

Thiết kế sao cho sau này mở rộng nhiều worker được.

---

# 28. Future AI verification

Không cần triển khai AI verification trong MVP.

Nhưng architecture phải cho phép sau này:

```text
Folder:
Triet_Hoc/02_Slide

        ↓

Extract text

        ↓

AI verification

        ↓

"Content appears consistent with Triết học / Slide"
```

Nếu AI phát hiện:

```text
File nằm trong Triết học
nhưng nội dung giống Cơ sở dữ liệu
```

thì sau này có thể:

```text
WARNING
```

Không tự move file ở MVP.

---

# 29. NotebookLM

Đây là điểm rất quan trọng.

Không xây logic:

```text
Python → NotebookLM UI
```

Không dùng Selenium/Playwright.

Không giả định có API NotebookLM cá nhân.

MVP dừng ở:

```text
Windows
→ Python
→ Google Drive
```

Sau đó người dùng dùng Drive làm nguồn cho NotebookLM Plus theo khả năng hiện tại của tài khoản.

Thiết kế code để sau này nếu Google cung cấp API phù hợp thì có thể thêm:

```text
src/notebooklm.py
```

mà không phải viết lại toàn bộ hệ thống.

---

# 30. Test

Tạo test cho:

### classifier

```text
Triet_Hoc + 01_Giao_Trinh
Triet_Hoc + 02_Slide
Co_So_Du_Lieu + 03_Tai_Lieu_Tham_Khao
Phuong_Phap_Nghien_Cuu + 04_On_Thi
```

### database

Test:

```text
insert
find by sha256
duplicate
update status
```

Nếu có thể, thêm test:

```text
same filename + different content
```

phải được xem là hai file khác nhau nếu SHA-256 khác.

---

# 31. README.md

README phải hướng dẫn từng bước cho người dùng Windows.

Bao gồm:

## Cài Python

Ví dụ:

```powershell
python --version
```

## Tạo virtual environment

```powershell
python -m venv .venv
```

## Activate

```powershell
.venv\Scripts\activate
```

## Install

```powershell
pip install -r requirements.txt
```

## Google Cloud setup

Hướng dẫn:

```text
Google Cloud Console
→ Create project
→ Enable Google Drive API
→ OAuth consent screen
→ Create OAuth Client
→ Desktop App
→ Download credentials.json
```

Sau đó:

```text
copy credentials.json
→ D:\ThacSi_HTTT_Auto\
```

Không đưa credential thật vào repository.

## Run

```powershell
python main.py
```

## Test

```powershell
pytest
```

## Example

Đưa:

```text
Bai_05.pptx
```

vào:

```text
D:\ThacSi_HTTT\Triet_Hoc\02_Slide\
```

và giải thích hệ thống sẽ làm gì.

---

# 32. Gitignore

Tạo `.gitignore`:

```text
.venv/
__pycache__/
*.pyc
credentials.json
token.json
data/*.db
logs/
.idea/
.vscode/
```

---

# 33. Code quality

Yêu cầu:

- Python 3.11+
- Type hints
- Docstrings cho class/function quan trọng
- Không dùng biến global tùy tiện
- Không hard-code secret
- Không hard-code Windows username
- Path dùng `pathlib.Path`
- Code dễ đọc
- Module hóa
- Error message rõ
- Logging thay vì `print()` cho runtime
- Không viết code thừa

---

# 34. Security

Tuyệt đối không:

```text
commit credentials.json
commit token.json
log OAuth token
hard-code Google credentials
```

README phải cảnh báo người dùng.

---

# 35. Acceptance criteria

Project được xem là hoàn thành khi:

### A. Local watcher

Tôi copy:

```text
D:\ThacSi_HTTT\Triet_Hoc\02_Slide\Bai_05.pptx
```

→ watcher phát hiện.

### B. Classification

Output:

```text
Subject = Triết học
Type = Slide
```

### C. Hash

SHA-256 được tính.

### D. Dedup

Copy lại cùng file:

```text
→ không upload lần 2
```

### E. Different content

Cùng filename nhưng nội dung khác:

```text
→ SHA khác
→ xử lý như file mới
```

### F. Drive

File được upload vào:

```text
ThacSi_HTTT
→ Triết học
→ Slide
```

### G. SQLite

Database lưu:

```text
sha256
path
subject
document_type
drive_file_id
status
error
created_at
```

### H. Error

Một file lỗi:

```text
→ log ERROR
→ database ERROR
→ watcher tiếp tục
```

### I. Startup scan

Nếu có file từ trước:

```text
→ start app
→ scan
→ process
```

---

# 36. Sau khi build xong

Không chỉ viết code.

Hãy thực hiện:

1. Tạo toàn bộ project.
2. Tạo các file cần thiết.
3. Cài dependencies nếu môi trường cho phép.
4. Kiểm tra syntax.
5. Chạy unit tests.
6. Nếu Google OAuth chưa có credentials thật thì phải nói rõ bước nào chưa thể test.
7. Không tạo fake Google credentials.
8. Báo cáo kết quả.

Report cuối cùng cần có:

```text
PROJECT STATUS

[OK] Project structure
[OK] Classifier
[OK] Extractors
[OK] SQLite
[OK] Watchdog
[OK] Google Drive integration
[OK] Tests
[OK] README

[WAITING] Google OAuth credentials
```

Nếu phần nào chưa test được thì ghi rõ lý do.

---

# 37. Quan trọng: đừng chỉ giải thích

Tôi không muốn bạn chỉ trả lời bằng lý thuyết.

Hãy **tạo code/project thật trong workspace hiện tại**.

Nếu gặp lỗi:

```text
→ tự kiểm tra
→ sửa
→ chạy lại
→ test lại
```

Ưu tiên một MVP chạy được trước, sau đó mới cải thiện architecture.

Mục tiêu cuối cùng:

```text
Tôi chỉ cần thả tài liệu vào:

D:\ThacSi_HTTT\...

và hệ thống tự động:

Detect
→ Classify
→ Extract
→ SHA256
→ Deduplicate
→ Upload Google Drive
→ Record SQLite
→ Log

```

Hãy bắt đầu xây dựng project ngay.
