# Thiết kế Giao diện Google AI Studio & NotebookLM 3-Cột (ThsAutoOrganizer)

**Ngày:** 23/09/2026  
**Chủ đề:** Nâng cấp UI Cloudflare Pages theo phong cách Google AI Studio kết hợp bố cục 3 cột kinh điển của NotebookLM  
**Trạng thái:** Bản thảo hoàn chỉnh (Validated Design Spec)

---

## 1. Mục tiêu & Định hướng Thiết kế

Ứng dụng chuyển đổi từ phong cách **Obsidian Minimalist** (tông tím đen tối giản) sang phong cách **Google AI Studio Developer Workbench** kết hợp **Google NotebookLM 3-Column Studio**, mang lại cảm giác chuyên nghiệp, thông thoáng, thân thuộc và tối ưu năng suất học tập nghiên cứu cao học.

### Các trụ cột chính:
1. **Bố cục 3 cột (3-Column Layout):**
   - **Cột Trái (Sources Panel — 280px):** Chọn môn học, xem nguồn tài liệu (PDF, Docs, Slides, Web), bật/tắt checkbox chọn nguồn để lọc ngữ cảnh, nút "+ Thêm nguồn".
   - **Cột Giữa (Center Canvas — 1fr):** Không gian làm việc chính cho các Tab (Chat AI, AI Study Hub, Quản lý Files, Duyệt nguồn web, Trạm Ôn thi, Kho Xuất bản).
   - **Cột Phải (Studio Panel — 300px):** Bảng công cụ sinh nội dung nhanh (Quiz, Tóm tắt, Đề cương, Slide) và kho lưu trữ Artifacts/Ghi chú của môn học. Có nút thu gọn/mở rộng `[ ◨ ]`.
2. **Hệ thống Theme Dark / Light Switcher:**
   - **Dark Mode (Mặc định):** Tông than chì sâu Google AI Studio (`#131314` / `#1e1f20`), viền xám mảnh (`#3c4043`), chữ sáng (`#e3e3e3`), điểm nhấn xanh Google Blue (`#1a73e8` / `#8ab4f8`) và gradient Gemini.
   - **Light Mode:** Tông trắng xám sạch sẽ chuẩn Google Workspace / Cloud Console (`#f8f9fa` / `#ffffff`), viền xám sáng (`#dadce0`), chữ đen xám (`#202124`).
   - Lưu lựa chọn vào `localStorage.getItem('ths_theme')` và tự động áp dụng khi mở trang.
3. **Typography & Component Styling:**
   - Font Inter / Google Sans hiện đại, hỗ trợ font JetBrains Mono cho code blocks và trích dẫn khoa học.
   - Cards phẳng viền mảnh thanh lịch, nút bấm pill-style, bong bóng chat thanh thoát, input prompt cố định với nút gửi xanh nổi bật.

---

## 2. Kiến trúc & Hệ thống Tokens (Design Tokens)

### 2.1 CSS Variables trong `main.css`

```css
:root {
  /* Fonts */
  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;

  /* Spacing & Radii */
  --sp-1: 4px;  --sp-2: 8px;  --sp-3: 12px;  --sp-4: 16px;
  --sp-6: 24px; --sp-8: 32px;
  --r-xs: 4px;  --r-sm: 8px;  --r-md: 12px;  --r-lg: 16px; --r-full: 9999px;

  /* Transitions */
  --t-fast: 150ms ease;
  --t-med: 250ms ease;

  /* Status Colors (Đồng nhất giữa Dark và Light) */
  --success: #22c55e;
  --warning: #f59e0b;
  --danger:  #ef4444;
  --info:    #3b82f6;
}

/* Dark Theme (Default) */
[data-theme="dark"], :root:not([data-theme="light"]) {
  color-scheme: dark;
  --bg:          #131314; /* Nền chính AI Studio */
  --bg-surface:  #1e1f20; /* Panel / Card */
  --bg-elevated: #282a2c; /* Input / Hover / Drawer */
  --bg-accent:   rgba(26, 115, 232, 0.15);
  
  --border:      #3c4043; /* Viền AI Studio */
  --border-subtle: #282a2c;

  --text:        #e3e3e3;
  --text-muted:  #9aa0a6;
  --text-dim:    #5f6368;

  --primary:     #8ab4f8; /* Google Blue sáng */
  --primary-hover: #aecbfa;
  --primary-bg:  #1a73e8;

  --gemini-gradient: linear-gradient(135deg, #4285f4 0%, #9b72cf 50%, #d96570 100%);
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.5);
  --shadow-md: 0 4px 16px rgba(0,0,0,0.4);
}

/* Light Theme */
[data-theme="light"] {
  color-scheme: light;
  --bg:          #f8f9fa; /* Nền xám nhạt Google */
  --bg-surface:  #ffffff; /* Panel / Card trắng */
  --bg-elevated: #f1f3f4; /* Input / Hover */
  --bg-accent:   rgba(26, 115, 232, 0.08);

  --border:      #dadce0;
  --border-subtle: #e8eaed;

  --text:        #202124;
  --text-muted:  #5f6368;
  --text-dim:    #80868b;

  --primary:     #1a73e8; /* Google Blue chuẩn */
  --primary-hover: #1557b0;
  --primary-bg:  #1a73e8;

  --gemini-gradient: linear-gradient(135deg, #1a73e8 0%, #8e24aa 50%, #d93025 100%);
  --shadow-sm: 0 1px 3px rgba(60,64,67,0.15);
  --shadow-md: 0 4px 16px rgba(60,64,67,0.1);
}
```

---

## 3. Cấu trúc DOM & Bố cục Giao diện

### 3.1 Cấu trúc App Shell (`index.html`)

```html
<div class="app-shell" id="app-shell">
  <!-- Topbar Cố Định -->
  <header class="studio-topbar">
    <div class="topbar-left">
      <div class="brand">
        <span class="gemini-sparkle">✨</span>
        <span class="brand-title">ThsAutoOrganizer</span>
        <span class="badge-studio">Studio</span>
      </div>
      <div id="nlm-status-badge" class="nlm-status-badge">...</div>
    </div>

    <!-- Thanh Điều Hướng Tab Chính Giữa -->
    <nav class="studio-nav-tabs">
      <button class="nav-tab active" data-tab="study-hub">🧠 Study Hub</button>
      <button class="nav-tab" data-tab="chat">💬 Chat AI</button>
      <button class="nav-tab" data-tab="dashboard">📁 Files</button>
      <button class="nav-tab" data-tab="review">🔍 Duyệt nguồn</button>
      <button class="nav-tab" data-tab="exam">🎯 Ôn thi</button>
      <button class="nav-tab" data-tab="artifacts">📦 Xuất bản</button>
    </nav>

    <!-- Khu Vực Điều Khiển Phải -->
    <div class="topbar-right">
      <button id="theme-toggle-btn" class="btn-icon" title="Chuyển Dark / Light">☀️</button>
      <div class="user-menu">
        <img id="user-avatar" class="avatar" src="" alt="User">
        <span id="user-name" class="user-name"></span>
        <button id="btn-sign-out" class="btn-ghost btn-sm">Thoát</button>
      </div>
    </div>
  </header>

  <!-- Thân Ứng Dụng 3 Cột -->
  <div class="studio-body">
    <!-- CỘT 1: NGUỒN TÀI LIỆU (Sources Panel) -->
    <aside class="panel-sources" id="panel-sources">
      <div class="panel-header">
        <div class="panel-title">📚 Nguồn tài liệu</div>
        <button class="btn btn-primary btn-sm" id="btn-quick-add-source">＋ Thêm</button>
      </div>
      <div class="course-picker-wrapper">
        <select id="global-course-select" class="course-select">
          <option value="">-- Chọn môn học --</option>
        </select>
      </div>
      <div class="sources-list" id="panel-sources-list">
        <!-- Danh sách file kèm checkbox và trạng thái NLM -->
      </div>
    </aside>

    <!-- CỘT 2: KHÔNG GIAN LÀM VIỆC CHÍNH (Center Canvas) -->
    <main class="panel-canvas" id="panel-canvas">
      <section class="page-section" id="page-study-hub">...</section>
      <section class="page-section" id="page-chat">...</section>
      <section class="page-section" id="page-dashboard">...</section>
      <section class="page-section" id="page-review">...</section>
      <section class="page-section" id="page-exam">...</section>
      <section class="page-section" id="page-artifacts">...</section>
    </main>

    <!-- CỘT 3: STUDIO & GHI CHÚ (Studio Panel) -->
    <aside class="panel-studio" id="panel-studio">
      <div class="panel-header">
        <div class="panel-title">🎨 Studio Ấn phẩm</div>
        <button class="btn-icon btn-sm" id="btn-toggle-studio-panel" title="Thu gọn/Mở rộng">◨</button>
      </div>
      <div class="studio-quick-actions">
        <button class="btn-studio-action" id="studio-action-quiz">🎯 Tạo Quiz trắc nghiệm</button>
        <button class="btn-studio-action" id="studio-action-summary">📝 Tóm tắt bài học</button>
        <button class="btn-studio-action" id="studio-action-outline">📋 Đề cương ôn tập</button>
        <button class="btn-studio-action" id="studio-action-slides">📊 Slide thuyết trình</button>
      </div>
      <div class="studio-artifacts-list" id="studio-artifacts-list">
        <!-- Danh sách Insights/Artifacts đã xuất bản của môn học -->
      </div>
    </aside>
  </div>
</div>
```

---

## 4. Tương tác & Luồng Dữ Liệu (Interaction & State Management)

1. **Theme Switcher:**
   - `app.js` khởi tạo đọc `localStorage.getItem('ths_theme')` (mặc định `'dark'`).
   - Khi bấm `#theme-toggle-btn`: Toggle `document.documentElement.setAttribute('data-theme', newTheme)` và cập nhật icon (☀️ khi dark, 🌙 khi light).
2. **Đồng bộ Môn học Toàn Cục (Global Course Selection):**
   - Dropdown `#global-course-select` ở cột trái nạp tất cả môn học.
   - Khi chọn một môn học, tự động:
     - Nạp danh sách file nguồn của môn đó vào Cột 1 (`panel-sources-list`).
     - Lọc dữ liệu hiển thị tương ứng ở Cột 2 (Study Hub insights, Chat context, Dashboard files).
     - Nạp danh sách ấn phẩm đã tạo của môn học vào Cột 3 (`studio-artifacts-list`).
3. **Cột 3 Toggle Thu gọn (Collapsible Studio Drawer):**
   - Nút `#btn-toggle-studio-panel` thêm/bỏ class `.collapsed` vào `#panel-studio`.
   - Khi `.collapsed`, Cột 3 thu về dạng thanh mỏng (44px) với icon, giải phóng độ rộng tối đa cho Canvas giữa.

---

## 5. Kế hoạch Kiểm thử & Triển khai

1. **Kiểm tra tương thích & Syntax:**
   - Chạy `node scripts/build.js` kiểm tra đóng gói Pages thành công.
   - Chạy `pytest tests/` bảo đảm toàn bộ 80 unit tests backend vẫn pass 100%.
2. **Kiểm tra trực quan & Chức năng (Verification Checklist):**
   - Chuyển đổi Dark / Light mode: màu sắc hiển thị đúng, tương phản tốt, không bị chữ trắng nền trắng.
   - Bố cục 3 cột hiển thị đẹp mắt, cuộn độc lập giữa các cột.
   - Nút đóng/mở Cột 3 hoạt động mượt mà.
   - Đầy đủ tính năng Chat AI, Study Hub Quick Research, File Upload và Trạm Ôn thi.
3. **Triển khai:**
   - Deploy trực tiếp lên Cloudflare Pages (`https://ths-organizer.pages.dev`).
