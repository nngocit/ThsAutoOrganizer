# Google AI Studio & NotebookLM 3-Column UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuyển đổi toàn diện giao diện web Cloudflare Pages từ Obsidian theme sang phong cách Google AI Studio kết hợp bố cục 3 cột kinh điển của NotebookLM (Nguồn bên trái — Canvas làm việc ở giữa — Studio Panel bên phải), hỗ trợ chuyển đổi Dark / Light mode linh hoạt.

**Architecture:** Bố cục CSS Grid 3 cột (`280px 1fr 300px`) với khả năng thu gọn panel phải. Design Tokens 2 chế độ (`[data-theme="dark"]`, `[data-theme="light"]`) chuẩn Google AI Studio. Tích hợp đồng bộ môn học toàn cục giữa cột Nguồn (Sources), Không gian làm việc (Center Canvas), và Cột Ấn phẩm (Studio Panel).

**Tech Stack:** Vanilla CSS3 (Custom Properties / Grid / Flexbox), Semantic HTML5, Vanilla JavaScript ES Modules, Cloudflare Pages.

**Spec:** [`docs/superpowers/specs/2026-09-23-ai-studio-notebooklm-ui-design.md`](file:///H:/2026/Thac%20Sy/App/ThsAutoOrganizer/docs/superpowers/specs/2026-09-23-ai-studio-notebooklm-ui-design.md)

## Global Constraints
- Phải giữ nguyên 100% các API routes và logic backend Worker / Python agent; không làm hỏng tính tương thích ngược.
- CSS phải tuân thủ chuẩn Design Tokens của Google AI Studio (Dark `#131314`/`#1e1f20`, Light `#f8f9fa`/`#ffffff`, Accent `#1a73e8`/`#8ab4f8`).
- Bố cục 3 cột phải cuộn độc lập và hỗ trợ thu gọn cột phải dạng drawer trên màn hình nhỏ.
- Tất cả 80 unit tests backend hiện tại phải tiếp tục PASS.
- Đóng gói frontend bằng `node scripts/build.js` không được phát sinh lỗi.

## Review Focus
1. Chuyển đổi Dark/Light mode không được gây ra tình trạng chữ trắng trên nền trắng hoặc chữ đen trên nền đen ở bất kỳ component nào.
2. Cột trái (Sources) khi chọn môn học phải cập nhật đồng bộ sang khung Chat và Study Hub mà không cần tải lại trang.
3. Khi thu gọn cột phải (Studio Panel), canvas giữa phải mở rộng mượt mà không làm vỡ bố cục grid/table.
4. Nút bấm Quick Action ở cột Studio phải kích hoạt đúng các luồng sinh Quiz, Tóm tắt, Đề cương tương ứng.
5. Modal upload kéo thả file vẫn phải hoạt động bình thường khi bấm "+ Thêm" ở cột nguồn.

---

### Task 1: Thiết lập Design Tokens & Khung Layout 3 Cột trong `main.css`

**Files:**
- Modify: `cloudflare/pages/src/css/main.css`

**Interfaces:**
- Consumes: Google Fonts (`Inter`, `JetBrains Mono`), HTML Root.
- Produces: CSS custom properties (`--bg`, `--bg-surface`, `--bg-elevated`, `--border`, `--text`, `--primary`), CSS Grid classes `.studio-topbar`, `.studio-body`, `.panel-sources`, `.panel-canvas`, `.panel-studio`.

- [ ] **Step 1: Viết bộ Design Tokens Google AI Studio Dark và Light**
Cập nhật `:root`, `[data-theme="dark"]`, và `[data-theme="light"]` với các mã màu chuẩn xác từ spec.

- [ ] **Step 2: Định nghĩa cấu trúc CSS Grid 3 cột và topbar**
Thiết lập layout `.app-shell`, `.studio-topbar`, `.studio-body`, `.panel-sources` (width: 280px), `.panel-canvas` (flex: 1), `.panel-studio` (width: 300px, transition transform/width khi `.collapsed`).

- [ ] **Step 3: Kiểm tra cú pháp CSS bằng build script**
Chạy: `node scripts/build.js` tại `cloudflare/pages`
Kỳ vọng: PASS

- [ ] **Step 4: Commit**
```bash
git add cloudflare/pages/src/css/main.css
git commit -m "feat(css): add Google AI Studio design tokens and 3-column grid layout"
```

---

### Task 2: Nâng cấp Styles Thẻ, Nút & Bong Bóng Chat trong `components.css`

**Files:**
- Modify: `cloudflare/pages/src/css/components.css`

**Interfaces:**
- Consumes: CSS tokens từ `main.css`.
- Produces: Component classes `.card`, `.badge`, `.btn`, `.btn-primary`, `.btn-studio-action`, `.studio-nav-tabs`, `.citations-drawer`, `.citations-toggle`, `.prompt-bar`.

- [ ] **Step 1: Cập nhật Cards, Badges và Buttons theo chuẩn AI Studio**
Chuyển đổi card viền mảnh `#3c4043`, góc bo `var(--r-md)`, nút bấm chính Google Blue `#1a73e8`, badge bo tròn pill-style.

- [ ] **Step 2: Cập nhật kiểu dáng Bong bóng Chat & Ngăn kéo Trích dẫn NotebookLM**
Tin nhắn người dùng viền xanh xám nhẹ, tin nhắn trợ lý nền phẳng không viền, trích dẫn dạng drawer mở rộng với số thứ tự nguồn `[1]`, `[2]`.

- [ ] **Step 3: Định nghĩa style cho Panel Nguồn và Studio Panel**
Style cho danh sách file nguồn có checkbox (`.source-item`), các nút hành động studio lớn (`.btn-studio-action`).

- [ ] **Step 4: Kiểm tra build**
Chạy: `node scripts/build.js` tại `cloudflare/pages`
Kỳ vọng: PASS

- [ ] **Step 5: Commit**
```bash
git add cloudflare/pages/src/css/components.css
git commit -m "feat(css): style AI Studio cards, buttons, chat bubbles and notebooklm panels"
```

---

### Task 3: Tái Cấu Trúc DOM 3 Cột & Topbar trong `index.html`

**Files:**
- Modify: `cloudflare/pages/src/index.html`

**Interfaces:**
- Consumes: CSS classes từ `main.css` & `components.css`.
- Produces: DOM elements `#theme-toggle-btn`, `#global-course-select`, `#panel-sources`, `#panel-canvas`, `#panel-studio`, `#btn-toggle-studio-panel`.

- [ ] **Step 1: Cập nhật Topbar với logo Studio, Tab Bar và Nút Chuyển Theme**
Thay thế thanh topbar cũ bằng `.studio-topbar`, tích hợp nút `#theme-toggle-btn` (☀️/🌙).

- [ ] **Step 2: Tạo cấu trúc 3 cột trong `.studio-body`**
Đưa các section tab vào `#panel-canvas` ở giữa. Tạo `#panel-sources` bên trái và `#panel-studio` bên phải.

- [ ] **Step 3: Kiểm tra build**
Chạy: `node scripts/build.js` tại `cloudflare/pages`
Kỳ vọng: PASS

- [ ] **Step 4: Commit**
```bash
git add cloudflare/pages/src/index.html
git commit -m "feat(html): restructure app shell to 3-column Studio layout"
```

---

### Task 4: Xử Lý Logic Theme Switcher & Đồng Bộ Nguồn Môn Học trong `app.js`

**Files:**
- Modify: `cloudflare/pages/src/js/app.js`

**Interfaces:**
- Consumes: `coursesApi.list()`, `filesApi.list()`, LocalStorage.
- Produces: Hàm `initTheme()`, `toggleTheme()`, `initStudioLayout()`, `initGlobalSourcesPanel()`.

- [ ] **Step 1: Viết hàm quản lý Theme Dark / Light**
Đọc và áp dụng theme từ `localStorage.getItem('ths_theme') || 'dark'`. Gắn sự kiện click cho `#theme-toggle-btn` để chuyển đổi và lưu theme.

- [ ] **Step 2: Viết hàm đóng / mở Cột 3 (Studio Panel Drawer)**
Gắn sự kiện click cho `#btn-toggle-studio-panel` để toggle class `.collapsed` trên `#panel-studio`.

- [ ] **Step 3: Viết hàm nạp danh sách Môn học & Nguồn vào Cột Trái**
Nạp các môn học vào `#global-course-select`. Khi người dùng đổi môn, tự động nạp danh sách file vào `#panel-sources-list` và đồng bộ ngữ cảnh cho các tab.

- [ ] **Step 4: Kiểm tra build**
Chạy: `node scripts/build.js` tại `cloudflare/pages`
Kỳ vọng: PASS

- [ ] **Step 5: Commit**
```bash
git add cloudflare/pages/src/js/app.js
git commit -m "feat(js): implement theme switcher, studio panel collapse and global sources loader"
```

---

### Task 5: Kết Nối Cột Studio & Đồng Bộ Tương Tác Giữa Các Tab

**Files:**
- Modify: `cloudflare/pages/src/js/pages/chat.js`
- Modify: `cloudflare/pages/src/js/pages/study_hub.js`

**Interfaces:**
- Consumes: Cột Sources (checkbox chọn nguồn), Cột Studio (các nút hành động Quiz/Tóm tắt/Đề cương).
- Produces: Tự động truyền nguồn đã tick ở Cột Trái vào payload gửi tin nhắn chat; tự động kích hoạt tạo Quiz/Tóm tắt từ Cột Phải.

- [ ] **Step 1: Kết nối checkbox nguồn ở Cột Trái với Chat AI**
Trong `chat.js`, liên kết danh sách `_selectedSources` với các checkbox trên `#panel-sources-list` để người dùng tick chọn nguồn ngay ở cột trái.

- [ ] **Step 2: Kết nối các nút Quick Action ở Cột Phải**
Trong `study_hub.js` hoặc `app.js`, gắn sự kiện cho `#studio-action-quiz`, `#studio-action-summary`, `#studio-action-outline`: khi bấm sẽ kích hoạt Quick Research hoặc điều hướng đến bài tập trắc nghiệm của môn đang chọn.

- [ ] **Step 3: Kiểm tra build**
Chạy: `node scripts/build.js` tại `cloudflare/pages`
Kỳ vọng: PASS

- [ ] **Step 4: Commit**
```bash
git add cloudflare/pages/src/js/pages/chat.js cloudflare/pages/src/js/pages/study_hub.js
git commit -m "feat(js): connect sources checkboxes and studio quick actions across tabs"
```

---

### Task 6: Kiểm Thử Toàn Diện, Nghiệm Thu & Triển Khai Cloudflare Pages

**Files:**
- Modify: `cloudflare/pages/dist/*` (thông qua build)

**Interfaces:**
- Consumes: Toàn bộ code frontend đã hoàn thiện.
- Produces: Bản build production đã triển khai trên `https://ths-organizer.pages.dev`.

- [ ] **Step 1: Chạy build production**
Chạy: `node scripts/build.js` tại `cloudflare/pages`
Kỳ vọng: Toàn bộ các file HTML, CSS, JS được sao chép và đóng gói vào `dist/` thành công.

- [ ] **Step 2: Chạy kiểm thử toàn bộ Backend Unit Tests**
Chạy: `python -m pytest tests/`
Kỳ vọng: 80 / 80 tests PASS (100% không suy suyển).

- [ ] **Step 3: Deploy lên Cloudflare Pages**
Chạy: `npx wrangler pages deploy dist --project-name=ths-organizer --commit-dirty=true`
Kỳ vọng: Deploy thành công, trả về URL production.

- [ ] **Step 4: Commit và Push**
```bash
git push origin main
```
