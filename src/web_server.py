"""Web Dashboard Server cho ThacSi HTTT Auto Organizer.

Giao diện quản lý hiện đại theo phong cách Google AI Studio / Glassmorphism:
- Bảng điều khiển thống kê trực quan
- Danh sách tài liệu trong SQLite & liên kết Google Drive
- Tính năng "Sửa tay" (Manual Edit) Môn học & Loại tài liệu
- Bật/tắt các định dạng hỗ trợ (PDF, DOCX, PPTX, JPG, PNG...)
- Quét lại thư mục theo yêu cầu và xem Live Logs
"""

import http.server
import json
import logging
from pathlib import Path
import socketserver
import threading
import urllib.parse
from typing import Any, Dict, List, Optional

from src.database import Database
from src.drive import DriveManager
from src.extractors import extract_text, ExtractionError

logger = logging.getLogger("ThsAutoOrganizer.web")


def get_html_dashboard() -> str:
    """Trả về mã nguồn giao diện HTML/CSS/JS phong cách Google AI Studio."""
    return """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ThsAutoOrganizer Studio – Quản Lý Tài Liệu ThS HTTT</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-base: #0a0c14;
      --bg-surface: rgba(18, 22, 34, 0.75);
      --bg-card: rgba(23, 28, 44, 0.65);
      --bg-card-hover: rgba(32, 39, 61, 0.85);
      --border-color: rgba(255, 255, 255, 0.08);
      --border-focus: rgba(0, 242, 254, 0.4);
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      
      --accent-blue: #1a73e8;
      --accent-cyan: #00f2fe;
      --accent-purple: #8b5cf6;
      --accent-pink: #ec4899;
      --accent-green: #10b981;
      --accent-amber: #f59e0b;
      --accent-red: #ef4444;

      --grad-studio: linear-gradient(135deg, #1a73e8 0%, #8b5cf6 50%, #00f2fe 100%);
      --grad-glow: radial-gradient(circle at 50% 0%, rgba(139, 92, 246, 0.15), transparent 70%);
      --radius-sm: 8px;
      --radius-md: 12px;
      --radius-lg: 18px;
      --radius-full: 9999px;
      --shadow-glass: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
      --shadow-glow: 0 0 25px rgba(0, 242, 254, 0.15);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg-base);
      background-image: var(--grad-glow);
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overflow-x: hidden;
    }

    /* Scrollbar Styling */
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: var(--bg-base); }
    ::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.15); border-radius: var(--radius-full); }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.25); }

    /* Top Navigation Bar */
    header {
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-color);
      padding: 14px 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
      text-decoration: none;
      color: inherit;
    }
    .brand-icon {
      width: 38px;
      height: 38px;
      border-radius: var(--radius-md);
      background: var(--grad-studio);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 16px rgba(0, 242, 254, 0.4);
    }
    .brand-icon svg { width: 22px; height: 22px; fill: white; }
    .brand-title {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-weight: 800;
      font-size: 1.15rem;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .badge-studio {
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      padding: 2px 8px;
      background: linear-gradient(135deg, rgba(26, 115, 232, 0.25), rgba(139, 92, 246, 0.25));
      border: 1px solid rgba(0, 242, 254, 0.3);
      color: var(--accent-cyan);
      border-radius: var(--radius-full);
      font-weight: 700;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .status-pill {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-full);
      font-size: 0.8rem;
      color: var(--text-muted);
    }
    .pulse-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent-green);
      box-shadow: 0 0 8px var(--accent-green);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.85); }
    }

    .btn {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 16px;
      font-size: 0.85rem;
      font-weight: 600;
      border-radius: var(--radius-md);
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      border: 1px solid transparent;
      outline: none;
      font-family: inherit;
    }
    .btn-primary {
      background: var(--grad-studio);
      color: #ffffff;
      box-shadow: 0 2px 12px rgba(26, 115, 232, 0.3);
    }
    .btn-primary:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 20px rgba(0, 242, 254, 0.45);
    }
    .btn-secondary {
      background: rgba(255, 255, 255, 0.05);
      color: var(--text-main);
      border-color: var(--border-color);
    }
    .btn-secondary:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(255, 255, 255, 0.2);
    }

    /* Main Container */
    main {
      flex: 1;
      max-width: 1400px;
      width: 100%;
      margin: 0 auto;
      padding: 28px 24px;
      display: flex;
      flex-direction: column;
      gap: 24px;
    }

    /* Stats Grid */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
    }
    .stat-card {
      background: var(--bg-card);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 20px 22px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      position: relative;
      overflow: hidden;
      transition: all 0.3s ease;
    }
    .stat-card:hover {
      background: var(--bg-card-hover);
      border-color: rgba(255, 255, 255, 0.15);
      transform: translateY(-2px);
      box-shadow: var(--shadow-glass);
    }
    .stat-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 2px;
      background: var(--grad-studio);
      opacity: 0.6;
    }
    .stat-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: var(--text-muted);
      font-size: 0.85rem;
      font-weight: 500;
    }
    .stat-icon-wrapper {
      width: 34px;
      height: 34px;
      border-radius: var(--radius-sm);
      background: rgba(255, 255, 255, 0.04);
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--accent-cyan);
    }
    .stat-value {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 1.9rem;
      font-weight: 800;
      color: var(--text-main);
      letter-spacing: -0.03em;
    }
    .stat-subtitle {
      font-size: 0.78rem;
      color: var(--text-dim);
    }

    /* Filter & Controls Toolbar */
    .toolbar-card {
      background: var(--bg-card);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 16px 20px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
    }
    .search-box {
      display: flex;
      align-items: center;
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 8px 14px;
      gap: 10px;
      min-width: 280px;
      flex: 1;
      transition: border-color 0.2s;
    }
    .search-box:focus-within {
      border-color: var(--accent-cyan);
      box-shadow: 0 0 0 1px var(--accent-cyan);
    }
    .search-box input {
      background: transparent;
      border: none;
      color: var(--text-main);
      font-size: 0.88rem;
      width: 100%;
      outline: none;
      font-family: inherit;
    }
    .search-box input::placeholder { color: var(--text-dim); }

    .filters-group {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    select.filter-select {
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 8px 14px;
      border-radius: var(--radius-md);
      font-size: 0.85rem;
      outline: none;
      cursor: pointer;
      font-family: inherit;
    }
    select.filter-select:focus {
      border-color: var(--accent-cyan);
    }

    /* Table Container */
    .table-container {
      background: var(--bg-card);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      overflow: hidden;
      box-shadow: var(--shadow-glass);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.88rem;
    }
    th {
      background: rgba(255, 255, 255, 0.02);
      padding: 14px 18px;
      font-weight: 600;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border-color);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    td {
      padding: 14px 18px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      color: var(--text-main);
      vertical-align: middle;
    }
    tr:hover td {
      background: rgba(255, 255, 255, 0.02);
    }

    .file-name-cell {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .ext-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      font-weight: 700;
      padding: 4px 8px;
      border-radius: var(--radius-sm);
      text-transform: uppercase;
    }
    .ext-pdf { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .ext-docx { background: rgba(26, 115, 232, 0.15); color: #60a5fa; border: 1px solid rgba(26, 115, 232, 0.3); }
    .ext-pptx { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .ext-img { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .ext-txt { background: rgba(139, 92, 246, 0.15); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.3); }

    .file-info {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .file-title {
      font-weight: 600;
      color: #ffffff;
    }
    .file-path {
      font-size: 0.75rem;
      color: var(--text-dim);
      font-family: 'JetBrains Mono', monospace;
    }

    .tag-subject {
      display: inline-block;
      padding: 4px 10px;
      border-radius: var(--radius-full);
      font-size: 0.78rem;
      font-weight: 500;
      background: rgba(139, 92, 246, 0.12);
      color: #c084fc;
      border: 1px solid rgba(139, 92, 246, 0.25);
    }
    .tag-type {
      display: inline-block;
      padding: 4px 10px;
      border-radius: var(--radius-full);
      font-size: 0.78rem;
      font-weight: 500;
      background: rgba(0, 242, 254, 0.1);
      color: #38bdf8;
      border: 1px solid rgba(0, 242, 254, 0.25);
    }

    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: var(--radius-full);
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .status-uploaded {
      background: rgba(16, 185, 129, 0.15);
      color: var(--accent-green);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .status-duplicate {
      background: rgba(245, 158, 11, 0.15);
      color: var(--accent-amber);
      border: 1px solid rgba(245, 158, 11, 0.3);
    }
    .status-error {
      background: rgba(239, 68, 68, 0.15);
      color: var(--accent-red);
      border: 1px solid rgba(239, 68, 68, 0.3);
    }

    .hash-code {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      color: var(--text-dim);
      background: rgba(0, 0, 0, 0.25);
      padding: 2px 6px;
      border-radius: var(--radius-sm);
      cursor: pointer;
    }
    .hash-code:hover { color: var(--accent-cyan); }

    .action-btn-group {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .btn-icon {
      padding: 6px 10px;
      border-radius: var(--radius-sm);
      font-size: 0.78rem;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      text-decoration: none;
      transition: all 0.15s;
    }
    .btn-icon:hover {
      background: rgba(255, 255, 255, 0.12);
      color: var(--text-main);
      border-color: rgba(255, 255, 255, 0.2);
    }
    .btn-icon-drive {
      color: #60a5fa;
      border-color: rgba(96, 165, 250, 0.3);
    }
    .btn-icon-drive:hover {
      background: rgba(96, 165, 250, 0.2);
    }

    /* Modal Styling */
    .modal-backdrop {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      backdrop-filter: blur(12px);
      z-index: 1000;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .modal-box {
      background: #131724;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: var(--radius-lg);
      width: 100%;
      max-width: 520px;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
      overflow: hidden;
      animation: modalSlide 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    @keyframes modalSlide {
      from { opacity: 0; transform: scale(0.95) translateY(10px); }
      to { opacity: 1; transform: scale(1) translateY(0); }
    }
    .modal-header {
      padding: 18px 24px;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .modal-title {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 1.1rem;
      font-weight: 700;
    }
    .modal-close {
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 1.2rem;
    }
    .modal-body {
      padding: 22px 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .form-group {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .form-label {
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-muted);
    }
    .form-control {
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 10px 14px;
      border-radius: var(--radius-md);
      font-size: 0.88rem;
      outline: none;
      font-family: inherit;
    }
    .form-control:focus { border-color: var(--accent-cyan); }
    .modal-footer {
      padding: 16px 24px;
      border-top: 1px solid var(--border-color);
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      background: rgba(255, 255, 255, 0.01);
    }

    /* Logs Drawer */
    .drawer-backdrop {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.5);
      backdrop-filter: blur(8px);
      z-index: 900;
      display: none;
    }
    .drawer-panel {
      position: fixed;
      bottom: 0; left: 0; right: 0;
      height: 420px;
      background: #0d101a;
      border-top: 1px solid rgba(0, 242, 254, 0.3);
      z-index: 901;
      display: none;
      flex-direction: column;
      box-shadow: 0 -10px 40px rgba(0,0,0,0.7);
    }
    .drawer-header {
      padding: 12px 24px;
      background: rgba(255, 255, 255, 0.02);
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .log-terminal {
      flex: 1;
      padding: 16px 24px;
      overflow-y: auto;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.78rem;
      line-height: 1.6;
      color: #94a3b8;
      background: #080a10;
    }
    .log-line-info { color: #38bdf8; }
    .log-line-warn { color: #fbbf24; }
    .log-line-err { color: #f87171; }

    /* Toast Notification */
    .toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      padding: 12px 20px;
      background: #1a1e2d;
      border: 1px solid rgba(0, 242, 254, 0.4);
      color: #ffffff;
      border-radius: var(--radius-md);
      font-size: 0.85rem;
      box-shadow: var(--shadow-glass);
      z-index: 2000;
      display: none;
      animation: fadeIn 0.2s ease;
    }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  </style>
</head>
<body>

  <!-- Top Navigation Bar -->
  <header>
    <a href="#" class="brand">
      <div class="brand-icon">
        <svg viewBox="0 0 24 24"><path d="M12 2L1 21h22L12 2zm0 3.84L19.53 19H4.47L12 5.84zM11 10h2v4h-2zm0 6h2v2h-2z"/></svg>
      </div>
      <div>
        <div class="brand-title">
          ThsAutoOrganizer
          <span class="badge-studio">Studio Edition</span>
        </div>
      </div>
    </a>

    <div class="header-actions">
      <div class="status-pill">
        <div class="pulse-dot"></div>
        <span id="driveStatusText">Google Drive: Đã kết nối</span>
      </div>
      <button class="btn btn-secondary" onclick="openSettingsModal()">⚙️ Cài đặt</button>
      <button class="btn btn-secondary" onclick="toggleLogsDrawer()">📜 Live Logs</button>
      <button class="btn btn-primary" onclick="triggerScan()" id="btnScan">⚡ Quét lại ngay</button>
    </div>
  </header>

  <!-- Main Content -->
  <main>
    <!-- Stats Row -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-header">
          <span>Tổng tài liệu đã quét</span>
          <div class="stat-icon-wrapper">📁</div>
        </div>
        <div class="stat-value" id="statTotalFiles">0</div>
        <div class="stat-subtitle" id="statStorageSize">Theo dõi tại: H:\\2026\\Thac Sy\\Mon_Hoc</div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span>Đồng bộ Google Drive</span>
          <div class="stat-icon-wrapper" style="color: var(--accent-green);">☁️</div>
        </div>
        <div class="stat-value" id="statUploaded" style="color: var(--accent-green);">0</div>
        <div class="stat-subtitle">Thư mục gốc: ThacSi_HTTT</div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span>Trùng lặp (Deduplicated)</span>
          <div class="stat-icon-wrapper" style="color: var(--accent-amber);">🛡️</div>
        </div>
        <div class="stat-value" id="statDuplicates" style="color: var(--accent-amber);">0</div>
        <div class="stat-subtitle">Bảo vệ bằng mã băm SHA-256</div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span>Môn học đang theo dõi</span>
          <div class="stat-icon-wrapper" style="color: var(--accent-purple);">🎓</div>
        </div>
        <div class="stat-value" id="statSubjectsCount" style="color: var(--accent-purple);">0</div>
        <div class="stat-subtitle" id="statSubjectsList">Toán KH Dữ liệu, Triết học...</div>
      </div>
    </div>

    <!-- Filter & Search Toolbar -->
    <div class="toolbar-card">
      <div class="search-box">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
        <input type="text" id="searchInput" placeholder="Tìm kiếm tài liệu theo tên, đường dẫn, hash..." oninput="applyFilters()">
      </div>

      <div class="filters-group">
        <select class="filter-select" id="filterSubject" onchange="applyFilters()">
          <option value="">Tất cả môn học</option>
        </select>

        <select class="filter-select" id="filterType" onchange="applyFilters()">
          <option value="">Tất cả loại tài liệu</option>
          <option value="Giáo trình">Giáo trình</option>
          <option value="Slide">Slide</option>
          <option value="Ôn thi">Ôn thi</option>
          <option value="Tài liệu tham khảo">Tài liệu tham khảo</option>
        </select>

        <select class="filter-select" id="filterStatus" onchange="applyFilters()">
          <option value="">Tất cả trạng thái</option>
          <option value="UPLOADED">Đã upload Drive</option>
          <option value="DUPLICATE">Trùng lặp</option>
          <option value="ERROR">Lỗi</option>
        </select>
      </div>
    </div>

    <!-- Data Table -->
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Tập tin tài liệu</th>
            <th>Môn học</th>
            <th>Phân loại</th>
            <th>SHA-256 / Cập nhật</th>
            <th>Trạng thái</th>
            <th style="text-align: right;">Thao tác</th>
          </tr>
        </thead>
        <tbody id="filesTableBody">
          <tr>
            <td colspan="6" style="text-align: center; color: var(--text-dim); padding: 36px;">
              Đang tải dữ liệu tài liệu...
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </main>

  <!-- Modal: Sửa tay phân loại -->
  <div class="modal-backdrop" id="editModal">
    <div class="modal-box">
      <div class="modal-header">
        <div class="modal-title">✏️ Sửa tay phân loại tài liệu</div>
        <button class="modal-close" onclick="closeEditModal()">&times;</button>
      </div>
      <div class="modal-body">
        <input type="hidden" id="editRecordId">
        <div class="form-group">
          <label class="form-label">Tên file:</label>
          <div id="editFileName" style="font-weight: 600; color: #ffffff; font-size: 0.88rem; word-break: break-all;"></div>
        </div>

        <div class="form-group">
          <label class="form-label">Môn học (Subject):</label>
          <input type="text" id="editSubject" class="form-control" list="subjectOptions" placeholder="Nhập hoặc chọn môn học...">
          <datalist id="subjectOptions">
            <option value="Toán khoa học dữ liệu">
            <option value="Triết học">
            <option value="Phương pháp ghi chú">
            <option value="Cơ sở dữ liệu">
            <option value="Phương pháp nghiên cứu">
          </datalist>
        </div>

        <div class="form-group">
          <label class="form-label">Loại tài liệu (Document Type):</label>
          <select id="editDocumentType" class="form-control">
            <option value="Giáo trình">Giáo trình</option>
            <option value="Slide">Slide</option>
            <option value="Ôn thi">Ôn thi</option>
            <option value="Tài liệu tham khảo">Tài liệu tham khảo</option>
            <option value="Tài liệu chung">Tài liệu chung</option>
          </select>
        </div>

        <div style="font-size: 0.78rem; color: var(--text-dim); background: rgba(0,242,254,0.05); padding: 10px; border-radius: 8px; border: 1px solid rgba(0,242,254,0.15);">
          💡 Khi bạn bấm <b>Lưu phân loại</b>, hệ thống sẽ cập nhật ngay vào SQLite và tự động tạo thư mục tương ứng trên Google Drive!
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="closeEditModal()">Hủy</button>
        <button class="btn btn-primary" onclick="submitEditClassification()">💾 Lưu phân loại</button>
      </div>
    </div>
  </div>

  <!-- Modal: Cài đặt cấu hình -->
  <div class="modal-backdrop" id="settingsModal">
    <div class="modal-box">
      <div class="modal-header">
        <div class="modal-title">⚙️ Cài đặt hệ thống</div>
        <button class="modal-close" onclick="closeSettingsModal()">&times;</button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label class="form-label">Thư mục nguồn (Source of Truth):</label>
          <input type="text" id="cfgRootFolder" class="form-control">
        </div>

        <div class="form-group">
          <label class="form-label">Định dạng file được theo dõi:</label>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 0.82rem;">
            <label><input type="checkbox" id="extPdf" value=".pdf"> .pdf (Tài liệu PDF)</label>
            <label><input type="checkbox" id="extDocx" value=".docx"> .docx (Word)</label>
            <label><input type="checkbox" id="extPptx" value=".pptx"> .pptx (PowerPoint)</label>
            <label><input type="checkbox" id="extTxt" value=".txt"> .txt (Plain text)</label>
            <label><input type="checkbox" id="extMd" value=".md"> .md (Markdown)</label>
            <label><input type="checkbox" id="extJpg" value=".jpg"> .jpg (Ảnh ghi chú)</label>
            <label><input type="checkbox" id="extJpeg" value=".jpeg"> .jpeg (Ảnh ghi chú)</label>
            <label><input type="checkbox" id="extPng" value=".png"> .png (Ảnh chụp bài)</label>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Thời gian chờ file ổn định (giây):</label>
          <input type="number" id="cfgWaitSecs" class="form-control" min="1" max="30">
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="closeSettingsModal()">Đóng</button>
        <button class="btn btn-primary" onclick="saveSettings()">💾 Lưu cấu hình</button>
      </div>
    </div>
  </div>

  <!-- Drawer: Live Logs -->
  <div class="drawer-backdrop" id="drawerBackdrop" onclick="toggleLogsDrawer()"></div>
  <div class="drawer-panel" id="logsDrawer">
    <div class="drawer-header">
      <div style="font-weight: 700; font-size: 0.9rem; display: flex; align-items: center; gap: 8px;">
        <span class="pulse-dot"></span> Nhật ký hệ thống trực tiếp (Live App Logs)
      </div>
      <div style="display: flex; gap: 8px;">
        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.75rem;" onclick="fetchLogs()">🔄 Làm mới</button>
        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.75rem;" onclick="toggleLogsDrawer()">✕ Đóng</button>
      </div>
    </div>
    <div class="log-terminal" id="logTerminal">
      Đang tải log...
    </div>
  </div>

  <!-- Toast Notification -->
  <div class="toast" id="toastMsg"></div>

  <script>
    let allFiles = [];

    function showToast(msg) {
      const t = document.getElementById('toastMsg');
      t.textContent = msg;
      t.style.display = 'block';
      setTimeout(() => { t.style.display = 'none'; }, 3000);
    }

    function getExtBadge(name) {
      const ext = name.split('.').pop().toLowerCase();
      if (ext === 'pdf') return `<span class="ext-badge ext-pdf">PDF</span>`;
      if (ext === 'docx' || ext === 'doc') return `<span class="ext-badge ext-docx">DOCX</span>`;
      if (ext === 'pptx' || ext === 'ppt') return `<span class="ext-badge ext-pptx">PPTX</span>`;
      if (['jpg', 'jpeg', 'png'].includes(ext)) return `<span class="ext-badge ext-img">IMG</span>`;
      return `<span class="ext-badge ext-txt">${ext.toUpperCase()}</span>`;
    }

    async function loadStats() {
      try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        document.getElementById('statTotalFiles').textContent = data.total_files || 0;
        document.getElementById('statUploaded').textContent = data.uploaded_files || 0;
        document.getElementById('statDuplicates').textContent = data.duplicate_files || 0;
        document.getElementById('statSubjectsCount').textContent = data.subjects_count || 0;
        if (data.subjects && data.subjects.length > 0) {
          document.getElementById('statSubjectsList').textContent = data.subjects.join(', ');
          
          // Cập nhật filterSubject dropdown
          const fSub = document.getElementById('filterSubject');
          const curVal = fSub.value;
          fSub.innerHTML = '<option value="">Tất cả môn học</option>';
          data.subjects.forEach(s => {
            fSub.innerHTML += `<option value="${s}">${s}</option>`;
          });
          fSub.value = curVal;
        }
      } catch (err) {
        console.error('Lỗi tải stats:', err);
      }
    }

    async function loadFiles() {
      try {
        const res = await fetch('/api/files');
        allFiles = await res.json();
        renderTable(allFiles);
      } catch (err) {
        console.error('Lỗi tải files:', err);
      }
    }

    function renderTable(files) {
      const tbody = document.getElementById('filesTableBody');
      if (!files || files.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-dim); padding: 36px;">Không tìm thấy tài liệu nào phù hợp.</td></tr>`;
        return;
      }

      let html = '';
      files.forEach(f => {
        const fileName = f.path.split(/[\\\\/]/).pop();
        let statusBadge = '';
        if (f.status === 'UPLOADED') {
          statusBadge = `<span class="status-badge status-uploaded">● ĐÃ UPLOAD</span>`;
        } else if (f.status === 'DUPLICATE') {
          statusBadge = `<span class="status-badge status-duplicate">● TRÙNG LẶP</span>`;
        } else if (f.status === 'ERROR') {
          statusBadge = `<span class="status-badge status-error" title="${f.error || ''}">● LỖI</span>`;
        } else {
          statusBadge = `<span class="status-badge">${f.status}</span>`;
        }

        const driveBtn = f.drive_file_id 
          ? `<a href="https://drive.google.com/file/d/${f.drive_file_id}/view" target="_blank" class="btn-icon btn-icon-drive" title="Mở trên Google Drive">🔗 Drive</a>`
          : '';

        const shortHash = f.sha256 ? f.sha256.substring(0, 10) + '...' : '-';

        html += `
          <tr>
            <td>
              <div class="file-name-cell">
                ${getExtBadge(fileName)}
                <div class="file-info">
                  <div class="file-title">${fileName}</div>
                  <div class="file-path">${f.path}</div>
                </div>
              </div>
            </td>
            <td><span class="tag-subject">${f.subject || 'Chưa phân loại'}</span></td>
            <td><span class="tag-type">${f.document_type || 'Chung'}</span></td>
            <td>
              <span class="hash-code" title="${f.sha256 || ''}" onclick="navigator.clipboard.writeText('${f.sha256 || ''}'); showToast('Đã copy SHA-256!');">${shortHash}</span>
            </td>
            <td>${statusBadge}</td>
            <td style="text-align: right;">
              <div class="action-btn-group" style="justify-content: flex-end;">
                ${driveBtn}
                <button class="btn-icon" onclick="openEditModal(${f.id}, '${encodeURIComponent(fileName)}', '${encodeURIComponent(f.subject || '')}', '${encodeURIComponent(f.document_type || '')}')">✏️ Sửa tay</button>
              </div>
            </td>
          </tr>
        `;
      });
      tbody.innerHTML = html;
    }

    function applyFilters() {
      const q = document.getElementById('searchInput').value.toLowerCase();
      const s = document.getElementById('filterSubject').value;
      const t = document.getElementById('filterType').value;
      const st = document.getElementById('filterStatus').value;

      const filtered = allFiles.filter(f => {
        const matchQ = !q || f.path.toLowerCase().includes(q) || (f.sha256 && f.sha256.toLowerCase().includes(q));
        const matchS = !s || f.subject === s;
        const matchT = !t || f.document_type === t;
        const matchSt = !st || f.status === st;
        return matchQ && matchS && matchT && matchSt;
      });

      renderTable(filtered);
    }

    function openEditModal(id, encName, encSub, encType) {
      document.getElementById('editRecordId').value = id;
      document.getElementById('editFileName').textContent = decodeURIComponent(encName);
      document.getElementById('editSubject').value = decodeURIComponent(encSub);
      document.getElementById('editDocumentType').value = decodeURIComponent(encType) || 'Tài liệu tham khảo';
      document.getElementById('editModal').style.display = 'flex';
    }

    function closeEditModal() {
      document.getElementById('editModal').style.display = 'none';
    }

    async function submitEditClassification() {
      const id = document.getElementById('editRecordId').value;
      const subject = document.getElementById('editSubject').value.trim();
      const docType = document.getElementById('editDocumentType').value;

      if (!subject) {
        alert('Vui lòng nhập hoặc chọn môn học!');
        return;
      }

      try {
        const res = await fetch('/api/files/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: parseInt(id), subject: subject, document_type: docType })
        });
        const result = await res.json();
        if (result.ok) {
          showToast('✅ Đã cập nhật phân loại và đồng bộ Drive!');
          closeEditModal();
          loadStats();
          loadFiles();
        } else {
          alert('Lỗi: ' + (result.error || 'Không rõ'));
        }
      } catch (err) {
        alert('Lỗi mạng khi lưu: ' + err);
      }
    }

    async function triggerScan() {
      const btn = document.getElementById('btnScan');
      btn.textContent = '⏳ Đang quét...';
      btn.disabled = true;
      try {
        const res = await fetch('/api/scan', { method: 'POST' });
        const data = await res.json();
        showToast('🚀 Đã kích hoạt quét! Tìm thấy ' + (data.count || 0) + ' file.');
        setTimeout(() => {
          loadStats();
          loadFiles();
          btn.textContent = '⚡ Quét lại ngay';
          btn.disabled = false;
        }, 1500);
      } catch (err) {
        showToast('Lỗi khi kích hoạt quét');
        btn.textContent = '⚡ Quét lại ngay';
        btn.disabled = false;
      }
    }

    async function openSettingsModal() {
      try {
        const res = await fetch('/api/config');
        const cfg = await res.json();
        document.getElementById('cfgRootFolder').value = cfg.root_folder || '';
        document.getElementById('cfgWaitSecs').value = cfg.stable_file_wait_seconds || 3;
        
        const exts = cfg.supported_extensions || [];
        ['.pdf', '.docx', '.pptx', '.txt', '.md', '.jpg', '.jpeg', '.png'].forEach(ext => {
          const el = document.querySelector(`input[value="${ext}"]`);
          if (el) el.checked = exts.includes(ext);
        });

        document.getElementById('settingsModal').style.display = 'flex';
      } catch (err) {
        alert('Lỗi tải cấu hình: ' + err);
      }
    }

    function closeSettingsModal() {
      document.getElementById('settingsModal').style.display = 'none';
    }

    async function saveSettings() {
      const rootFolder = document.getElementById('cfgRootFolder').value.trim();
      const waitSecs = parseInt(document.getElementById('cfgWaitSecs').value) || 3;
      
      const exts = [];
      document.querySelectorAll('input[type="checkbox"]:checked').forEach(c => exts.push(c.value));

      try {
        const res = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            root_folder: rootFolder,
            stable_file_wait_seconds: waitSecs,
            supported_extensions: exts
          })
        });
        const data = await res.json();
        if (data.ok) {
          showToast('✅ Đã lưu cấu hình mới!');
          closeSettingsModal();
          loadStats();
        } else {
          alert('Lỗi lưu: ' + data.error);
        }
      } catch (err) {
        alert('Lỗi lưu cấu hình: ' + err);
      }
    }

    function toggleLogsDrawer() {
      const drawer = document.getElementById('logsDrawer');
      const backdrop = document.getElementById('drawerBackdrop');
      const isVisible = drawer.style.display === 'flex';
      if (isVisible) {
        drawer.style.display = 'none';
        backdrop.style.display = 'none';
      } else {
        drawer.style.display = 'flex';
        backdrop.style.display = 'block';
        fetchLogs();
      }
    }

    async function fetchLogs() {
      const el = document.getElementById('logTerminal');
      try {
        const res = await fetch('/api/logs');
        const text = await res.text();
        const lines = text.split('\\n');
        el.innerHTML = lines.map(line => {
          if (line.includes('| ERROR |') || line.includes('ERR')) return `<div class="log-line-err">${line}</div>`;
          if (line.includes('| WARNING |') || line.includes('WARN')) return `<div class="log-line-warn">${line}</div>`;
          return `<div class="log-line-info">${line}</div>`;
        }).join('');
        el.scrollTop = el.scrollHeight;
      } catch (err) {
        el.textContent = 'Lỗi tải log: ' + err;
      }
    }

    // Auto-refresh periodically
    setInterval(() => {
      loadStats();
      loadFiles();
    }, 10000);

    // Initial load
    window.addEventListener('DOMContentLoaded', () => {
      loadStats();
      loadFiles();
    });
  </script>
</body>
</html>
"""


class DashboardRequestHandler(http.server.BaseHTTPRequestHandler):
    """Handler xử lý API và giao diện Web Dashboard."""

    database: Optional[Database] = None
    drive_manager: Optional[DriveManager] = None
    config_path: Path = Path("config.json")
    scan_callback: Optional[Any] = None

    def log_message(self, format: str, *args: Any) -> None:
        # Tắt bớt log HTTP mặc định trên console để không làm rối terminal
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path in ["/", "/index.html"]:
            content = get_html_dashboard().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/api/stats":
            if not self.database:
                self._send_json({"error": "Database not initialized"}, 500)
                return

            records = self.database.get_all_records(limit=1000)
            total = len(records)
            uploaded = sum(1 for r in records if r.get("status") == "UPLOADED")
            duplicate = sum(1 for r in records if r.get("status") == "DUPLICATE")
            error = sum(1 for r in records if r.get("status") == "ERROR")

            subjects = sorted(list({r["subject"] for r in records if r.get("subject")}))

            self._send_json({
                "total_files": total,
                "uploaded_files": uploaded,
                "duplicate_files": duplicate,
                "error_files": error,
                "subjects_count": len(subjects),
                "subjects": subjects,
                "drive_connected": self.drive_manager.is_configured() if self.drive_manager else False,
            })
            return

        if path == "/api/files":
            if not self.database:
                self._send_json([], 500)
                return
            records = self.database.get_all_records(limit=1000)
            self._send_json(records)
            return

        if path == "/api/config":
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self._send_json(cfg)
            except Exception as exc:
                self._send_json({"error": str(exc)}, 500)
            return

        if path == "/api/logs":
            log_file = Path("logs/app.log")
            if log_file.is_file():
                try:
                    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()[-150:]
                    content = "".join(lines).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception as exc:
                    err_bytes = f"Lỗi đọc log: {exc}".encode("utf-8")
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(err_bytes)
                    return

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Chua co log.")
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        content_len = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            body = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            body = {}

        if path == "/api/files/update":
            record_id = body.get("id")
            new_subject = body.get("subject", "").strip()
            new_type = body.get("document_type", "").strip()

            if not record_id or not new_subject or not new_type or not self.database:
                self._send_json({"ok": False, "error": "Tham số không hợp lệ"}, 400)
                return

            try:
                record = self.database.get_record(record_id)
                if not record:
                    self._send_json({"ok": False, "error": "Không tìm thấy file"}, 404)
                    return

                new_drive_id = record.get("drive_file_id")

                # Nếu file đã có trên Drive và DriveManager sẵn sàng, di chuyển sang thư mục mới
                if self.drive_manager and self.drive_manager.is_configured() and record.get("drive_file_id"):
                    try:
                        # 1. Tìm hoặc tạo cây thư mục mới
                        target_folder_id = self.drive_manager.resolve_folder_hierarchy(
                            subject=new_subject,
                            document_type=new_type,
                        )
                        # 2. Cập nhật vị trí cha của file trên Drive
                        service = self.drive_manager.get_service()
                        file_meta = service.files().get(
                            fileId=record["drive_file_id"],
                            fields="parents",
                        ).execute()
                        previous_parents = ",".join(file_meta.get("parents", []))

                        service.files().update(
                            fileId=record["drive_file_id"],
                            addParents=target_folder_id,
                            removeParents=previous_parents,
                            fields="id, parents",
                        ).execute()
                        logger.info("Đã di chuyển file Drive '%s' sang folder '%s'", record['path'], target_folder_id)
                    except Exception as exc:
                        logger.warning("Không thể di chuyển file Drive tự động: %s", exc)

                # Cập nhật trong SQLite
                self.database.update_classification(
                    record_id=record_id,
                    subject=new_subject,
                    document_type=new_type,
                    drive_file_id=new_drive_id,
                )
                self._send_json({"ok": True, "id": record_id})
                return
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, 500)
                return

        if path == "/api/config":
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    current_cfg = json.load(f)

                current_cfg.update(body)

                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(current_cfg, f, indent=2, ensure_ascii=False)

                self._send_json({"ok": True})
                return
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, 500)
                return

        if path == "/api/scan":
            count = 0
            cb = DashboardRequestHandler.scan_callback
            if cb:
                try:
                    count = cb()
                except Exception as exc:
                    logger.error("Lỗi callback scan: %s", exc)
            self._send_json({"ok": True, "count": count})
            return

        self.send_response(404)
        self.end_headers()


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Multi-threaded HTTP Server."""
    daemon_threads = True
    allow_reuse_address = True


def start_web_server(
    port: int = 8080,
    database: Optional[Database] = None,
    drive_manager: Optional[DriveManager] = None,
    config_path: Path | str = "config.json",
    scan_callback: Optional[Any] = None,
) -> ThreadedHTTPServer:
    """Khởi động Web Dashboard Server trong một luồng riêng biệt."""
    DashboardRequestHandler.database = database
    DashboardRequestHandler.drive_manager = drive_manager
    DashboardRequestHandler.config_path = Path(config_path).resolve()
    DashboardRequestHandler.scan_callback = scan_callback

    server = ThreadedHTTPServer(("0.0.0.0", port), DashboardRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="WebDashboardServer")
    thread.start()
    logger.info("Web Dashboard Studio đang chạy tại: http://localhost:%d", port)
    return server


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)
    db = Database("data/files.db")
    db.initialize()
    dm = DriveManager()
    server = start_web_server(8080, db, dm)
    print("Dashboard started at http://localhost:8080. Press Enter to exit.")
    input()
    server.shutdown()
