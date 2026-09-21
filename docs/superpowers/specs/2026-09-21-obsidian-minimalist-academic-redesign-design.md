# Thiết Kế Kiến Trúc & Giao Diện: Obsidian Minimalist Academic Workspace (ThsAutoOrganizer Studio)

**Ngày lập**: 2026-09-21  
**Trạng thái**: Đã phê duyệt qua Brainstorming  
**Định hướng thẩm mỹ**: Chủ nghĩa Tối giản (Minimalism) phong cách Obsidian — Chỉn chu, thanh lịch, học thuật và tĩnh lặng.

---

## 1. Bối cảnh & Mục tiêu (Context & Goals)

### 1.1. Thực trạng cần giải quyết
1. **Rò rỉ dữ liệu cũ khi Logout**: Khi sinh viên bấm đăng xuất, các thẻ thống kê vẫn lưu vết đường dẫn thư mục cá nhân máy tính (`H:\2026\Thac Sy\Users_Storage\mongxuancomestic...`) và tài khoản Google Drive của người vừa đăng xuất.
2. **Quá nhiều điểm đăng nhập rời rạc**: Trên một màn hình xuất hiện tới 4 khu vực đăng nhập (Góc trên Topbar, Banner cảnh báo giữa màn hình, Hộp trống ở khu vực tài liệu, Menu Sidebar), tạo cảm giác chắp vá và gây rối mắt.
3. **Menu tính năng bị phân mảnh**: Các mục *Kho tài liệu*, *Nạp đa thiết bị*, *Google Drive*, *AI Phân loại* bị tách thành 4 mục riêng trên Sidebar, trong khi bản chất chúng đều là các khâu của một tính năng duy nhất: **Quản lý & Tổ chức Tài liệu Học tập**.

### 1.2. Mục tiêu thiết kế
* Tái cấu trúc Menu Sidebar thành 4 mục mạch lạc, trật tự.
* Tạo ra một điểm Đăng nhập duy nhất, trang nhã tại góc phải thanh Topbar.
* Đảm bảo chu trình Đăng xuất (Logout) xóa sạch 100% dữ liệu trong DOM, bộ nhớ tạm và điều hướng ngay về Trang chủ.
* Hợp nhất các chức năng nạp tệp, xem tài liệu, cấu hình máy tính và Google Drive vào một không gian làm việc tĩnh lặng **"Tổ chức tài liệu"** với 2 Sub-Tabs rõ ràng.
* Áp dụng bảng màu và kiểu chữ **Obsidian Minimalist** (than chì sâu, viền mảnh siêu thực, typography học thuật, không gradient sặc sỡ).

---

## 2. Kiến Trúc Điều Hướng & Quản Lý Phiên (Navigation & Auth)

### 2.1. Cấu trúc Menu Sidebar
Sidebar được tinh giản tối đa, chỉ giữ các mục thiết yếu cho việc học tập và nghiên cứu:

```
ThsOrganizer (Studio Edition)
├── 🏠 Trang chủ         (Tổng quan hệ thống, triết lý tối giản, hướng dẫn)
├── 📚 Tổ chức tài liệu   (Không gian làm việc chính: Kho tệp, AI phân loại, Nạp tệp & Drive)
├── 🔍 Tra cứu           (Tìm kiếm nhanh tài liệu và nội dung trích xuất)
└── ℹ️ Giới thiệu         (Mục tiêu đề án Thạc sĩ HTTT)
```

### 2.2. Điểm Đăng nhập Đơn nhất (Single Entry Point)
* **Vị trí**: Nằm duy nhất tại góc phải của thanh Topbar.
* **Trạng thái chưa đăng nhập**: Nút bấm tối giản `[ 🔑 Đăng nhập ]`. Khi click sẽ mở Modal đăng nhập Google chính thống (kèm tùy chọn kiểm thử nhanh cho nhà phát triển).
* **Trạng thái đã đăng nhập**: Chip hồ sơ nhỏ gọn gồm Avatar chữ cái đầu + Tên/Email sinh viên. Nhấp vào sẽ mở rộng menu cá nhân chứa nút `[ 🚪 Đăng xuất ]`.
* **Loại bỏ**: Xóa bỏ hoàn toàn các banner cảnh báo vàng/đỏ hay các nút login chèn lộn xộn giữa trang.

### 2.3. Quy trình Dọn dẹp Sạch khi Đăng xuất (Zero-Leak Logout Protocol)
Khi người dùng bấm Đăng xuất:
1. Gửi request `POST /auth/logout` để hủy phiên làm việc trên server.
2. Thiết lập `currentUser = null`, `allFiles = []`.
3. Đặt lại toàn bộ thông số trên DOM về giá trị mặc định:
   * `statTotalFiles` = 0
   * `statUploaded` = 0
   * `statNewCount` = 0
   * `statSubjectsCount` = 0
   * `statStoragePath` = "Chưa kết nối thư mục"
   * `statDriveFolder` = "Chưa kết nối Google Drive"
   * `displayUserFolder` = "--"
   * `displayUserEmail` = "--"
   * `displayUserDrive` = "--"
4. Làm rỗng bảng dữ liệu và lưới thẻ tài liệu.
5. Tự động chuyển hướng mượt mà về **Trang chủ (`homeView`)**.

---

## 3. Không Gian Làm Việc "Tổ Chức Tài Liệu" (Unified Workspace)

### 3.1. Cấu trúc Sub-Tabs
Bên trong màn hình **Tổ chức tài liệu**, sinh viên chuyển đổi giữa 2 không gian chuyên biệt:
* **Tab 1: 📁 Kho tài liệu & Phân loại (Mặc định)**
* **Tab 2: ⚡ Nạp & Kết nối (Ingestion & Sync Hub)**

### 3.2. Chi tiết Tab 1: Kho tài liệu & Phân loại
* **4 Thẻ số liệu Obsidian siêu mảnh**:
  1. *Kho tài liệu cá nhân*: Số lượng tệp + đường dẫn thư mục máy tính tương ứng.
  2. *Google Drive*: Số lượng tệp đã đồng bộ + email Drive riêng.
  3. *Tài liệu mới (<24h)*: Số tệp mới nạp trong ngày.
  4. *Môn học theo dõi*: Số lượng môn học đã được AI gom nhóm.
* **Thanh công cụ lọc học thuật**:
  * Ô tìm kiếm tên tệp, môn học.
  * Bộ lọc nhanh: Tất cả, Mới (<24h), Đã lên Drive.
  * Dropdown lọc Môn học, Loại tài liệu (*Giáo trình, Slide, Ôn thi, Tham khảo*), Sắp xếp thời gian.
  * Nút chuyển đổi giao diện: Lưới thẻ (Cards) / Danh sách bảng (Table).
* **Danh sách tài liệu**: Hiển thị thẻ tệp sạch sẽ với huy hiệu môn học, dung lượng, thời gian và nút chỉnh sửa nhanh môn học.

### 3.3. Chi tiết Tab 2: Nạp & Kết nối
* **Phân khu 1: Nạp tài liệu đa thiết bị**:
  * Vùng kéo thả (Dropzone) học thuật tối giản hỗ trợ tệp PDF, DOCX, PPTX, TXT, MD và Ảnh tài liệu/ghi chú bài giảng.
  * Nút thao tác: `📸 Chụp bài giảng (Mobile)`, `📤 Nạp tệp từ máy`, `📁 Chọn thư mục máy tính (HTML5 API)`.
* **Phân khu 2: Trạng thái Kết nối & Đồng bộ**:
  * Cấu hình thư mục lưu trữ cục bộ: Hiển thị đường dẫn hiện tại, nút đổi thư mục, nút quét đồng bộ ngay.
  * Cấu hình Google Drive cá nhân: Trạng thái liên kết OAuth 2.0, tự động băm SHA-256 chống trùng lặp.

### 3.4. Trạng thái khi Chưa Đăng Nhập (Calm Unauthenticated State)
Nếu sinh viên vào "Tổ chức tài liệu" khi chưa đăng nhập:
* Hiển thị duy nhất một khung tĩnh lặng ở trung tâm:
  * Biểu tượng học thuật: 🏛️
  * Tiêu đề: **Không gian Học tập Cá nhân**
  * Nội dung: *Đăng nhập bằng tài khoản Google để kết nối thư mục máy tính và Google Drive cá nhân của bạn.*
  * Nút bấm duy nhất: `[ 🔑 Đăng nhập Google ]`.
  * Dòng liên kết phụ: *Đăng nhập nhanh email sinh viên (Chế độ kiểm thử)*.

---

## 4. Hệ Thống Thẩm Mỹ Obsidian Minimalist (Design System)

| Token | Giá trị | Ý nghĩa & Ứng dụng |
| :--- | :--- | :--- |
| `--bg-base` | `#111113` | Nền trang sâu thẳm, tĩnh lặng |
| `--bg-surface` | `#18181B` | Nền khối thẻ, thanh công cụ, modal |
| `--bg-subtle` | `#222226` | Nền ô tìm kiếm, chip lọc, hover effect |
| `--border-subtle` | `rgba(255, 255, 255, 0.08)` | Đường viền siêu mảnh 1px chia tách không gian |
| `--border-focus` | `rgba(255, 255, 255, 0.22)` | Viền khi active hoặc focus |
| `--text-primary` | `#F4F4F5` | Chữ chính trắng ngà dịu mắt |
| `--text-secondary` | `#A1A1AA` | Chữ phụ, mô tả xám tro |
| `--text-tertiary` | `#71717A` | Chú thích nhỏ, timestamp |
| `--accent-purple` | `#A855F7` | Tím thạch anh học thuật cho icon, badge môn |
| `--accent-emerald` | `#10B981` | Xanh ngọc trầm cho trạng thái đã lưu Drive |
| `--accent-amber` | `#F59E0B` | Vàng ấm cho tài liệu lưu local |

* **Typography**:
  * Giao diện & nội dung: Font `'Inter'`, sans-serif.
  * Đường dẫn & mã kỹ thuật: Font `'JetBrains Mono'`, monospace.
* **Loại bỏ**: Tuyệt đối không dùng gradient 7 màu rực rỡ, không dùng shadow đậm đổ bóng nặng nề.

---

## 5. Kế Hoạch Kiểm Thử & Xác Minh (Verification Plan)

1. **Kiểm thử Đăng xuất (Logout Data Wipe)**:
   * Đăng nhập với tài khoản `mongxuancomestic@gmail.com`.
   * Kiểm tra thông tin đường dẫn và Drive hiển thị đúng.
   * Bấm Đăng xuất.
   * Xác nhận: Thư mục máy tính và Google Drive trên DOM phải quay về mặc định (`--`), danh sách file rỗng, không còn lưu vết tài khoản cũ.
2. **Kiểm thử Điểm Đăng nhập Đơn nhất**:
   * Kiểm tra giao diện khi chưa đăng nhập: Không có banner thừa, chỉ có 1 nút Đăng nhập trên Topbar và 1 khung tĩnh lặng nếu truy cập Workspace.
3. **Kiểm thử Chuyển đổi Sub-Tabs trong Tổ chức tài liệu**:
   * Chuyển mượt mà giữa Tab *Kho tài liệu & Phân loại* và Tab *Nạp & Kết nối*.
4. **Hồi quy toàn bộ Test Suite (pytest)**:
   * Đảm bảo toàn bộ 43+ unit/integration tests tiếp tục pass 100%.
