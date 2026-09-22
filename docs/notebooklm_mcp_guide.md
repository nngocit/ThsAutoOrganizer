# Hướng Dẫn Kích Hoạt & Khai Thác Google NotebookLM Plus MCP Trên ThsAutoOrganizer

> **Tài liệu hướng dẫn vận hành kỹ thuật (User & Agent Guide)**  
> **Dự án:** ThsAutoOrganizer – Multi-Major Academic Assistant  
> **Giao thức:** Model Context Protocol (MCP) & Native Python Pipeline  

---

## 1. Tổng Quan Về Kiến Trúc Kết Hợp 4 Bước

Hệ sinh thái ThsAutoOrganizer đã được kết nối khép kín với **Google NotebookLM Plus**:
1. **Bước 1 (Thu thập & Phân loại):** Bạn tải bài giảng, slide, ảnh chụp đề thi lên Web ThsAutoOrganizer. Hệ thống băm mã SHA-256, phân loại đúng môn học và lưu vào thư mục chuẩn + sync Google Drive.
2. **Bước 2 (Nạp nguồn tự động - Auto-Ingestion):** ThreadPool ngầm của ThsAutoOrganizer tự động kích hoạt `nlm source add`, đẩy thẳng file tài liệu vào đúng Sổ tay (Notebook) môn học trên NotebookLM Plus mà không làm chậm giao diện web.
3. **Bước 3 (Truy vấn Siêu tốc từ AntiGravity IDE):** Bạn mở chat AntiGravity gõ:  
   `"@notebooklm Hãy trích xuất cho tôi 3 luận điểm chính về NQ 27 từ Notebook Triết học kèm số trang trích dẫn."`  
   Agent sẽ truy vấn NotebookLM Plus và trả kết quả chính xác tuyệt đối kèm Citations (số trang, đoạn văn bản nguồn).
4. **Bước 4 (Xuất bản ngược lại Web Dashboard):** Các bài phân tích, bộ câu hỏi trắc nghiệm (Quiz), đề cương được lưu vào CSDL và hiển thị ngay trên Tab mới **"🧠 AI Study Hub"** của Web ThsAutoOrganizer.

---

## 2. Hướng Dẫn Cài Đặt & Đăng Nhập (1 Lần Duy Nhất)

### Bước 2.1: Cài đặt công cụ CLI trên máy tính
Mở PowerShell hoặc Command Prompt và chạy lệnh cài đặt package Python:
```powershell
pip install notebooklm-mcp-cli
```
*(Hoặc nếu bạn dùng công cụ `uv`: `uv tool install notebooklm-mcp-cli`)*

### Bước 2.2: Đăng nhập tài khoản Google (Có NotebookLM Plus)
Chạy lệnh sau trên terminal:
```powershell
nlm login
```
* **Hiện tượng:** Một cửa sổ trình duyệt an toàn sẽ mở ra.
* **Thao tác:** Bạn chỉ cần đăng nhập tài khoản Google của bạn (tài khoản đã nâng cấp gói Google One AI Premium / NotebookLM Plus).
* **Kết quả:** Trình duyệt tự động đóng và phiên làm việc (session token) được mã hóa, lưu trữ an toàn cục bộ trên máy tính (`%USERPROFILE%\.notebooklm`).

### Bước 2.3: Kiểm tra cấu hình MCP của AntiGravity
Hệ thống đã tự động tạo file cấu hình MCP tại:
[`.agents/mcp_config.json`](file:///h:/2026/Thac%20Sy/App/ThsAutoOrganizer/.agents/mcp_config.json)
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
*Khi mở AntiGravity IDE, IDE sẽ tự động kết nối với MCP Server `notebooklm`.*

---

## 3. Các Câu Prompt Mẫu Đỉnh Cao Trong AntiGravity Chat

Khi lập trình hoặc ôn tập trong AntiGravity, bạn có thể gọi trực tiếp công cụ NotebookLM:

### Mẫu 1: Trích xuất luận điểm kèm số trang trích dẫn
```markdown
@notebooklm Hãy tra cứu trong sổ tay môn "Triết học":
Trích xuất 3 luận điểm trọng tâm về NQ 27 Hội nghị Trung ương 6.
Yêu cầu bắt buộc: Kèm theo số trang trích dẫn chính xác từ tài liệu nguồn.
```

### Mẫu 2: Soạn bộ câu hỏi trắc nghiệm Quiz & Đẩy về Web
```markdown
@notebooklm Hãy tạo 5 câu hỏi trắc nghiệm ôn tập về "Toán khoa học dữ liệu" 
(Chương Xác suất thống kê) dựa trên slide bài giảng đã nạp. 
Định dạng JSON chuẩn: [{"q": "...", "options": ["A", "B", "C", "D"], "ans": "A", "explain": "Trích từ Slide 02 trang 15"}].
Sau đó hãy lưu kết quả này vào Web ThsAutoOrganizer qua API POST /api/ai/insights.
```

### Mẫu 3: Xây dựng Đề cương ôn thi cuối kỳ
```markdown
@notebooklm Hãy đọc toàn bộ tài liệu trong sổ tay môn "Cơ sở dữ liệu", 
lập dàn ý đề cương ôn thi gồm 4 phần trọng tâm và các câu hỏi tự luận tiềm năng. 
Đẩy bài viết này vào AI Study Hub của môn Cơ sở dữ liệu.
```

---

## 4. Khai Thác Giao Diện Web "🧠 AI Study Hub"

Mở trình duyệt truy cập: `http://localhost:8080` (hoặc domain Cloudflare Tunnel từ điện thoại).

1. **Thanh điều hướng:** Bấm chọn mục **"🧠 AI Study Hub"** (có huy hiệu `Plus` xanh lá).
2. **Huy hiệu kết nối:**
   - 🟢 **Xanh lá:** NotebookLM Plus đã sẵn sàng.
   - 🟡 **Vàng:** Cần mở terminal gõ `nlm login` để cập nhật session.
   - 🔴 **Đỏ:** Chưa cài đặt thư viện CLI.
3. **Hộp hỏi đáp nhanh (Quick Research Box):**
   - Chọn môn học muốn tra cứu.
   - Nhập câu hỏi (ví dụ: *"Chuẩn hóa dữ liệu dạng 3NF là gì?"*).
   - Bấm **"Gửi câu hỏi"** -> Gemini 1.5 Pro trả kết quả tức thì kèm danh sách Citations.
   - Bấm nút **"💾 Lưu vào Hub"** để lưu kết quả thành bài học chung.
4. **Luyện tập Trắc nghiệm (Interactive Quiz Player):**
   - Với các thẻ bài dạng Quiz, bấm nút **"🎯 Luyện tập Quiz"**.
   - Bấm chọn đáp án A / B / C / D: Đúng hiện xanh lá, Sai hiện đỏ và hiển thị ngay lời giải thích trích dẫn từ giáo trình.
5. **Ngăn xem trích dẫn (Citations Drawer):**
   - Dưới mỗi thẻ bài có mục **"📎 Trích dẫn nguồn (N dẫn chứng)"**.
   - Bấm mở để xem chính xác tài liệu nguồn và số trang mà AI đã trích dẫn.

---

## 5. Xử Lý Sự Cố (Troubleshooting)

| Tình huống | Nguyên nhân | Cách khắc phục |
| :--- | :--- | :--- |
| Badge báo *"Cần đăng nhập"* | Cookie phiên Google hết hạn | Mở PowerShell và gõ `nlm login`, đăng nhập lại trong cửa sổ trình duyệt |
| Tệp `.zip` hoặc `.py` không nạp vào NotebookLM | Định dạng không hỗ trợ | Hệ thống tự động gán nhãn `skipped`. NotebookLM chỉ hỗ trợ PDF, DOCX, PPTX, TXT, MD, MP3 |
| Có tệp bị lỗi mạng khi nạp | Mạng gián đoạn lúc upload | Trên Web AI Study Hub, bấm nút **"🔄 Nạp lại tệp chờ sync"** |
