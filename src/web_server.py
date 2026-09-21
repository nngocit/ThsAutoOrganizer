"""Web Dashboard Server cho ThacSi HTTT Auto Organizer.

Nền tảng Web SaaS Multi-User đa thiết bị (Máy tính, iPad, Điện thoại):
- Đăng nhập tài khoản Google riêng biệt (OAuth 2.0 Web Flow + Session Management)
- Tách biệt dữ liệu và Google Drive riêng cho từng người dùng (Multi-Tenant)
- Hỗ trợ nạp tài liệu đa nền tảng:
  + HTML5 File System Access API (trên Laptop/PC)
  + Camera chụp ảnh bài giảng trực tiếp (trên Điện thoại/Tablet)
  + Tải lên hàng loạt tệp (Drag & Drop, Multi-file picker)
- Bảng điều khiển phong cách Google AI Studio / Glassmorphism
- Nhận diện tức thì file ✨ MỚI (<24h), hiển thị thời gian tương đối
- Chế độ Thẻ (Cards Grid) & Bảng (Table View) linh hoạt
"""

import base64
import http.cookies
import http.server
import json
import logging
import os
from pathlib import Path
import secrets
import socketserver
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.classifier import PathClassifier
from src.database import Database, STATUS_UPLOADED, STATUS_SAVED_LOCAL, STATUS_DUPLICATE, STATUS_ERROR
from src.drive import DriveManager
from src.processor import calculate_sha256

logger = logging.getLogger("ThsAutoOrganizer.web")

# Bộ nhớ phiên đăng nhập (session_id -> user_dict)
SESSION_STORE: Dict[str, Dict[str, Any]] = {}


def get_html_dashboard() -> str:
    """Trả về giao diện Web Studio Responsive đa thiết bị (Desktop, iPad, Mobile)."""
    return """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>ThsAutoOrganizer Cloud Studio – Hệ Thống Quản Lý Tài Liệu Đa Thiết Bị</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-base: #080a12;
      --bg-surface: rgba(16, 20, 32, 0.85);
      --bg-card: rgba(22, 28, 46, 0.7);
      --bg-card-hover: rgba(30, 38, 62, 0.9);
      --border-color: rgba(255, 255, 255, 0.08);
      --border-focus: rgba(0, 242, 254, 0.45);
      --text-main: #f8fafc;
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
      --grad-glow: radial-gradient(ellipse at 50% -20%, rgba(26, 115, 232, 0.22), rgba(139, 92, 246, 0.14), transparent 70%);
      --grad-new: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
      
      --radius-sm: 8px;
      --radius-md: 12px;
      --radius-lg: 18px;
      --radius-full: 9999px;
      --shadow-glass: 0 8px 32px 0 rgba(0, 0, 0, 0.45);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg-base);
      background-image: var(--grad-glow);
      background-attachment: fixed;
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overflow-x: hidden;
    }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: var(--bg-base); }
    ::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.15); border-radius: var(--radius-full); }

    /* Header */
    header {
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-color);
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      text-decoration: none;
      color: inherit;
    }
    .brand-icon {
      width: 36px;
      height: 36px;
      border-radius: var(--radius-md);
      background: var(--grad-studio);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 16px rgba(0, 242, 254, 0.4);
    }
    .brand-icon svg { width: 20px; height: 20px; fill: white; }
    .brand-title {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-weight: 800;
      font-size: 1.1rem;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .badge-studio {
      font-size: 0.65rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 2px 8px;
      border-radius: var(--radius-full);
      background: rgba(0, 242, 254, 0.15);
      color: var(--accent-cyan);
      border: 1px solid rgba(0, 242, 254, 0.3);
    }

    .header-right {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    /* User Profile Chip in Header */
    .user-profile-chip {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 4px 12px 4px 4px;
      border-radius: var(--radius-full);
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-color);
      cursor: pointer;
      transition: all 0.2s;
    }
    .user-profile-chip:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(0, 242, 254, 0.3);
    }
    .user-avatar {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: var(--grad-studio);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 0.78rem;
      color: #fff;
    }
    .user-name-text {
      font-size: 0.8rem;
      font-weight: 600;
      max-width: 140px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    /* Buttons */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 8px 14px;
      border-radius: var(--radius-md);
      font-size: 0.82rem;
      font-weight: 600;
      font-family: inherit;
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      border: 1px solid transparent;
      text-decoration: none;
      white-space: nowrap;
    }
    .btn-primary {
      background: var(--grad-studio);
      color: #ffffff;
      box-shadow: 0 2px 12px rgba(0, 242, 254, 0.25);
    }
    .btn-primary:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 18px rgba(0, 242, 254, 0.4);
    }
    .btn-secondary {
      background: rgba(255, 255, 255, 0.05);
      border-color: var(--border-color);
      color: var(--text-main);
    }
    .btn-secondary:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(255, 255, 255, 0.2);
    }
    .btn-google {
      background: #ffffff;
      color: #1f2937;
      border-color: #e5e7eb;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    .btn-google:hover {
      background: #f3f4f6;
      transform: translateY(-1px);
    }

    /* Cross-Platform Quick Upload Bar */
    .upload-action-banner {
      background: linear-gradient(135deg, rgba(26, 115, 232, 0.12) 0%, rgba(139, 92, 246, 0.1) 50%, rgba(0, 242, 254, 0.08) 100%);
      border: 1px dashed rgba(0, 242, 254, 0.4);
      border-radius: var(--radius-lg);
      padding: 16px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }
    .upload-banner-text {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .upload-banner-title {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-weight: 700;
      font-size: 0.95rem;
      color: #ffffff;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .upload-banner-sub {
      font-size: 0.78rem;
      color: var(--text-muted);
    }
    .upload-btn-group {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    /* Main Container */
    main {
      flex: 1;
      max-width: 1440px;
      width: 100%;
      margin: 0 auto;
      padding: 20px 24px 48px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }

    /* Stats Grid */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }
    .stat-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 16px 20px;
      backdrop-filter: blur(16px);
      transition: all 0.2s;
    }
    .stat-card:hover {
      border-color: rgba(255, 255, 255, 0.15);
      background: var(--bg-card-hover);
    }
    .stat-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: var(--text-muted);
      font-size: 0.76rem;
      font-weight: 600;
      text-transform: uppercase;
    }
    .stat-value {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 1.9rem;
      font-weight: 800;
      margin: 8px 0 2px;
    }
    .stat-subtitle {
      font-size: 0.72rem;
      color: var(--text-dim);
    }

    /* Toolbar */
    .toolbar-container {
      display: flex;
      flex-direction: column;
      gap: 12px;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 14px 18px;
    }
    .toolbar-row-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }
    .search-box {
      flex: 1;
      min-width: 240px;
      display: flex;
      align-items: center;
      gap: 8px;
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 8px 12px;
    }
    .search-box:focus-within {
      border-color: var(--border-focus);
    }
    .search-box input {
      background: transparent;
      border: none;
      color: var(--text-main);
      font-size: 0.85rem;
      outline: none;
      width: 100%;
    }

    .filter-chips {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .chip {
      padding: 5px 12px;
      border-radius: var(--radius-full);
      font-size: 0.76rem;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .chip.active {
      background: rgba(0, 242, 254, 0.15);
      border-color: var(--accent-cyan);
      color: var(--accent-cyan);
    }
    .chip-badge {
      background: rgba(0, 0, 0, 0.35);
      padding: 1px 5px;
      border-radius: var(--radius-full);
      font-size: 0.68rem;
    }

    .toolbar-row-bottom {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
      padding-top: 10px;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
    }
    .filter-select {
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      padding: 6px 10px;
      border-radius: var(--radius-md);
      font-size: 0.78rem;
      outline: none;
    }

    .view-switcher {
      display: flex;
      align-items: center;
      background: rgba(0, 0, 0, 0.3);
      padding: 2px;
      border-radius: var(--radius-md);
      border: 1px solid var(--border-color);
    }
    .view-btn {
      padding: 5px 10px;
      border-radius: var(--radius-sm);
      border: none;
      background: transparent;
      color: var(--text-muted);
      font-size: 0.76rem;
      font-weight: 600;
      cursor: pointer;
    }
    .view-btn.active {
      background: rgba(255, 255, 255, 0.12);
      color: #ffffff;
    }

    /* BADGES */
    .badge-new {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      padding: 2px 7px;
      border-radius: var(--radius-full);
      font-size: 0.65rem;
      font-weight: 800;
      background: var(--grad-new);
      color: #031326;
      box-shadow: 0 0 10px rgba(0, 242, 254, 0.4);
    }
    .badge-drive-sync {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      padding: 2px 7px;
      border-radius: var(--radius-full);
      font-size: 0.65rem;
      font-weight: 700;
      background: rgba(16, 185, 129, 0.18);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.4);
    }

    .ext-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.68rem;
      font-weight: 700;
      padding: 3px 7px;
      border-radius: var(--radius-sm);
      text-transform: uppercase;
    }
    .ext-pdf { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .ext-docx { background: rgba(26, 115, 232, 0.15); color: #60a5fa; border: 1px solid rgba(26, 115, 232, 0.3); }
    .ext-pptx { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .ext-img { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .ext-txt { background: rgba(139, 92, 246, 0.15); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.3); }

    .tag-subject {
      display: inline-block;
      padding: 3px 8px;
      border-radius: var(--radius-full);
      font-size: 0.72rem;
      font-weight: 600;
      background: rgba(139, 92, 246, 0.14);
      color: #c084fc;
      border: 1px solid rgba(139, 92, 246, 0.3);
    }
    .tag-type {
      display: inline-block;
      padding: 3px 8px;
      border-radius: var(--radius-full);
      font-size: 0.72rem;
      font-weight: 500;
      background: rgba(0, 242, 254, 0.08);
      color: #38bdf8;
      border: 1px solid rgba(0, 242, 254, 0.25);
    }

    /* CARDS GRID */
    .cards-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 14px;
    }
    .file-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 16px;
      backdrop-filter: blur(16px);
      display: flex;
      flex-direction: column;
      gap: 10px;
      position: relative;
      overflow: hidden;
      transition: all 0.2s;
    }
    .file-card:hover {
      border-color: rgba(255, 255, 255, 0.18);
      background: var(--bg-card-hover);
      transform: translateY(-2px);
    }
    .file-card.is-new-card::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 3px;
      background: var(--grad-new);
    }
    .card-title {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 0.92rem;
      font-weight: 700;
      color: #ffffff;
      line-height: 1.35;
      word-break: break-word;
    }
    .card-path {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.7rem;
      color: var(--text-dim);
      word-break: break-all;
    }
    .card-footer {
      margin-top: auto;
      padding-top: 10px;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }

    /* TABLE */
    .table-container {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      backdrop-filter: blur(16px);
      overflow-x: auto;
      display: none;
    }
    table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
    th {
      background: rgba(255, 255, 255, 0.02);
      color: var(--text-muted);
      font-weight: 600;
      padding: 12px 16px;
      border-bottom: 1px solid var(--border-color);
      text-transform: uppercase;
      font-size: 0.7rem;
    }
    td { padding: 12px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); vertical-align: middle; }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }

    .btn-icon {
      padding: 5px 9px;
      border-radius: var(--radius-sm);
      font-size: 0.74rem;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .btn-icon:hover { background: rgba(255, 255, 255, 0.1); color: #fff; }

    /* Modals */
    .modal-backdrop {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(12px);
      z-index: 1000;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }
    .modal-box {
      background: #111522;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: var(--radius-lg);
      width: 100%;
      max-width: 480px;
      overflow: hidden;
    }
    .modal-header {
      padding: 16px 20px;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .modal-body { padding: 18px 20px; display: flex; flex-direction: column; gap: 14px; }
    .modal-footer { padding: 14px 20px; border-top: 1px solid var(--border-color); display: flex; justify-content: flex-end; gap: 8px; }
    .form-control {
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid var(--border-color);
      color: #fff;
      padding: 9px 12px;
      border-radius: var(--radius-md);
      font-size: 0.85rem;
      outline: none;
      width: 100%;
    }

    /* Toast */
    .toast {
      position: fixed;
      bottom: 20px; right: 20px;
      padding: 12px 18px;
      background: #141828;
      border: 1px solid rgba(0, 242, 254, 0.4);
      color: #ffffff;
      border-radius: var(--radius-md);
      font-size: 0.82rem;
      z-index: 2000;
      display: none;
      box-shadow: var(--shadow-glass);
    }

    /* Mobile Responsive Optimizations */
    @media (max-width: 768px) {
      header { padding: 10px 14px; }
      main { padding: 14px 14px 40px; }
      .brand-title span.badge-studio { display: none; }
      .upload-action-banner { flex-direction: column; align-items: stretch; }
      .upload-btn-group { justify-content: stretch; }
      .upload-btn-group button { flex: 1; }
      .cards-grid { grid-template-columns: 1fr; }
      .stats-grid { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>

  <!-- Top Navigation -->
  <header>
    <a href="#" class="brand">
      <div class="brand-icon">
        <svg viewBox="0 0 24 24"><path d="M12 2L1 21h22L12 2zm0 3.84L19.53 19H4.47L12 5.84zM11 10h2v4h-2zm0 6h2v2h-2z"/></svg>
      </div>
      <div class="brand-title">
        ThsAutoOrganizer
        <span class="badge-studio">Studio Edition</span>
      </div>
    </a>

    <div class="header-right">
      <!-- User Profile or Sign-in button -->
      <div id="userSection">
        <button class="btn btn-google" onclick="openLoginModal()" id="btnLoginGoogle">
          <svg width="16" height="16" viewBox="0 0 24 24"><path fill="#EA4335" d="M12 5c1.6 0 3 .6 4.1 1.6l3.1-3.1C17.3 1.7 14.8 1 12 1 7.5 1 3.7 3.6 1.9 7.3l3.7 2.9C6.5 7.3 9 5 12 5z"/><path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.6h6.5c-.3 1.5-1.1 2.8-2.4 3.7l3.7 2.9c2.2-2 3.7-5 3.7-8.9z"/><path fill="#FBBC05" d="M5.6 14.8c-.2-.7-.4-1.5-.4-2.8s.2-2.1.4-2.8L1.9 6.3C.7 8.7 0 10.3 0 12s.7 3.3 1.9 5.7l3.7-2.9z"/><path fill="#34A853" d="M12 23c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3 0-5.5-2.3-6.4-5.2L1.9 16C3.7 19.7 7.5 23 12 23z"/></svg>
          Đăng nhập Google
        </button>
      </div>

      <button class="btn btn-secondary" onclick="openSettingsModal()" title="Cài đặt">⚙️</button>
    </div>
  </header>

  <!-- Main Content -->
  <main>
    <!-- Login Prompt Banner (Hiển thị khi chưa đăng nhập) -->
    <div id="loginPromptBanner" style="display:none; background: linear-gradient(135deg, rgba(26, 115, 232, 0.18) 0%, rgba(139, 92, 246, 0.18) 100%); border: 1px solid rgba(0, 242, 254, 0.4); border-radius: var(--radius-md); padding: 18px 22px; color: #f8fafc; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 20px;">
      <div style="display: flex; align-items: center; gap: 14px;">
        <span style="font-size: 2rem;">🔒</span>
        <div>
          <div style="font-weight: 800; font-size: 1.05rem; color: #fff;">Chưa kết nối tài khoản & thư mục máy</div>
          <div style="font-size: 0.82rem; color: #cbd5e1; margin-top: 3px; max-width: 620px; line-height: 1.45;">
            Hệ thống chỉ quét và đồng bộ khi bạn đã đăng nhập đúng tài khoản Gmail và thư mục máy tính của mình. Hãy đăng nhập để bắt đầu!
          </div>
        </div>
      </div>
      <div style="display: flex; gap: 8px; flex-wrap: wrap;">
        <button class="btn btn-google" onclick="openLoginModal()" style="padding: 9px 18px; font-size: 0.86rem;">🔑 Đăng nhập Google</button>
        <button class="btn btn-secondary" onclick="openLoginModal()" style="padding: 9px 18px; font-size: 0.86rem;">⚡ Đăng nhập nhanh</button>
      </div>
    </div>

    <!-- User Machine Folder Bar (Chỉ hiển thị khi đã đăng nhập) -->
    <div id="userFolderBar" style="display:none; background: linear-gradient(135deg, rgba(26, 115, 232, 0.15) 0%, rgba(0, 242, 254, 0.08) 100%); border: 1px solid rgba(0, 242, 254, 0.35); border-radius: var(--radius-md); padding: 14px 18px; margin-bottom: 20px; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap;">
      <div style="display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 1.6rem;">📁</span>
        <div>
          <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <span style="font-weight: 700; font-size: 0.92rem; color: #fff;">Thư mục máy tính của bạn:</span>
            <span id="displayUserFolder" style="font-family: 'JetBrains Mono', monospace; color: var(--accent-cyan); font-weight: 600; background: rgba(0,0,0,0.35); padding: 3px 10px; border-radius: 4px; font-size: 0.82rem;">--</span>
          </div>
          <div style="font-size: 0.76rem; color: var(--text-muted); margin-top: 3px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <span>Tài khoản: <b id="displayUserEmail" style="color: #60a5fa;">--</b></span>
            <span>|</span>
            <span id="displayUserDrive" style="font-size: 0.75rem; padding: 2px 8px; border-radius: 4px;">--</span>
          </div>
        </div>
      </div>
      <div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">
        <button class="btn btn-secondary" onclick="openChangeFolderModal()" style="font-size: 0.8rem; padding: 7px 12px;">
          ✏️ Đổi thư mục máy
        </button>
        <button class="btn btn-primary" onclick="triggerServerScan()" id="btnServerScan" style="font-size: 0.8rem; padding: 7px 16px; background: linear-gradient(135deg, #1a73e8, #00f2fe);">
          🔍 Quét & Đồng bộ thư mục ngay
        </button>
      </div>
    </div>

    <!-- Cross-Platform Upload Banner -->
    <div class="upload-action-banner">
      <div class="upload-banner-text">
        <div class="upload-banner-title">
          <span>⚡ Nạp tài liệu đa thiết bị</span>
          <span style="font-size: 0.72rem; color: var(--accent-cyan); font-weight: normal;">(Tự động băm SHA-256, phân loại & lưu Drive)</span>
        </div>
        <div class="upload-banner-sub">
          Hỗ trợ chụp bài giảng từ điện thoại, nạp tệp từ iPad hoặc kết nối thư mục trên Laptop/PC.
        </div>
      </div>

      <div class="upload-btn-group">
        <!-- 1. Mobile Camera Trigger -->
        <input type="file" id="cameraInput" accept="image/*" capture="environment" style="display:none" onchange="handleFileInput(this.files)">
        <button class="btn btn-secondary" onclick="document.getElementById('cameraInput').click()">
          📸 Chụp bài giảng
        </button>

        <!-- 2. Multi-File Picker -->
        <input type="file" id="fileInput" multiple style="display:none" onchange="handleFileInput(this.files)">
        <button class="btn btn-secondary" onclick="document.getElementById('fileInput').click()">
          📤 Nạp tệp (PDF/Word/Ảnh)
        </button>

        <!-- 3. Desktop HTML5 File System API -->
        <button class="btn btn-primary" onclick="pickDirectoryOnDesktop()" id="btnPickFolder">
          📁 Chọn thư mục máy tính
        </button>
      </div>
    </div>

    <!-- Stats Row -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-header">
          <span>Kho tài liệu của bạn</span>
          <span>📁</span>
        </div>
        <div class="stat-value" id="statTotalFiles">0</div>
        <div class="stat-subtitle" id="statStoragePath">Tự động phân loại theo môn</div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span>Google Drive cá nhân</span>
          <span style="color: var(--accent-green);">☁️</span>
        </div>
        <div class="stat-value" id="statUploaded" style="color: var(--accent-green);">0</div>
        <div class="stat-subtitle" id="statDriveFolder">Thư mục: ThacSi_HTTT</div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span>Tài liệu mới (<24h)</span>
          <span style="color: var(--accent-cyan);">✨</span>
        </div>
        <div class="stat-value" id="statNewCount" style="color: var(--accent-cyan);">0</div>
        <div class="stat-subtitle">Nhận diện theo thời gian nạp</div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span>Môn học theo dõi</span>
          <span style="color: var(--accent-purple);">🎓</span>
        </div>
        <div class="stat-value" id="statSubjectsCount" style="color: var(--accent-purple);">0</div>
        <div class="stat-subtitle" id="statSubjectsList">Toán KH Dữ liệu, Triết học...</div>
      </div>
    </div>

    <!-- Toolbar -->
    <div class="toolbar-container">
      <div class="toolbar-row-top">
        <div class="search-box">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <input type="text" id="searchInput" placeholder="Tìm kiếm tài liệu theo tên, môn học..." oninput="applyFilters()">
        </div>

        <div class="filter-chips">
          <div class="chip active" id="chipAll" onclick="setQuickFilter('ALL')">
            🔥 Tất cả <span class="chip-badge" id="countAll">0</span>
          </div>
          <div class="chip" id="chipNew" onclick="setQuickFilter('NEW')">
            ✨ Mới (<24h) <span class="chip-badge" id="countNew">0</span>
          </div>
          <div class="chip" id="chipDrive" onclick="setQuickFilter('DRIVE')">
            ☁️ Trên Drive <span class="chip-badge" id="countDrive">0</span>
          </div>
        </div>
      </div>

      <div class="toolbar-row-bottom">
        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
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
          <select class="filter-select" id="filterSort" onchange="applyFilters()">
            <option value="NEWEST">⏱️ Mới nhất trước</option>
            <option value="NAME">🔤 Tên file A-Z</option>
            <option value="SIZE">💾 Dung lượng</option>
          </select>
        </div>

        <div class="view-switcher">
          <button class="view-btn active" id="btnViewCards" onclick="setViewMode('cards')">🎴 Thẻ</button>
          <button class="view-btn" id="btnViewTable" onclick="setViewMode('table')">📑 Bảng</button>
        </div>
      </div>
    </div>

    <!-- Cards Grid -->
    <div class="cards-grid" id="cardsContainer"></div>

    <!-- Table View -->
    <div class="table-container" id="tableContainer">
      <table>
        <thead>
          <tr>
            <th>Tập tin</th>
            <th>Môn học</th>
            <th>Phân loại</th>
            <th>Dung lượng</th>
            <th>Thời gian nạp</th>
            <th>Trạng thái</th>
            <th style="text-align: right;">Thao tác</th>
          </tr>
        </thead>
        <tbody id="filesTableBody"></tbody>
      </table>
    </div>
  </main>

  <!-- Modal Đăng nhập / Chọn tài khoản sinh viên -->
  <div class="modal-backdrop" id="loginModal">
    <div class="modal-box">
      <div class="modal-header">
        <div style="font-weight: 700; font-size: 1rem;">🔑 Đăng nhập Tài khoản Sinh viên</div>
        <button style="background:none; border:none; color:var(--text-muted); cursor:pointer; font-size:1.2rem;" onclick="closeLoginModal()">&times;</button>
      </div>
      <div class="modal-body">
        <div style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.5;">
          Mỗi sinh viên sử dụng tài khoản riêng để lưu trữ tài liệu vào Google Drive cá nhân của mình, đảm bảo hoàn toàn riêng tư và độc lập.
        </div>

        <div style="display: flex; flex-direction: column; gap: 10px; margin-top: 6px;">
          <!-- Nút Đăng nhập Google thật -->
          <a href="/auth/google/login" class="btn btn-google" style="padding: 12px; font-size: 0.9rem;">
            <svg width="18" height="18" viewBox="0 0 24 24"><path fill="#EA4335" d="M12 5c1.6 0 3 .6 4.1 1.6l3.1-3.1C17.3 1.7 14.8 1 12 1 7.5 1 3.7 3.6 1.9 7.3l3.7 2.9C6.5 7.3 9 5 12 5z"/><path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.6h6.5c-.3 1.5-1.1 2.8-2.4 3.7l3.7 2.9c2.2-2 3.7-5 3.7-8.9z"/><path fill="#FBBC05" d="M5.6 14.8c-.2-.7-.4-1.5-.4-2.8s.2-2.1.4-2.8L1.9 6.3C.7 8.7 0 10.3 0 12s.7 3.3 1.9 5.7l3.7-2.9z"/><path fill="#34A853" d="M12 23c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3 0-5.5-2.3-6.4-5.2L1.9 16C3.7 19.7 7.5 23 12 23z"/></svg>
            Đăng nhập bằng Google Workspace / Gmail
          </a>

          <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 10px 12px; margin-top: 4px; font-size: 0.76rem; line-height: 1.45;">
            <div style="color: #f87171; font-weight: 700; margin-bottom: 3px;">⚠️ Gặp lỗi 403 "access_denied" từ Google?</div>
            <div style="color: #cbd5e1;">
              Ứng dụng Google Cloud đang ở chế độ <b>Testing</b>. Bạn hãy thêm email vào mục <b>Test users</b> trên Google Cloud Console, HOẶC nhập email vào ô dưới để <b>Đăng nhập nhanh</b> ngay lập tức (không lo Google chặn)!
            </div>
          </div>

          <div style="text-align: center; font-size: 0.75rem; color: var(--text-dim); margin: 6px 0;">- CHỌN NHANH TÀI KHOẢN ĐỂ SỬ DỤNG / KIỂM TRA -</div>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
            <button type="button" class="btn btn-secondary" style="font-size: 0.76rem; text-align: left; padding: 9px 10px; border-color: rgba(26, 115, 232, 0.4);" onclick="quickLoginAs('xuanngocit@gmail.com', 'Admin XuanNgoc')">
              👑 <b>xuanngocit@gmail.com</b><br><span style="font-size:0.68rem; color:var(--accent-cyan);">(Tài khoản gốc & Drive)</span>
            </button>
            <button type="button" class="btn btn-secondary" style="font-size: 0.76rem; text-align: left; padding: 9px 10px; border-color: rgba(16, 185, 129, 0.4);" onclick="quickLoginAs('mongxuancomestic@gmail.com', 'Mộng Xuân')">
              👤 <b>mongxuancomestic@gmail.com</b><br><span style="font-size:0.68rem; color:#a7f3d0);">(Tài khoản SV riêng)</span>
            </button>
          </div>

          <div style="text-align: center; font-size: 0.75rem; color: var(--text-dim); margin: 6px 0;">- HOẶC NHẬP EMAIL BẤT KỲ -</div>

          <div style="display: flex; flex-direction: column; gap: 6px;">
            <input type="email" id="testEmailInput" class="form-control" placeholder="Nhập email (vd: mongxuancomestic@gmail.com)">
            <input type="text" id="testNameInput" class="form-control" placeholder="Họ và tên của bạn">
            <button class="btn btn-primary" onclick="submitTestLogin()" style="margin-top: 4px; background: linear-gradient(135deg, #10b981, #00f2fe);">🚀 Vào kho tài liệu của tôi</button>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="closeLoginModal()">Đóng</button>
      </div>
    </div>
  </div>

  <!-- Modal Đổi Thư Mục Máy Tính Của User -->
  <div class="modal-backdrop" id="changeFolderModal">
    <div class="modal-box">
      <div class="modal-header">
        <div style="font-weight: 700; font-size: 1rem;">📁 Đổi thư mục máy tính của bạn</div>
        <button style="background:none; border:none; color:var(--text-muted); cursor:pointer; font-size:1.2rem;" onclick="closeChangeFolderModal()">&times;</button>
      </div>
      <div class="modal-body">
        <div style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.5;">
          Nhập đường dẫn thư mục chứa tài liệu học tập trên máy tính của bạn (Windows/Mac/Linux). Hệ thống sẽ quét các tài liệu trong thư mục này và liên kết riêng cho tài khoản của bạn.
        </div>
        <div>
          <label style="font-size: 0.78rem; color: var(--text-muted); margin-top: 8px; display: block;">Đường dẫn thư mục máy:</label>
          <input type="text" id="inputUserFolder" class="form-control" style="margin-top: 4px; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;" placeholder="Ví dụ: D:/ThacSi_HTTT hoặc H:/Mon_Hoc">
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="closeChangeFolderModal()">Hủy</button>
        <button class="btn btn-primary" onclick="saveUserFolderAndScan()">💾 Lưu & Quét ngay</button>
      </div>
    </div>
  </div>

  <!-- Modal Sửa tay phân loại -->
  <div class="modal-backdrop" id="editModal">
    <div class="modal-box">
      <div class="modal-header">
        <div style="font-weight: 700; font-size: 1rem;">✏️ Sửa tay phân loại</div>
        <button style="background:none; border:none; color:var(--text-muted); cursor:pointer; font-size:1.2rem;" onclick="closeEditModal()">&times;</button>
      </div>
      <div class="modal-body">
        <input type="hidden" id="editRecordId">
        <div id="editFileName" style="font-weight: 600; color: #fff; font-size: 0.88rem; word-break: break-all;"></div>
        <div>
          <label style="font-size: 0.78rem; color: var(--text-muted);">Môn học:</label>
          <input type="text" id="editSubject" class="form-control" list="subjectOptions" style="margin-top: 4px;">
          <datalist id="subjectOptions">
            <option value="Toán khoa học dữ liệu">
            <option value="Triết học">
            <option value="Phương pháp ghi chú">
            <option value="Cơ sở dữ liệu">
            <option value="Phương pháp nghiên cứu">
          </datalist>
        </div>
        <div>
          <label style="font-size: 0.78rem; color: var(--text-muted);">Loại tài liệu:</label>
          <select id="editDocumentType" class="form-control" style="margin-top: 4px;">
            <option value="Giáo trình">Giáo trình</option>
            <option value="Slide">Slide</option>
            <option value="Ôn thi">Ôn thi</option>
            <option value="Tài liệu tham khảo">Tài liệu tham khảo</option>
          </select>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="closeEditModal()">Hủy</button>
        <button class="btn btn-primary" onclick="submitEditClassification()">💾 Lưu thay đổi</button>
      </div>
    </div>
  </div>

  <!-- Modal Cài đặt -->
  <div class="modal-backdrop" id="settingsModal">
    <div class="modal-box">
      <div class="modal-header">
        <div style="font-weight: 700; font-size: 1rem;">⚙️ Cài đặt hệ thống</div>
        <button style="background:none; border:none; color:var(--text-muted); cursor:pointer;" onclick="closeSettingsModal()">&times;</button>
      </div>
      <div class="modal-body">
        <div>
          <label style="font-size: 0.78rem; color: var(--text-muted);">Tài khoản hiện tại:</label>
          <div id="settingsUserEmail" style="font-weight: 600; color: var(--accent-cyan); font-size: 0.88rem; margin-top: 4px;">--</div>
        </div>
        <div>
          <label style="font-size: 0.78rem; color: var(--text-muted);">Thư mục lưu trữ trên máy (cho desktop):</label>
          <input type="text" id="cfgRootFolder" class="form-control" style="margin-top: 4px;">
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="logoutUser()" style="color: var(--accent-red); margin-right: auto;">🚪 Đăng xuất</button>
        <button class="btn btn-secondary" onclick="closeSettingsModal()">Đóng</button>
        <button class="btn btn-primary" onclick="saveSettings()">💾 Lưu</button>
      </div>
    </div>
  </div>

  <!-- Toast -->
  <div class="toast" id="toastMsg"></div>

  <script>
    let currentUser = null;
    let allFiles = [];
    let currentViewMode = 'cards';
    let currentQuickFilter = 'ALL';

    function showToast(msg) {
      const t = document.getElementById('toastMsg');
      t.textContent = msg;
      t.style.display = 'block';
      setTimeout(() => { t.style.display = 'none'; }, 3500);
    }

    function setViewMode(mode) {
      currentViewMode = mode;
      document.getElementById('btnViewCards').classList.toggle('active', mode === 'cards');
      document.getElementById('btnViewTable').classList.toggle('active', mode === 'table');
      document.getElementById('cardsContainer').style.display = (mode === 'cards') ? 'grid' : 'none';
      document.getElementById('tableContainer').style.display = (mode === 'table') ? 'block' : 'none';
      applyFilters();
    }

    function setQuickFilter(f) {
      currentQuickFilter = f;
      document.getElementById('chipAll').classList.toggle('active', f === 'ALL');
      document.getElementById('chipNew').classList.toggle('active', f === 'NEW');
      document.getElementById('chipDrive').classList.toggle('active', f === 'DRIVE');
      applyFilters();
    }

    function getExtBadge(name) {
      const ext = name.split('.').pop().toLowerCase();
      if (ext === 'pdf') return `<span class="ext-badge ext-pdf">PDF</span>`;
      if (ext === 'docx' || ext === 'doc') return `<span class="ext-badge ext-docx">DOCX</span>`;
      if (ext === 'pptx' || ext === 'ppt') return `<span class="ext-badge ext-pptx">PPTX</span>`;
      if (['jpg', 'jpeg', 'png'].includes(ext)) return `<span class="ext-badge ext-img">IMG</span>`;
      return `<span class="ext-badge ext-txt">${ext.toUpperCase()}</span>`;
    }

    function formatRelativeTime(isoStr) {
      if (!isoStr) return '--';
      try {
        const d = new Date(isoStr);
        const diffMs = new Date() - d;
        const diffSecs = Math.floor(diffMs / 1000);
        if (diffSecs < 60) return 'Vừa xong';
        if (diffSecs < 3600) return `${Math.floor(diffSecs / 60)} phút trước`;
        if (diffSecs < 86400) return `${Math.floor(diffSecs / 3600)} giờ trước`;
        return d.toLocaleDateString('vi-VN');
      } catch (e) {
        return isoStr;
      }
    }

    let defaultRootFolder = '';

    async function checkCurrentUser() {
      try {
        const res = await fetch('/api/me');
        const data = await res.json();
        defaultRootFolder = data.default_folder || '';
        const userSec = document.getElementById('userSection');
        const banner = document.getElementById('loginPromptBanner');
        const folderBar = document.getElementById('userFolderBar');

        if (data.authenticated && data.user) {
          currentUser = data.user;
          if (banner) banner.style.display = 'none';
          if (folderBar) {
            folderBar.style.display = 'flex';
            document.getElementById('displayUserFolder').textContent = currentUser.local_folder || defaultRootFolder || 'Chưa đặt';
            document.getElementById('displayUserEmail').textContent = currentUser.email;
            const driveEl = document.getElementById('displayUserDrive');
            if (driveEl) {
              if (data.drive_connected) {
                driveEl.style.background = 'rgba(16, 185, 129, 0.2)';
                driveEl.style.color = '#34d399';
                driveEl.textContent = `● ${data.drive_account}`;
              } else {
                driveEl.style.background = 'rgba(234, 179, 8, 0.2)';
                driveEl.style.color = '#facc15';
                driveEl.textContent = '● Lưu máy local (Chưa liên kết Drive)';
              }
            }
          }
          const initial = (currentUser.name || currentUser.email || 'U')[0].toUpperCase();
          userSec.innerHTML = `
            <div class="user-profile-chip" onclick="openSettingsModal()" title="${currentUser.email}">
              <div class="user-avatar">${initial}</div>
              <span class="user-name-text">${currentUser.name || currentUser.email}</span>
            </div>
          `;
          document.getElementById('settingsUserEmail').textContent = currentUser.email;
          const cfgInput = document.getElementById('cfgRootFolder');
          if (cfgInput) cfgInput.value = currentUser.local_folder || defaultRootFolder;

          await loadStats();
          await loadFiles();
        } else {
          currentUser = null;
          if (banner) banner.style.display = 'flex';
          if (folderBar) folderBar.style.display = 'none';
          userSec.innerHTML = `
            <button class="btn btn-google" onclick="openLoginModal()">
              🔑 Đăng nhập Google
            </button>
          `;
          renderLoggedOutState();
        }
      } catch (e) {
        console.error('Lỗi check user:', e);
      }
    }

    function renderLoggedOutState() {
      allFiles = [];
      document.getElementById('statTotalFiles').textContent = '0';
      document.getElementById('statUploaded').textContent = '0';
      document.getElementById('statNewCount').textContent = '0';
      document.getElementById('statSubjectsCount').textContent = '0';
      document.getElementById('countAll').textContent = '0';
      document.getElementById('countNew').textContent = '0';
      document.getElementById('countDrive').textContent = '0';
      const drv = document.getElementById('statDriveFolder');
      if (drv) drv.textContent = 'Chưa đăng nhập';
      const stp = document.getElementById('statStoragePath');
      if (stp) stp.textContent = 'Vui lòng đăng nhập';

      const container = document.getElementById('cardsContainer');
      if (container) {
        container.innerHTML = `
          <div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 50px 20px; background: var(--bg-card); border-radius: var(--radius-lg); border: 1px dashed var(--border-color);">
            <div style="font-size: 2.5rem; margin-bottom: 12px;">🔒</div>
            <div style="font-size: 1.15rem; font-weight: 700; color: #fff; margin-bottom: 6px;">Chưa đăng nhập tài khoản</div>
            <div style="font-size: 0.85rem; color: var(--text-dim); max-width: 500px; margin: 0 auto 18px; line-height: 1.5;">
              Hệ thống sẽ kết nối đúng thư mục trên máy tính và tài khoản Google Drive cá nhân của bạn ngay sau khi đăng nhập.
            </div>
            <div style="display: flex; justify-content: center; gap: 10px; flex-wrap: wrap;">
              <button class="btn btn-google" onclick="openLoginModal()" style="display: inline-flex;">
                🔑 Đăng nhập Google
              </button>
              <button class="btn btn-secondary" onclick="openLoginModal()" style="display: inline-flex;">
                ⚡ Đăng nhập bằng Email sinh viên
              </button>
            </div>
          </div>`;
      }
      const tbody = document.getElementById('filesTableBody');
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:36px; color:var(--text-dim);">Vui lòng đăng nhập để xem danh sách tài liệu của bạn.</td></tr>`;
      }
    }

    async function loadStats() {
      try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        document.getElementById('statTotalFiles').textContent = data.total_files || 0;
        document.getElementById('statUploaded').textContent = data.uploaded_files || 0;
        document.getElementById('statSubjectsCount').textContent = data.subjects_count || 0;

        if (data.drive_account) {
          const el = document.getElementById('statDriveFolder');
          if (el) el.textContent = data.drive_account;
        }
        if (data.local_folder) {
          const el = document.getElementById('statStoragePath');
          if (el) el.textContent = data.local_folder;
        }

        if (data.subjects && data.subjects.length > 0) {
          document.getElementById('statSubjectsList').textContent = data.subjects.join(', ');
          const fSub = document.getElementById('filterSubject');
          const curVal = fSub.value;
          fSub.innerHTML = '<option value="">Tất cả môn học</option>';
          data.subjects.forEach(s => {
            fSub.innerHTML += `<option value="${s}">${s}</option>`;
          });
          fSub.value = curVal;
        }
      } catch (err) {
        console.error('Lỗi stats:', err);
      }
    }

    async function loadFiles() {
      try {
        const res = await fetch('/api/files');
        allFiles = await res.json();

        const newFiles = allFiles.filter(f => f.is_new);
        const driveFiles = allFiles.filter(f => f.is_from_drive || Boolean(f.drive_file_id));

        document.getElementById('countAll').textContent = allFiles.length;
        document.getElementById('countNew').textContent = newFiles.length;
        document.getElementById('countDrive').textContent = driveFiles.length;
        document.getElementById('statNewCount').textContent = newFiles.length;

        applyFilters();
      } catch (err) {
        console.error('Lỗi load files:', err);
      }
    }

    function applyFilters() {
      const q = document.getElementById('searchInput').value.toLowerCase();
      const s = document.getElementById('filterSubject').value;
      const t = document.getElementById('filterType').value;
      const sortBy = document.getElementById('filterSort').value;

      let filtered = allFiles.filter(f => {
        const matchQ = !q || f.path.toLowerCase().includes(q) || (f.sha256 && f.sha256.toLowerCase().includes(q));
        const matchS = !s || f.subject === s;
        const matchT = !t || f.document_type === t;

        let matchQuick = true;
        if (currentQuickFilter === 'NEW') matchQuick = f.is_new;
        if (currentQuickFilter === 'DRIVE') matchQuick = f.is_from_drive || Boolean(f.drive_file_id);

        return matchQ && matchS && matchT && matchQuick;
      });

      if (sortBy === 'NEWEST') filtered.sort((a, b) => (b.id || 0) - (a.id || 0));
      else if (sortBy === 'NAME') filtered.sort((a, b) => a.path.localeCompare(b.path));
      else if (sortBy === 'SIZE') filtered.sort((a, b) => (b.size_bytes || 0) - (a.size_bytes || 0));

      if (currentViewMode === 'cards') renderCards(filtered);
      else renderTable(filtered);
    }

    function renderCards(files) {
      const container = document.getElementById('cardsContainer');
      if (!files || files.length === 0) {
        container.innerHTML = `
          <div style="grid-column: 1/-1; text-align: center; color: var(--text-dim); padding: 40px; background: var(--bg-card); border-radius: var(--radius-lg);">
            Không có tài liệu nào. Hãy bấm nút phía trên để chụp bài giảng hoặc nạp tệp!
          </div>`;
        return;
      }

      let html = '';
      files.forEach(f => {
        const fileName = f.path.split(/[\\\\/]/).pop();
        const relTime = formatRelativeTime(f.updated_at || f.created_at);
        const newBadge = f.is_new ? `<span class="badge-new">✨ MỚI</span>` : '';
        const driveBadge = f.drive_file_id 
          ? `<a href="https://drive.google.com/file/d/${f.drive_file_id}/view" target="_blank" class="btn-icon" style="color:#60a5fa;" title="Mở Drive">🔗 Drive</a>` 
          : `<span class="btn-icon" style="color:#00f2fe; background:rgba(0,242,254,0.1); border:1px solid rgba(0,242,254,0.3); font-size:0.7rem;" title="File lưu an toàn tại máy tính">💻 Máy local</span>`;

        html += `
          <div class="file-card ${f.is_new ? 'is-new-card' : ''}">
            <div style="display: flex; align-items: center; justify-content: space-between;">
              <div style="display: flex; gap: 6px; align-items: center;">
                ${getExtBadge(fileName)}
                ${newBadge}
              </div>
              <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #cbd5e1;">${f.size_formatted || '--'}</span>
            </div>

            <div class="card-title" title="${fileName}">${fileName}</div>
            <div class="card-path" title="${f.path}">${f.path}</div>

            <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px;">
              <span class="tag-subject">${f.subject || 'Chưa phân loại'}</span>
              <span class="tag-type">${f.document_type || 'Tài liệu'}</span>
            </div>

            <div class="card-footer">
              <span style="font-size: 0.72rem; color: var(--text-dim);">⏱️ ${relTime}</span>
              <div style="display: flex; gap: 6px;">
                ${driveBadge}
                <button class="btn-icon" onclick="openEditModal(${f.id}, '${encodeURIComponent(fileName)}', '${encodeURIComponent(f.subject || '')}', '${encodeURIComponent(f.document_type || '')}')">✏️ Sửa</button>
              </div>
            </div>
          </div>
        `;
      });
      container.innerHTML = html;
    }

    function renderTable(files) {
      const tbody = document.getElementById('filesTableBody');
      if (!files || files.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:32px; color:var(--text-dim);">Chưa có tài liệu.</td></tr>`;
        return;
      }
      let html = '';
      files.forEach(f => {
        const fileName = f.path.split(/[\\\\/]/).pop();
        const relTime = formatRelativeTime(f.updated_at || f.created_at);
        const newBadge = f.is_new ? `<span class="badge-new">✨ MỚI</span>` : '';
        const driveBtn = f.drive_file_id 
          ? `<a href="https://drive.google.com/file/d/${f.drive_file_id}/view" target="_blank" class="btn-icon" style="color:#60a5fa;">🔗 Drive</a>` 
          : '';
        const statusBadge = f.drive_file_id
          ? `<span style="color:var(--accent-green); font-size:0.75rem; font-weight:600;">● ĐÃ LÊN DRIVE</span>`
          : `<span style="color:var(--accent-cyan); font-size:0.75rem; font-weight:600;">💻 LƯU MÁY LOCAL</span>`;

        html += `
          <tr>
            <td>
              <div style="display:flex; align-items:center; gap:8px;">
                ${getExtBadge(fileName)}
                <div>
                  <div style="font-weight:600; color:#fff;">${fileName} ${newBadge}</div>
                  <div style="font-size:0.7rem; color:var(--text-dim); font-family:monospace;">${f.path}</div>
                </div>
              </div>
            </td>
            <td><span class="tag-subject">${f.subject || 'Chung'}</span></td>
            <td><span class="tag-type">${f.document_type || 'Tài liệu'}</span></td>
            <td style="font-family: monospace;">${f.size_formatted || '--'}</td>
            <td style="font-size: 0.75rem; color: var(--text-muted);">⏱️ ${relTime}</td>
            <td>${statusBadge}</td>
            <td style="text-align: right;">
              <div style="display:flex; justify-content:flex-end; gap:6px;">
                ${driveBtn}
                <button class="btn-icon" onclick="openEditModal(${f.id}, '${encodeURIComponent(fileName)}', '${encodeURIComponent(f.subject || '')}', '${encodeURIComponent(f.document_type || '')}')">✏️ Sửa</button>
              </div>
            </td>
          </tr>
        `;
      });
      tbody.innerHTML = html;
    }

    /* Cross-Platform Upload Functions */
    async function handleFileInput(fileList) {
      if (!fileList || fileList.length === 0) return;
      if (!currentUser) {
        showToast('⚠️ Vui lòng đăng nhập tài khoản trước khi nạp tài liệu!');
        openLoginModal();
        return;
      }
      showToast(`Đang nạp ${fileList.length} tệp...`);

      for (let i = 0; i < fileList.length; i++) {
        const file = fileList[i];
        try {
          const reader = new FileReader();
          reader.onload = async function(e) {
            const base64Data = e.target.result.split(',')[1];
            const payload = {
              filename: file.name,
              content_base64: base64Data,
              size_bytes: file.size,
            };
            const res = await fetch('/api/upload', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.ok) {
              showToast(`✅ Đã nạp & lưu Drive: ${file.name}`);
              loadStats();
              loadFiles();
            } else {
              showToast(`⚠️ Lỗi ${file.name}: ${data.error || 'Thất bại'}`);
            }
          };
          reader.readAsDataURL(file);
        } catch (err) {
          console.error('Lỗi đọc file:', err);
        }
      }
    }

    /* HTML5 File System Access API cho Desktop */
    async function pickDirectoryOnDesktop() {
      if (!currentUser) {
        showToast('⚠️ Vui lòng đăng nhập tài khoản trước khi chọn thư mục máy tính!');
        openLoginModal();
        return;
      }
      if (!window.showDirectoryPicker) {
        document.getElementById('fileInput').click();
        return;
      }
      try {
        const dirHandle = await window.showDirectoryPicker();
        showToast(`📁 Đang quét thư mục: ${dirHandle.name}...`);
        let count = 0;
        for await (const entry of dirHandle.values()) {
          if (entry.kind === 'file') {
            const file = await entry.getFile();
            const ext = '.' + file.name.split('.').pop().toLowerCase();
            if (['.pdf', '.docx', '.pptx', '.jpg', '.jpeg', '.png', '.txt', '.md'].includes(ext)) {
              await handleFileInput([file]);
              count++;
            }
          }
        }
        showToast(`🎉 Đã quét và nạp ${count} tài liệu từ ${dirHandle.name}!`);
      } catch (err) {
        if (err.name !== 'AbortError') {
          showToast(`Lỗi chọn thư mục: ${err.message}`);
        }
      }
    }

    /* Modals & Auth */
    function openLoginModal() { document.getElementById('loginModal').style.display = 'flex'; }
    function closeLoginModal() { document.getElementById('loginModal').style.display = 'none'; }

    function quickLoginAs(email, name) {
      const emailInput = document.getElementById('testEmailInput');
      const nameInput = document.getElementById('testNameInput');
      if (emailInput) emailInput.value = email;
      if (nameInput) nameInput.value = name;
      submitTestLogin();
    }

    async function submitTestLogin() {
      const email = document.getElementById('testEmailInput').value.trim();
      const name = document.getElementById('testNameInput').value.trim() || email.split('@')[0];
      if (!email) { alert('Vui lòng nhập địa chỉ email sinh viên!'); return; }

      try {
        const res = await fetch('/auth/test-login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, name })
        });
        const data = await res.json();
        if (data.ok) {
          showToast(`👋 Chào mừng sinh viên: ${name}!`);
          closeLoginModal();
          checkCurrentUser();
          loadStats();
          loadFiles();
        }
      } catch (e) {
        alert('Lỗi đăng nhập: ' + e);
      }
    }

    async function logoutUser() {
      try {
        await fetch('/auth/logout', { method: 'POST' });
        showToast('Đã đăng xuất.');
        closeSettingsModal();
        checkCurrentUser();
        loadStats();
        loadFiles();
      } catch (e) {
        console.error(e);
      }
    }

    function openEditModal(id, encName, encSub, encType) {
      document.getElementById('editRecordId').value = id;
      document.getElementById('editFileName').textContent = decodeURIComponent(encName);
      document.getElementById('editSubject').value = decodeURIComponent(encSub);
      document.getElementById('editDocumentType').value = decodeURIComponent(encType) || 'Tài liệu tham khảo';
      document.getElementById('editModal').style.display = 'flex';
    }
    function closeEditModal() { document.getElementById('editModal').style.display = 'none'; }

    async function submitEditClassification() {
      const id = document.getElementById('editRecordId').value;
      const subject = document.getElementById('editSubject').value.trim();
      const docType = document.getElementById('editDocumentType').value;
      if (!subject) { alert('Vui lòng nhập môn học!'); return; }

      try {
        const res = await fetch('/api/files/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: parseInt(id), subject, document_type: docType })
        });
        const d = await res.json();
        if (d.ok) {
          showToast('✅ Đã cập nhật môn học!');
          closeEditModal();
          loadStats();
          loadFiles();
        }
      } catch (e) { alert('Lỗi: ' + e); }
    }

    function openChangeFolderModal() {
      const cur = (currentUser && currentUser.local_folder) || defaultRootFolder || '';
      document.getElementById('inputUserFolder').value = cur;
      document.getElementById('changeFolderModal').style.display = 'flex';
    }
    function closeChangeFolderModal() {
      document.getElementById('changeFolderModal').style.display = 'none';
    }

    async function saveUserFolderAndScan() {
      const folder = document.getElementById('inputUserFolder').value.trim();
      if (!folder) { alert('Vui lòng nhập đường dẫn thư mục!'); return; }
      try {
        const res = await fetch('/api/user/folder', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ local_folder: folder })
        });
        const d = await res.json();
        if (d.ok) {
          if (currentUser) currentUser.local_folder = folder;
          document.getElementById('displayUserFolder').textContent = folder;
          closeChangeFolderModal();
          showToast('✅ Đã cập nhật thư mục máy tính!');
          await triggerServerScan();
        } else {
          alert('Lỗi: ' + (d.error || 'Không thể lưu thư mục'));
        }
      } catch (e) {
        alert('Lỗi: ' + e.message);
      }
    }

    async function triggerServerScan() {
      if (!currentUser) {
        showToast('⚠️ Vui lòng đăng nhập tài khoản trước khi quét!');
        openLoginModal();
        return;
      }
      const folder = (currentUser && currentUser.local_folder) || defaultRootFolder;
      const btn = document.getElementById('btnServerScan');
      const oldText = btn ? btn.innerHTML : '';
      if (btn) {
        btn.innerHTML = '⏳ Đang quét...';
        btn.disabled = true;
      }
      showToast(`🔍 Đang quét thư mục máy cho ${currentUser.email}...`);

      try {
        const res = await fetch('/api/scan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folder_path: folder })
        });
        const data = await res.json();
        if (data.ok) {
          showToast(`🎉 Quét hoàn tất! Đã tìm thấy ${data.count} tài liệu.`);
          await loadStats();
          await loadFiles();
        } else {
          showToast(`⚠️ Lỗi quét: ${data.error || 'Thất bại'}`);
        }
      } catch (e) {
        showToast(`⚠️ Lỗi kết nối: ${e.message}`);
      } finally {
        if (btn) {
          btn.innerHTML = oldText;
          btn.disabled = false;
        }
      }
    }

    function openSettingsModal() { document.getElementById('settingsModal').style.display = 'flex'; }
    function closeSettingsModal() { document.getElementById('settingsModal').style.display = 'none'; }
    async function saveSettings() {
      const rootFolder = document.getElementById('cfgRootFolder').value.trim();
      try {
        await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ root_folder: rootFolder })
        });
        showToast('Đã lưu cài đặt.');
        closeSettingsModal();
      } catch (e) { alert('Lỗi: ' + e); }
    }

    window.addEventListener('DOMContentLoaded', () => {
      checkCurrentUser();
    });
  </script>
</body>
</html>
"""


def get_user_storage_folder(user: Optional[Dict[str, Any]], config_root_folder: Path | str) -> Path:
    """Trả về đường dẫn thư mục lưu trữ cục bộ riêng biệt cho từng người dùng."""
    root_path = Path(config_root_folder).resolve()
    if not user:
        return root_path

    email = user.get("email", "").strip().lower()
    custom = user.get("local_folder", "").strip()
    if custom:
        return Path(custom).resolve()

    # Tài khoản gốc sở hữu thư mục root_folder
    if email in ["xuanngocit@gmail.com", "default@user"]:
        return root_path

    # Người dùng khác chưa cài đặt thư mục riêng:
    # Tạo thư mục riêng biệt tại Users_Storage/<safe_email> để không lẫn vào thư mục gốc của xuanngocit
    safe_name = email.replace("@", "_at_").replace(".", "_")
    user_dir = root_path.parent / "Users_Storage" / safe_name
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_user_drive_manager(
    user: Optional[Dict[str, Any]],
    root_dm: Optional[DriveManager],
    db: Optional[Database],
    credentials_path: Path | str = "credentials.json",
) -> Tuple[Optional[DriveManager], bool, str]:
    """Trả về (DriveManager, is_connected, account_display) tương ứng với tài khoản người dùng."""
    if not user:
        return None, False, "Chưa đăng nhập"

    email = user.get("email", "").strip().lower()

    # 1. Nếu là tài khoản gốc xuanngocit@gmail.com -> Dùng root_dm (kết nối token.json của xuanngocit)
    if email in ["xuanngocit@gmail.com", "default@user"]:
        if root_dm and root_dm.is_configured():
            return root_dm, True, "Google Drive: xuanngocit@gmail.com"
        return None, False, "Chưa cấu hình Google Drive"

    # 2. Nếu là user khác, kiểm tra xem user đó có token OAuth riêng trong database hay không
    if db:
        db_user = db.get_user_by_email(email)
        if db_user and db_user.get("access_token"):
            try:
                token_dict = {
                    "access_token": db_user["access_token"],
                    "refresh_token": db_user.get("refresh_token"),
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
                user_dm = DriveManager.from_token_dict(
                    token_info=token_dict,
                    credentials_file=str(credentials_path),
                    root_folder_id=db_user.get("drive_root_folder_id") or "",
                )
                return user_dm, True, f"Google Drive: {email}"
            except Exception as exc:
                logger.warning("Không thể khởi tạo DriveManager cho %s: %s", email, exc)

    # 3. User khác chưa kết nối Google Drive riêng -> TUYỆT ĐỐI KHÔNG DÙNG DRIVE CỦA XUANNGOCTIT!
    return None, False, "Chưa kết nối Drive riêng (Lưu tại máy)"


class DashboardRequestHandler(http.server.BaseHTTPRequestHandler):
    """Handler xử lý API và giao diện Web Dashboard Multi-User."""

    database: Optional[Database] = None
    drive_manager: Optional[DriveManager] = None
    config_path: Path = Path("config.json")
    scan_callback: Optional[Any] = None
    classifier: Optional[PathClassifier] = None
    auto_sync_worker: Optional[Any] = None

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _get_current_user(self) -> Optional[Dict[str, Any]]:
        """Lấy thông tin người dùng từ Cookie session nếu có."""
        cookie_header = self.headers.get("Cookie")
        session_id = None
        if cookie_header:
            cookie = http.cookies.SimpleCookie()
            try:
                cookie.load(cookie_header)
                if "ths_session" in cookie:
                    session_id = cookie["ths_session"].value
            except Exception:
                pass

        if session_id and session_id in SESSION_STORE:
            return SESSION_STORE[session_id]

        return None

    def _send_json(self, data: Any, status: int = 200, set_cookie: Optional[str] = None) -> None:
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)
        current_user = self._get_current_user()

        if path in ["/", "/index.html"]:
            content = get_html_dashboard().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/api/me":
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            config_root = cfg.get("root_folder", "")

            user_dm, drive_connected, drive_account = get_user_drive_manager(
                current_user, self.drive_manager, self.database
            )

            user_data = dict(current_user) if current_user else None
            if user_data:
                user_folder_path = get_user_storage_folder(user_data, config_root)
                user_data["local_folder"] = str(user_folder_path)

            self._send_json({
                "authenticated": bool(current_user),
                "user": user_data,
                "drive_connected": drive_connected,
                "drive_account": drive_account,
                "default_folder": config_root,
            })
            return

        # Google OAuth Callback
        if path == "/auth/google/callback":
            code = query_params.get("code", [""])[0]
            if not code:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing authorization code")
                return

            try:
                client_id = ""
                client_secret = ""
                if Path("credentials.json").is_file():
                    with open("credentials.json", "r", encoding="utf-8") as f:
                        cdata = json.load(f)
                    cinfo = cdata.get("installed", {}) or cdata.get("web", {})
                    client_id = cinfo.get("client_id", "")
                    client_secret = cinfo.get("client_secret", "")

                email = ""
                name = ""
                avatar_url = ""
                access_token = ""
                refresh_token = ""

                if client_id and client_secret:
                    token_url = "https://oauth2.googleapis.com/token"
                    post_fields = urllib.parse.urlencode({
                        "code": code,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uri": "http://localhost:8080/auth/google/callback",
                        "grant_type": "authorization_code",
                    }).encode("utf-8")
                    req = urllib.request.Request(token_url, data=post_fields, headers={"Content-Type": "application/x-www-form-urlencoded"})
                    try:
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            token_resp = json.loads(resp.read().decode("utf-8"))
                            access_token = token_resp.get("access_token", "")
                            refresh_token = token_resp.get("refresh_token", "")

                        if access_token:
                            uinfo_req = urllib.request.Request("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"})
                            with urllib.request.urlopen(uinfo_req, timeout=10) as resp:
                                uinfo = json.loads(resp.read().decode("utf-8"))
                                email = uinfo.get("email", "").strip().lower()
                                name = uinfo.get("name", "")
                                avatar_url = uinfo.get("picture", "")
                    except Exception as exc:
                        logger.warning("Không thể trao đổi Google token tự động: %s", exc)

                if not email:
                    email = "xuanngocit@gmail.com"

                session_id = secrets.token_hex(24)
                if self.database:
                    user = self.database.get_or_create_user(email=email, name=name, avatar_url=avatar_url)
                    if access_token:
                        self.database.update_user_tokens(email=email, access_token=access_token, refresh_token=refresh_token)
                        user = self.database.get_user_by_email(email) or user
                    SESSION_STORE[session_id] = user
                else:
                    SESSION_STORE[session_id] = {"email": email, "name": name, "avatar_url": avatar_url}

                # Redirect về trang chủ kèm Cookie
                cookie_str = f"ths_session={session_id}; Path=/; HttpOnly; SameSite=Lax"
                self.send_response(302)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie", cookie_str)
                self.end_headers()
                return
            except Exception as exc:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"OAuth Callback Error: {exc}".encode("utf-8"))
                return

        if path == "/auth/google/login":
            # Điều hướng sang trang Google OAuth Consent Screen
            client_id = ""
            if Path("credentials.json").is_file():
                try:
                    with open("credentials.json", "r", encoding="utf-8") as f:
                        cred_data = json.load(f)
                        client_id = cred_data.get("installed", {}).get("client_id", "") or cred_data.get("web", {}).get("client_id", "")
                except Exception:
                    pass

            redirect_uri = "http://localhost:8080/auth/google/callback"
            if client_id:
                oauth_url = (
                    f"https://accounts.google.com/o/oauth2/v2/auth?"
                    f"client_id={urllib.parse.quote(client_id)}&"
                    f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
                    f"response_type=code&"
                    f"scope={urllib.parse.quote('openid email profile https://www.googleapis.com/auth/drive.file')}&"
                    f"access_type=offline&prompt=consent"
                )
            else:
                oauth_url = "/?login_error=missing_credentials"

            self.send_response(302)
            self.send_header("Location", oauth_url)
            self.end_headers()
            return

        if path == "/api/stats":
            if not self.database:
                self._send_json({"error": "Database not initialized"}, 500)
                return

            user_email = current_user.get("email") if current_user else None
            user_dm, drive_connected, drive_account = get_user_drive_manager(
                current_user, self.drive_manager, self.database
            )

            records = self.database.get_all_records(limit=1000, user_email=user_email)
            unique_files: Dict[str, Any] = {}
            for r in records:
                p = r["path"]
                if p not in unique_files or r.get("status") in ["UPLOADED", "SAVED_LOCAL"]:
                    unique_files[p] = r

            file_list = list(unique_files.values())
            total = len(file_list)
            uploaded = sum(1 for r in file_list if r.get("status") in ["UPLOADED", "SAVED_LOCAL"])
            duplicate = sum(1 for r in file_list if r.get("status") == "DUPLICATE")
            error = sum(1 for r in file_list if r.get("status") == "ERROR")

            subjects = sorted(list({r["subject"] for r in file_list if r.get("subject")}))

            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            config_root = cfg.get("root_folder", "")
            user_folder_path = str(get_user_storage_folder(current_user, config_root))

            self._send_json({
                "total_files": total,
                "uploaded_files": uploaded,
                "duplicate_files": duplicate,
                "error_files": error,
                "subjects_count": len(subjects),
                "subjects": subjects,
                "drive_connected": drive_connected,
                "drive_account": drive_account,
                "local_folder": user_folder_path,
            })
            return

        if path == "/api/files":
            if not self.database:
                self._send_json([], 500)
                return

            user_email = current_user.get("email") if current_user else None
            records = self.database.get_all_records(limit=1000, user_email=user_email)
            unique_files: Dict[str, Any] = {}
            for r in records:
                p = r["path"]
                if p not in unique_files:
                    unique_files[p] = r
                elif r.get("status") in ["UPLOADED", "SAVED_LOCAL"] and unique_files[p].get("status") not in ["UPLOADED", "SAVED_LOCAL"]:
                    unique_files[p] = r

            file_list = list(unique_files.values())
            file_list.sort(key=lambda x: x.get("id", 0), reverse=True)

            now_ts = time.time()
            for f in file_list:
                p = f.get("path", "")
                try:
                    size_b = os.path.getsize(p)
                    if size_b < 1024:
                        f["size_formatted"] = f"{size_b} B"
                    elif size_b < 1024 * 1024:
                        f["size_formatted"] = f"{size_b / 1024:.1f} KB"
                    else:
                        f["size_formatted"] = f"{size_b / (1024 * 1024):.1f} MB"
                    f["size_bytes"] = size_b
                except Exception:
                    f["size_formatted"] = "--"
                    f["size_bytes"] = 0

                f_time = f.get("updated_at") or f.get("created_at") or ""
                is_new = False
                if f_time:
                    try:
                        dt = datetime.fromisoformat(f_time.replace("Z", "+00:00"))
                        if abs(now_ts - dt.timestamp()) < 86400:
                            is_new = True
                    except Exception:
                        pass
                f["is_new"] = is_new
                f["is_from_drive"] = bool(f.get("drive_file_id"))

            self._send_json(file_list)
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
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(f"Lỗi: {exc}".encode("utf-8"))
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
        current_user = self._get_current_user()

        content_len = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            body = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            body = {}

        # Quick Test Login for Students
        if path == "/auth/test-login":
            email = body.get("email", "").strip()
            name = body.get("name", "").strip() or email.split("@")[0]
            if not email or not self.database:
                self._send_json({"ok": False, "error": "Vui lòng cung cấp email"}, 400)
                return

            user = self.database.get_or_create_user(email=email, name=name)
            session_id = secrets.token_hex(24)
            SESSION_STORE[session_id] = user
            cookie_str = f"ths_session={session_id}; Path=/; HttpOnly; SameSite=Lax"
            self._send_json({"ok": True, "user": user}, set_cookie=cookie_str)
            return

        if path == "/auth/logout":
            cookie_header = self.headers.get("Cookie")
            if cookie_header:
                cookie = http.cookies.SimpleCookie()
                try:
                    cookie.load(cookie_header)
                    if "ths_session" in cookie:
                        sid = cookie["ths_session"].value
                        SESSION_STORE.pop(sid, None)
                except Exception:
                    pass
            clear_cookie = "ths_session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT"
            self._send_json({"ok": True}, set_cookie=clear_cookie)
            return

        # Multi-Platform Upload API (Desktop, iPad, Phone)
        if path == "/api/upload":
            if not current_user:
                self._send_json({"ok": False, "error": "Vui lòng đăng nhập tài khoản trước khi nạp tài liệu"}, 401)
                return

            filename = body.get("filename", "").strip()
            content_base64 = body.get("content_base64", "")
            if not filename or not content_base64 or not self.database:
                self._send_json({"ok": False, "error": "Dữ liệu upload không hợp lệ"}, 400)
                return

            try:
                raw_bytes = base64.b64decode(content_base64)
                import hashlib
                sha256_hash = hashlib.sha256(raw_bytes).hexdigest()

                user_email = current_user.get("email", "default@user")

                # Kiểm tra trùng lặp cho tài khoản này
                existing = self.database.find_by_sha256(sha256_hash, user_email=user_email)
                if existing and existing.get("status") in [STATUS_UPLOADED, STATUS_SAVED_LOCAL]:
                    self._send_json({"ok": True, "duplicate": True, "message": "File đã tồn tại trong kho tài liệu của bạn."})
                    return

                # Phân loại
                subject = body.get("subject")
                doc_type = body.get("document_type")
                if not subject or not doc_type:
                    if DashboardRequestHandler.classifier:
                        info = DashboardRequestHandler.classifier.classify_path(Path(filename))
                        subject = subject or info.get("subject", "Tài liệu chung")
                        doc_type = doc_type or info.get("document_type", "Tài liệu tham khảo")
                    else:
                        subject = subject or "Tài liệu chung"
                        doc_type = doc_type or "Tài liệu tham khảo"

                # Lưu file vào thư mục lưu trữ CỦA TỪNG USER (Cách ly hoàn toàn)
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                config_root = cfg.get("root_folder", "")
                user_folder = get_user_storage_folder(current_user, config_root)
                dest_dir = user_folder / subject
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path = dest_dir / filename
                with open(dest_path, "wb") as f_out:
                    f_out.write(raw_bytes)

                # Lấy DriveManager riêng của user này
                user_dm, drive_connected, _ = get_user_drive_manager(
                    current_user, self.drive_manager, self.database
                )
                drive_file_id = None
                file_status = STATUS_SAVED_LOCAL

                if user_dm and user_dm.is_configured():
                    try:
                        drive_file_id = user_dm.upload_file(
                            file_path=dest_path,
                            subject=subject,
                            document_type=doc_type,
                        )
                        if drive_file_id:
                            file_status = STATUS_UPLOADED
                    except Exception as exc:
                        logger.warning("Lỗi upload Drive khi user %s nạp file: %s", user_email, exc)

                rec_id = self.database.insert_record(
                    sha256=sha256_hash,
                    path=str(dest_path),
                    subject=subject,
                    document_type=doc_type,
                    status=file_status,
                    drive_file_id=drive_file_id,
                    user_email=user_email,
                )

                self._send_json({
                    "ok": True,
                    "id": rec_id,
                    "filename": filename,
                    "subject": subject,
                    "document_type": doc_type,
                    "status": file_status,
                    "drive_file_id": drive_file_id,
                })
                return
            except Exception as exc:
                logger.error("Lỗi xử lý API upload: %s", exc, exc_info=True)
                self._send_json({"ok": False, "error": str(exc)}, 500)
                return

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

                if self.drive_manager and self.drive_manager.is_configured() and record.get("drive_file_id"):
                    try:
                        target_folder_id = self.drive_manager.resolve_folder_hierarchy(
                            subject=new_subject,
                            document_type=new_type,
                        )
                        service = self.drive_manager.get_service()
                        file_meta = service.files().get(fileId=record["drive_file_id"], fields="parents").execute()
                        previous_parents = ",".join(file_meta.get("parents", []))

                        service.files().update(
                            fileId=record["drive_file_id"],
                            addParents=target_folder_id,
                            removeParents=previous_parents,
                            fields="id, parents",
                        ).execute()
                    except Exception as exc:
                        logger.warning("Không thể di chuyển file Drive: %s", exc)

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

        if path == "/api/user/folder":
            if not current_user or not self.database:
                self._send_json({"ok": False, "error": "Vui lòng đăng nhập tài khoản"}, 401)
                return
            folder = body.get("local_folder", "").strip()
            if folder:
                self.database.update_user_folder(current_user["email"], folder)
                current_user["local_folder"] = folder
            self._send_json({"ok": True, "local_folder": folder})
            return

        if path == "/api/scan":
            folder_path = body.get("folder_path") if isinstance(body, dict) else None
            user_email = current_user.get("email") if current_user else "default@user"

            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            config_root = cfg.get("root_folder", "")

            if current_user and folder_path and self.database:
                try:
                    self.database.update_user_folder(current_user["email"], folder_path)
                    current_user["local_folder"] = folder_path
                except Exception as exc:
                    logger.warning("Không thể lưu folder user: %s", exc)

            target_folder = folder_path or (current_user.get("local_folder") if current_user else None)
            if not target_folder:
                target_folder = str(get_user_storage_folder(current_user, config_root))

            count = 0
            cb = DashboardRequestHandler.scan_callback
            if cb:
                try:
                    import inspect
                    sig = inspect.signature(cb)
                    if len(sig.parameters) >= 2:
                        count = cb(target_folder=target_folder, user_email=user_email)
                    elif len(sig.parameters) == 1:
                        count = cb(target_folder=target_folder)
                    else:
                        count = cb()
                except Exception as exc:
                    logger.error("Lỗi callback scan: %s", exc)

            self._send_json({
                "ok": True,
                "count": count,
                "folder": str(target_folder) if target_folder else "",
                "user_email": user_email,
            })
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
    classifier: Optional[Any] = None,
    auto_sync_worker: Optional[Any] = None,
) -> ThreadedHTTPServer:
    """Khởi động Web Dashboard Server trong một luồng riêng biệt."""
    DashboardRequestHandler.database = database
    DashboardRequestHandler.drive_manager = drive_manager
    DashboardRequestHandler.config_path = Path(config_path).resolve()
    DashboardRequestHandler.scan_callback = scan_callback
    DashboardRequestHandler.classifier = classifier
    DashboardRequestHandler.auto_sync_worker = auto_sync_worker

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
