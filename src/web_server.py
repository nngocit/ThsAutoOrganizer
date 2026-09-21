"""Web Dashboard Server cho ThacSi HTTT Auto Organizer.

Giao diện quản lý hiện đại theo phong cách Google AI Studio / Glassmorphism:
- Bảng điều khiển thống kê trực quan
- Nhận diện tức thì file MỚI (✨ MỚI badge, bộ lọc mới, hiển thị thời gian cập nhật tương đối)
- Hỗ trợ chuyển đổi linh hoạt: Chế độ Thẻ (Cards Grid) & Chế độ Bảng (Table View)
- Tự động kéo tài liệu từ Google Drive về máy định kỳ (Auto Drive Sync Worker)
- Tính năng "Sửa tay" (Manual Edit) Môn học & Loại tài liệu
- Bật/tắt các định dạng hỗ trợ (PDF, DOCX, PPTX, JPG, PNG...)
- Quét lại thư mục theo yêu cầu và xem Live Logs
"""

import http.server
import json
import logging
import os
from pathlib import Path
import socketserver
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.database import Database
from src.drive import DriveManager

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
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-base: #080a12;
      --bg-surface: rgba(16, 20, 32, 0.75);
      --bg-card: rgba(22, 28, 46, 0.65);
      --bg-card-hover: rgba(30, 38, 62, 0.85);
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
      --grad-glow: radial-gradient(ellipse at 50% -20%, rgba(26, 115, 232, 0.2), rgba(139, 92, 246, 0.12), transparent 70%);
      --grad-new: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
      --grad-drive: linear-gradient(135deg, #10b981 0%, #059669 100%);
      
      --radius-sm: 8px;
      --radius-md: 12px;
      --radius-lg: 18px;
      --radius-full: 9999px;
      --shadow-glass: 0 8px 32px 0 rgba(0, 0, 0, 0.45);
      --shadow-glow: 0 0 25px rgba(0, 242, 254, 0.18);
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
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: var(--bg-base); }
    ::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.15); border-radius: var(--radius-full); }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.25); }

    /* Header */
    header {
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-color);
      padding: 12px 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
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
      font-weight: 700;
      text-transform: uppercase;
      padding: 2px 8px;
      border-radius: var(--radius-full);
      background: rgba(0, 242, 254, 0.15);
      color: var(--accent-cyan);
      border: 1px solid rgba(0, 242, 254, 0.3);
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      border-radius: var(--radius-full);
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      font-size: 0.8rem;
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.2s;
    }
    .status-pill:hover {
      background: rgba(255, 255, 255, 0.08);
      border-color: rgba(0, 242, 254, 0.3);
    }
    .pulse-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent-green);
      box-shadow: 0 0 8px var(--accent-green);
      animation: pulseAnim 2s infinite;
    }
    @keyframes pulseAnim {
      0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
      70% { transform: scale(1.1); box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
      100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    /* Buttons */
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 15px;
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
    .btn-sync {
      background: rgba(16, 185, 129, 0.15);
      border-color: rgba(16, 185, 129, 0.4);
      color: #34d399;
    }
    .btn-sync:hover {
      background: rgba(16, 185, 129, 0.25);
      box-shadow: 0 0 14px rgba(16, 185, 129, 0.3);
    }

    /* Main Container */
    main {
      flex: 1;
      max-width: 1440px;
      width: 100%;
      margin: 0 auto;
      padding: 24px 28px 48px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    /* Stats Grid */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
    }
    .stat-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 18px 22px;
      backdrop-filter: blur(16px);
      position: relative;
      overflow: hidden;
      transition: all 0.2s;
    }
    .stat-card:hover {
      border-color: rgba(255, 255, 255, 0.15);
      transform: translateY(-2px);
      background: var(--bg-card-hover);
    }
    .stat-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: var(--text-muted);
      font-size: 0.8rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .stat-icon { font-size: 1.25rem; }
    .stat-value {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 2.1rem;
      font-weight: 800;
      margin: 10px 0 4px;
      letter-spacing: -0.02em;
    }
    .stat-subtitle {
      font-size: 0.75rem;
      color: var(--text-dim);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    /* Modern Controls & Filters Toolbar */
    .toolbar-container {
      display: flex;
      flex-direction: column;
      gap: 14px;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 16px 20px;
      backdrop-filter: blur(16px);
    }
    .toolbar-row-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      flex-wrap: wrap;
    }
    .search-box {
      flex: 1;
      min-width: 280px;
      display: flex;
      align-items: center;
      gap: 10px;
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 9px 14px;
      transition: all 0.2s;
    }
    .search-box:focus-within {
      border-color: var(--border-focus);
      box-shadow: 0 0 16px rgba(0, 242, 254, 0.15);
    }
    .search-box input {
      background: transparent;
      border: none;
      color: var(--text-main);
      font-size: 0.86rem;
      outline: none;
      width: 100%;
      font-family: inherit;
    }
    .search-box input::placeholder { color: var(--text-dim); }

    /* Quick Filter Chips */
    .filter-chips {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .chip {
      padding: 6px 14px;
      border-radius: var(--radius-full);
      font-size: 0.78rem;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.15s;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .chip:hover {
      background: rgba(255, 255, 255, 0.1);
      color: var(--text-main);
    }
    .chip.active {
      background: rgba(0, 242, 254, 0.15);
      border-color: var(--accent-cyan);
      color: var(--accent-cyan);
      box-shadow: 0 0 12px rgba(0, 242, 254, 0.2);
    }
    .chip-badge {
      background: rgba(0, 0, 0, 0.35);
      padding: 1px 6px;
      border-radius: var(--radius-full);
      font-size: 0.7rem;
      font-family: 'JetBrains Mono', monospace;
    }

    .toolbar-row-bottom {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      padding-top: 10px;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
    }
    .filters-select-group {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .filter-select {
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      padding: 7px 12px;
      border-radius: var(--radius-md);
      font-size: 0.8rem;
      outline: none;
      cursor: pointer;
      font-family: inherit;
    }
    .filter-select:hover { border-color: rgba(255, 255, 255, 0.2); color: var(--text-main); }
    .filter-select:focus { border-color: var(--accent-cyan); }

    .view-switcher {
      display: flex;
      align-items: center;
      background: rgba(0, 0, 0, 0.3);
      padding: 3px;
      border-radius: var(--radius-md);
      border: 1px solid var(--border-color);
    }
    .view-btn {
      padding: 5px 12px;
      border-radius: var(--radius-sm);
      border: none;
      background: transparent;
      color: var(--text-muted);
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .view-btn.active {
      background: rgba(255, 255, 255, 0.1);
      color: #ffffff;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
    }

    /* BADGES (✨ MỚI, 📥 TỪ DRIVE, FILE EXTENSIONS) */
    .badge-new {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 3px 8px;
      border-radius: var(--radius-full);
      font-size: 0.68rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      background: var(--grad-new);
      color: #031326;
      box-shadow: 0 0 14px rgba(0, 242, 254, 0.5);
      animation: badgePulse 2s infinite ease-in-out;
      text-transform: uppercase;
    }
    @keyframes badgePulse {
      0%, 100% { transform: scale(1); box-shadow: 0 0 10px rgba(0, 242, 254, 0.4); }
      50% { transform: scale(1.04); box-shadow: 0 0 18px rgba(0, 242, 254, 0.7); }
    }

    .badge-drive-sync {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 3px 8px;
      border-radius: var(--radius-full);
      font-size: 0.68rem;
      font-weight: 700;
      background: rgba(16, 185, 129, 0.18);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.4);
    }

    .ext-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.7rem;
      font-weight: 700;
      padding: 4px 8px;
      border-radius: var(--radius-sm);
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    .ext-pdf { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.35); }
    .ext-docx { background: rgba(26, 115, 232, 0.15); color: #60a5fa; border: 1px solid rgba(26, 115, 232, 0.35); }
    .ext-pptx { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.35); }
    .ext-img { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.35); }
    .ext-txt { background: rgba(139, 92, 246, 0.15); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.35); }

    /* SUBJECT TAG COLORS */
    .tag-subject {
      display: inline-block;
      padding: 3px 9px;
      border-radius: var(--radius-full);
      font-size: 0.74rem;
      font-weight: 600;
      border: 1px solid transparent;
    }
    .tag-sub-toan { background: rgba(26, 115, 232, 0.15); color: #93c5fd; border-color: rgba(26, 115, 232, 0.3); }
    .tag-sub-triet { background: rgba(139, 92, 246, 0.15); color: #c084fc; border-color: rgba(139, 92, 246, 0.3); }
    .tag-sub-note { background: rgba(16, 185, 129, 0.15); color: #6ee7b7; border-color: rgba(16, 185, 129, 0.3); }
    .tag-sub-default { background: rgba(255, 255, 255, 0.08); color: var(--text-muted); border-color: var(--border-color); }

    .tag-type {
      display: inline-block;
      padding: 3px 9px;
      border-radius: var(--radius-full);
      font-size: 0.74rem;
      font-weight: 500;
      background: rgba(0, 242, 254, 0.08);
      color: #38bdf8;
      border: 1px solid rgba(0, 242, 254, 0.25);
    }

    /* CARD GRID VIEW */
    .cards-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 16px;
    }
    .file-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 18px;
      backdrop-filter: blur(16px);
      display: flex;
      flex-direction: column;
      gap: 12px;
      position: relative;
      overflow: hidden;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .file-card::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 3px;
      background: rgba(255, 255, 255, 0.1);
      transition: all 0.3s;
    }
    .file-card.is-new-card::before {
      background: var(--grad-new);
      box-shadow: 0 0 12px rgba(0, 242, 254, 0.6);
    }
    .file-card:hover {
      transform: translateY(-3px);
      border-color: rgba(255, 255, 255, 0.2);
      background: var(--bg-card-hover);
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.5);
    }
    .file-card:hover::before {
      background: var(--grad-studio);
    }

    .card-top {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 8px;
    }
    .card-badges {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }
    .card-title {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 0.95rem;
      font-weight: 700;
      color: #ffffff;
      line-height: 1.4;
      word-break: break-word;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .card-path {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      color: var(--text-dim);
      word-break: break-all;
    }
    .card-meta-row {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 4px;
    }
    .card-footer {
      margin-top: auto;
      padding-top: 12px;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .card-time-info {
      display: flex;
      flex-direction: column;
      gap: 2px;
      font-size: 0.72rem;
      color: var(--text-muted);
    }
    .card-size {
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;
      color: #cbd5e1;
    }

    /* TABLE VIEW */
    .table-container {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      backdrop-filter: blur(16px);
      overflow-x: auto;
      box-shadow: var(--shadow-glass);
      display: none; /* Controlled by JS toggle */
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.85rem;
    }
    th {
      background: rgba(255, 255, 255, 0.02);
      color: var(--text-muted);
      font-weight: 600;
      padding: 14px 18px;
      border-bottom: 1px solid var(--border-color);
      text-transform: uppercase;
      font-size: 0.72rem;
      letter-spacing: 0.06em;
      white-space: nowrap;
    }
    td {
      padding: 14px 18px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      vertical-align: middle;
    }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: rgba(255, 255, 255, 0.025); }
    tr.tr-new td {
      background: rgba(0, 242, 254, 0.02);
    }
    tr.tr-new td:first-child {
      border-left: 3px solid var(--accent-cyan);
    }

    .file-name-cell {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      max-width: 380px;
    }
    .file-info {
      display: flex;
      flex-direction: column;
      gap: 3px;
      overflow: hidden;
    }
    .file-title {
      font-weight: 600;
      color: #ffffff;
      word-break: break-word;
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .file-path {
      font-size: 0.72rem;
      color: var(--text-dim);
      font-family: 'JetBrains Mono', monospace;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .time-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 0.74rem;
      color: #cbd5e1;
      font-family: 'JetBrains Mono', monospace;
    }

    .action-btn-group {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .btn-icon {
      padding: 6px 10px;
      border-radius: var(--radius-sm);
      font-size: 0.76rem;
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
      padding: 20px;
    }
    .modal-box {
      background: #111522;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: var(--radius-lg);
      width: 100%;
      max-width: 520px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.7);
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
      font-size: 1.3rem;
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
      background: rgba(0, 0, 0, 0.35);
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
      background: rgba(0, 0, 0, 0.6);
      backdrop-filter: blur(8px);
      z-index: 900;
      display: none;
    }
    .drawer-panel {
      position: fixed;
      bottom: 0; left: 0; right: 0;
      height: 440px;
      background: #090c14;
      border-top: 1px solid rgba(0, 242, 254, 0.35);
      z-index: 901;
      display: none;
      flex-direction: column;
      box-shadow: 0 -10px 40px rgba(0,0,0,0.8);
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
      background: #05070c;
    }
    .log-line-info { color: #38bdf8; }
    .log-line-warn { color: #fbbf24; }
    .log-line-err { color: #f87171; }

    /* Toast */
    .toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      padding: 12px 20px;
      background: #141828;
      border: 1px solid rgba(0, 242, 254, 0.4);
      color: #ffffff;
      border-radius: var(--radius-md);
      font-size: 0.85rem;
      box-shadow: var(--shadow-glass);
      z-index: 2000;
      display: none;
      animation: toastIn 0.2s ease;
    }
    @keyframes toastIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  </style>
</head>
<body>

  <!-- Top Navigation -->
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
      <!-- Auto Sync Status Pill -->
      <div class="status-pill" id="autoSyncPill" onclick="triggerSyncDown()" title="Nhấn để kéo tài liệu từ Drive về ngay lập tức!">
        <div class="pulse-dot" id="autoSyncDot"></div>
        <span id="autoSyncText">🔄 Drive Auto-Pull: Đang kết nối...</span>
      </div>

      <button class="btn btn-secondary" onclick="openSettingsModal()">⚙️ Cài đặt</button>
      <button class="btn btn-secondary" onclick="toggleLogsDrawer()">📜 Live Logs</button>
      <button class="btn btn-sync" onclick="triggerSyncDown()" id="btnSyncDown">📥 Kéo từ Drive về ngay</button>
      <button class="btn btn-primary" onclick="triggerScan()" id="btnScan">⚡ Quét máy tính</button>
    </div>
  </header>

  <!-- Main Content -->
  <main>
    <!-- Stats Row -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-header">
          <span>Tổng tài liệu</span>
          <span class="stat-icon">📁</span>
        </div>
        <div class="stat-value" id="statTotalFiles">0</div>
        <div class="stat-subtitle" id="statStoragePath">Thư mục: H:\\2026\\Thac Sy\\Mon_Hoc</div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span>Đã đồng bộ Drive</span>
          <span class="stat-icon" style="color: var(--accent-green);">☁️</span>
        </div>
        <div class="stat-value" id="statUploaded" style="color: var(--accent-green);">0</div>
        <div class="stat-subtitle">Thư mục gốc: ThacSi_HTTT</div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span>Tài liệu mới (<24h)</span>
          <span class="stat-icon" style="color: var(--accent-cyan);">✨</span>
        </div>
        <div class="stat-value" id="statNewCount" style="color: var(--accent-cyan);">0</div>
        <div class="stat-subtitle" id="statNewSubtitle">Tự động nhận diện thời gian</div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span>Môn học theo dõi</span>
          <span class="stat-icon" style="color: var(--accent-purple);">🎓</span>
        </div>
        <div class="stat-value" id="statSubjectsCount" style="color: var(--accent-purple);">0</div>
        <div class="stat-subtitle" id="statSubjectsList">Toán KH Dữ liệu, Triết học...</div>
      </div>
    </div>

    <!-- Toolbar: Search, Filter Tabs & View Mode Switcher -->
    <div class="toolbar-container">
      <div class="toolbar-row-top">
        <div class="search-box">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <input type="text" id="searchInput" placeholder="Tìm kiếm tài liệu theo tên, môn học, hash..." oninput="applyFilters()">
        </div>

        <div class="filter-chips">
          <div class="chip active" id="chipAll" onclick="setQuickFilter('ALL')">
            🔥 Tất cả <span class="chip-badge" id="countAll">0</span>
          </div>
          <div class="chip" id="chipNew" onclick="setQuickFilter('NEW')">
            ✨ Mới nhất (<24h) <span class="chip-badge" id="countNew">0</span>
          </div>
          <div class="chip" id="chipDrive" onclick="setQuickFilter('DRIVE')">
            📥 Từ Google Drive <span class="chip-badge" id="countDrive">0</span>
          </div>
        </div>
      </div>

      <div class="toolbar-row-bottom">
        <div class="filters-select-group">
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
            <option value="NEWEST">⏱️ Mới nhất trước (Mặc định)</option>
            <option value="OLDEST">⏳ Cũ nhất trước</option>
            <option value="NAME">🔤 Tên file A-Z</option>
            <option value="SIZE">💾 Dung lượng lớn nhất</option>
          </select>
        </div>

        <div class="view-switcher">
          <button class="view-btn active" id="btnViewCards" onclick="setViewMode('cards')">
            🎴 Dạng Thẻ
          </button>
          <button class="view-btn" id="btnViewTable" onclick="setViewMode('table')">
            📑 Dạng Bảng
          </button>
        </div>
      </div>
    </div>

    <!-- 1. CARDS GRID VIEW -->
    <div class="cards-grid" id="cardsContainer">
      <!-- Injected via JavaScript -->
    </div>

    <!-- 2. TABLE VIEW -->
    <div class="table-container" id="tableContainer">
      <table>
        <thead>
          <tr>
            <th>Tập tin tài liệu</th>
            <th>Môn học</th>
            <th>Phân loại</th>
            <th>Dung lượng</th>
            <th>Cập nhật / Thời gian</th>
            <th>Trạng thái</th>
            <th style="text-align: right;">Thao tác</th>
          </tr>
        </thead>
        <tbody id="filesTableBody">
          <!-- Injected via JavaScript -->
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
          💡 Khi bạn bấm <b>Lưu phân loại</b>, hệ thống sẽ tự động cập nhật vào SQLite và chuyển thư mục tương ứng trên Google Drive!
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
        <div class="modal-title">⚙️ Cài đặt hệ thống Studio</div>
        <button class="modal-close" onclick="closeSettingsModal()">&times;</button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label class="form-label">Tự động kéo tài liệu từ Google Drive:</label>
          <div style="display: flex; align-items: center; gap: 12px; background: rgba(255,255,255,0.03); padding: 12px; border-radius: 10px; border: 1px solid var(--border-color);">
            <input type="checkbox" id="cfgAutoSync" style="width: 18px; height: 18px; accent-color: var(--accent-cyan); cursor: pointer;">
            <div>
              <div style="font-size: 0.85rem; font-weight: 600; color: #fff;">Bật đồng bộ tự động nền (Auto-Pull)</div>
              <div style="font-size: 0.75rem; color: var(--text-dim);">Tự động phát hiện và kéo tài liệu mới tải lên Drive về máy</div>
            </div>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Chu kỳ tự động kéo từ Drive (phút):</label>
          <input type="number" id="cfgSyncIntervalMins" class="form-control" min="1" max="60" value="3">
        </div>

        <div class="form-group">
          <label class="form-label">Thư mục nguồn (Source of Truth):</label>
          <input type="text" id="cfgRootFolder" class="form-control">
        </div>

        <div class="form-group">
          <label class="form-label">Định dạng file theo dõi:</label>
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
        <span class="pulse-dot"></span> Nhật ký ứng dụng trực tiếp (Live App Logs)
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

    function getSubjectClass(subject) {
      if (!subject) return 'tag-sub-default';
      const s = subject.toLowerCase();
      if (s.includes('toán') || s.includes('toan')) return 'tag-sub-toan';
      if (s.includes('triết') || s.includes('triet')) return 'tag-sub-triet';
      if (s.includes('ghi chú') || s.includes('phuong phap')) return 'tag-sub-note';
      return 'tag-sub-default';
    }

    function formatRelativeTime(isoStr) {
      if (!isoStr) return '--';
      try {
        const d = new Date(isoStr);
        const now = new Date();
        const diffMs = now - d;
        const diffSecs = Math.floor(diffMs / 1000);
        if (diffSecs < 60) return 'Vừa xong';
        if (diffSecs < 3600) return `${Math.floor(diffSecs / 60)} phút trước`;
        if (diffSecs < 86400) return `${Math.floor(diffSecs / 3600)} giờ trước`;
        if (diffSecs < 172800) return `Hôm qua ${d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`;
        return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
      } catch (e) {
        return isoStr;
      }
    }

    async function loadStats() {
      try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        document.getElementById('statTotalFiles').textContent = data.total_files || 0;
        document.getElementById('statUploaded').textContent = data.uploaded_files || 0;
        document.getElementById('statSubjectsCount').textContent = data.subjects_count || 0;

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

        // Auto Sync Status Info
        if (data.auto_sync) {
          const sync = data.auto_sync;
          const statusText = document.getElementById('autoSyncText');
          const dot = document.getElementById('autoSyncDot');
          if (sync.enabled) {
            dot.style.display = 'block';
            statusText.innerHTML = `🔄 <b>Auto-Pull:</b> ${sync.interval_minutes}p/lần • ${sync.last_sync_human || 'Sẵn sàng'}`;
          } else {
            dot.style.display = 'none';
            statusText.innerHTML = `⏸️ Drive Auto-Pull: Tắt`;
          }
        }
      } catch (err) {
        console.error('Lỗi tải stats:', err);
      }
    }

    async function loadFiles() {
      try {
        const res = await fetch('/api/files');
        allFiles = await res.json();

        // Update counts
        const newFiles = allFiles.filter(f => f.is_new);
        const driveFiles = allFiles.filter(f => f.is_from_drive || (f.drive_file_id && f.path.includes('Mon_Hoc')));

        document.getElementById('countAll').textContent = allFiles.length;
        document.getElementById('countNew').textContent = newFiles.length;
        document.getElementById('countDrive').textContent = driveFiles.length;
        document.getElementById('statNewCount').textContent = newFiles.length;

        applyFilters();
      } catch (err) {
        console.error('Lỗi tải files:', err);
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

      // Sorting
      if (sortBy === 'NEWEST') {
        filtered.sort((a, b) => (b.id || 0) - (a.id || 0));
      } else if (sortBy === 'OLDEST') {
        filtered.sort((a, b) => (a.id || 0) - (b.id || 0));
      } else if (sortBy === 'NAME') {
        filtered.sort((a, b) => a.path.localeCompare(b.path));
      } else if (sortBy === 'SIZE') {
        filtered.sort((a, b) => (b.size_bytes || 0) - (a.size_bytes || 0));
      }

      if (currentViewMode === 'cards') {
        renderCards(filtered);
      } else {
        renderTable(filtered);
      }
    }

    function renderCards(files) {
      const container = document.getElementById('cardsContainer');
      if (!files || files.length === 0) {
        container.innerHTML = `
          <div style="grid-column: 1/-1; text-align: center; color: var(--text-dim); padding: 48px; background: var(--bg-card); border-radius: var(--radius-lg);">
            Không tìm thấy tài liệu nào phù hợp với bộ lọc hiện tại.
          </div>`;
        return;
      }

      let html = '';
      files.forEach(f => {
        const fileName = f.path.split(/[\\\\/]/).pop();
        const shortHash = f.sha256 ? f.sha256.substring(0, 10) + '...' : '-';
        const relTime = formatRelativeTime(f.updated_at || f.created_at);

        const newBadge = f.is_new ? `<span class="badge-new">✨ MỚI</span>` : '';
        const driveSyncBadge = f.is_from_drive ? `<span class="badge-drive-sync">📥 DRIVE SYNC</span>` : '';
        const driveBtn = f.drive_file_id 
          ? `<a href="https://drive.google.com/file/d/${f.drive_file_id}/view" target="_blank" class="btn-icon btn-icon-drive" title="Mở trực tiếp trên Google Drive">🔗 Drive</a>`
          : '';

        html += `
          <div class="file-card ${f.is_new ? 'is-new-card' : ''}">
            <div class="card-top">
              <div class="card-badges">
                ${getExtBadge(fileName)}
                ${newBadge}
                ${driveSyncBadge}
              </div>
              <button class="btn-icon" style="padding: 2px 6px;" title="Sao chép SHA-256" onclick="navigator.clipboard.writeText('${f.sha256 || ''}'); showToast('Đã sao chép SHA-256!');">
                📋
              </button>
            </div>

            <div class="card-title" title="${fileName}">${fileName}</div>
            <div class="card-path" title="${f.path}">${f.path}</div>

            <div class="card-meta-row">
              <span class="tag-subject ${getSubjectClass(f.subject)}">${f.subject || 'Chưa phân loại'}</span>
              <span class="tag-type">${f.document_type || 'Tài liệu'}</span>
            </div>

            <div class="card-footer">
              <div class="card-time-info">
                <span class="card-size">💾 ${f.size_formatted || '--'}</span>
                <span>⏱️ ${relTime}</span>
              </div>
              <div class="action-btn-group">
                ${driveBtn}
                <button class="btn-icon" onclick="openEditModal(${f.id}, '${encodeURIComponent(fileName)}', '${encodeURIComponent(f.subject || '')}', '${encodeURIComponent(f.document_type || '')}')">✏️ Sửa tay</button>
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
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 48px;">Không tìm thấy tài liệu nào phù hợp.</td></tr>`;
        return;
      }

      let html = '';
      files.forEach(f => {
        const fileName = f.path.split(/[\\\\/]/).pop();
        const shortHash = f.sha256 ? f.sha256.substring(0, 10) + '...' : '-';
        const relTime = formatRelativeTime(f.updated_at || f.created_at);

        const newBadge = f.is_new ? `<span class="badge-new">✨ MỚI</span>` : '';
        const driveSyncBadge = f.is_from_drive ? `<span class="badge-drive-sync">📥 DRIVE SYNC</span>` : '';

        let statusBadge = '<span class="status-badge status-uploaded">● ĐÃ UPLOAD</span>';
        if (f.status === 'DUPLICATE') statusBadge = '<span class="status-badge status-duplicate">● TRÙNG LẶP</span>';
        if (f.status === 'ERROR') statusBadge = `<span class="status-badge status-error" title="${f.error || ''}">● LỖI</span>`;

        const driveBtn = f.drive_file_id 
          ? `<a href="https://drive.google.com/file/d/${f.drive_file_id}/view" target="_blank" class="btn-icon btn-icon-drive" title="Mở trên Google Drive">🔗 Drive</a>`
          : '';

        html += `
          <tr class="${f.is_new ? 'tr-new' : ''}">
            <td>
              <div class="file-name-cell">
                ${getExtBadge(fileName)}
                <div class="file-info">
                  <div class="file-title">
                    ${fileName}
                    ${newBadge}
                    ${driveSyncBadge}
                  </div>
                  <div class="file-path">${f.path}</div>
                </div>
              </div>
            </td>
            <td><span class="tag-subject ${getSubjectClass(f.subject)}">${f.subject || 'Chưa phân loại'}</span></td>
            <td><span class="tag-type">${f.document_type || 'Chung'}</span></td>
            <td><span style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #cbd5e1;">${f.size_formatted || '--'}</span></td>
            <td>
              <div class="time-badge" title="${f.updated_at || f.created_at || ''}">
                ⏱️ ${relTime}
              </div>
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
          showToast('✅ Đã lưu phân loại và cập nhật Google Drive!');
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
          btn.textContent = '⚡ Quét máy tính';
          btn.disabled = false;
        }, 1200);
      } catch (err) {
        alert('Lỗi quét: ' + err);
        btn.textContent = '⚡ Quét máy tính';
        btn.disabled = false;
      }
    }

    async function triggerSyncDown() {
      const btn = document.getElementById('btnSyncDown');
      btn.textContent = '⏳ Đang kéo từ Drive...';
      btn.disabled = true;
      try {
        const res = await fetch('/api/sync-down', { method: 'POST' });
        const data = await res.json();
        if (data.ok) {
          if (data.count > 0) {
            showToast(`🎉 Đã kéo thành công ${data.count} tài liệu mới từ Drive về máy!`);
          } else {
            showToast('👌 Máy tính đã đồng bộ hoàn toàn với Drive (Không có file mới).');
          }
          loadStats();
          loadFiles();
        } else {
          alert('Lỗi kéo từ Drive: ' + (data.error || 'Không rõ'));
        }
      } catch (err) {
        alert('Lỗi mạng: ' + err);
      } finally {
        btn.textContent = '📥 Kéo từ Drive về ngay';
        btn.disabled = false;
      }
    }

    async function openSettingsModal() {
      try {
        const res = await fetch('/api/config');
        const cfg = await res.json();
        document.getElementById('cfgRootFolder').value = cfg.root_folder || '';
        document.getElementById('cfgWaitSecs').value = cfg.stable_file_wait_seconds || 3;
        document.getElementById('cfgAutoSync').checked = cfg.auto_sync_drive !== false;
        document.getElementById('cfgSyncIntervalMins').value = cfg.drive_sync_interval_minutes || 3;

        const exts = cfg.supported_extensions || [];
        document.getElementById('extPdf').checked = exts.includes('.pdf');
        document.getElementById('extDocx').checked = exts.includes('.docx');
        document.getElementById('extPptx').checked = exts.includes('.pptx');
        document.getElementById('extTxt').checked = exts.includes('.txt');
        document.getElementById('extMd').checked = exts.includes('.md');
        document.getElementById('extJpg').checked = exts.includes('.jpg');
        document.getElementById('extJpeg').checked = exts.includes('.jpeg');
        document.getElementById('extPng').checked = exts.includes('.png');

        document.getElementById('settingsModal').style.display = 'flex';
      } catch (err) {
        alert('Không thể tải cấu hình: ' + err);
      }
    }

    function closeSettingsModal() {
      document.getElementById('settingsModal').style.display = 'none';
    }

    async function saveSettings() {
      const rootFolder = document.getElementById('cfgRootFolder').value.trim();
      const waitSecs = parseInt(document.getElementById('cfgWaitSecs').value);
      const autoSync = document.getElementById('cfgAutoSync').checked;
      const intervalMins = parseInt(document.getElementById('cfgSyncIntervalMins').value) || 3;

      const exts = [];
      ['extPdf', 'extDocx', 'extPptx', 'extTxt', 'extMd', 'extJpg', 'extJpeg', 'extPng'].forEach(id => {
        const el = document.getElementById(id);
        if (el && el.checked) exts.push(el.value);
      });

      const body = {
        root_folder: rootFolder,
        stable_file_wait_seconds: waitSecs,
        supported_extensions: exts,
        auto_sync_drive: autoSync,
        drive_sync_interval_minutes: intervalMins,
      };

      try {
        const res = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        const resJson = await res.json();
        if (resJson.ok) {
          showToast('✅ Đã lưu cài đặt hệ thống!');
          closeSettingsModal();
          loadStats();
        } else {
          alert('Lỗi lưu cấu hình: ' + resJson.error);
        }
      } catch (err) {
        alert('Lỗi mạng khi lưu cấu hình: ' + err);
      }
    }

    function toggleLogsDrawer() {
      const drawer = document.getElementById('logsDrawer');
      const backdrop = document.getElementById('drawerBackdrop');
      if (drawer.style.display === 'flex') {
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

    // Auto-refresh periodically (every 10s)
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
    classifier: Optional[Any] = None
    auto_sync_worker: Optional[Any] = None

    def log_message(self, format: str, *args: Any) -> None:
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
            unique_files: Dict[str, Any] = {}
            for r in records:
                p = r["path"]
                if p not in unique_files or r.get("status") == "UPLOADED":
                    unique_files[p] = r

            file_list = list(unique_files.values())
            total = len(file_list)
            uploaded = sum(1 for r in file_list if r.get("status") == "UPLOADED")
            duplicate = sum(1 for r in file_list if r.get("status") == "DUPLICATE")
            error = sum(1 for r in file_list if r.get("status") == "ERROR")

            subjects = sorted(list({r["subject"] for r in file_list if r.get("subject")}))

            auto_sync_info = (
                self.auto_sync_worker.get_status_info()
                if self.auto_sync_worker
                else {
                    "enabled": True,
                    "interval_minutes": 3,
                    "is_syncing": False,
                    "last_sync_time": None,
                    "last_sync_human": "Chưa chạy",
                    "last_sync_status": "Sẵn sàng",
                }
            )

            self._send_json({
                "total_files": total,
                "uploaded_files": uploaded,
                "duplicate_files": duplicate,
                "error_files": error,
                "subjects_count": len(subjects),
                "subjects": subjects,
                "drive_connected": self.drive_manager.is_configured() if self.drive_manager else False,
                "auto_sync": auto_sync_info,
            })
            return

        if path == "/api/files":
            if not self.database:
                self._send_json([], 500)
                return
            records = self.database.get_all_records(limit=1000)
            unique_files: Dict[str, Any] = {}
            for r in records:
                p = r["path"]
                if p not in unique_files:
                    unique_files[p] = r
                elif r.get("status") == "UPLOADED" and unique_files[p].get("status") != "UPLOADED":
                    unique_files[p] = r

            file_list = list(unique_files.values())
            file_list.sort(key=lambda x: x.get("id", 0), reverse=True)

            now_ts = time.time()
            recent_drive_ids = set()
            if self.auto_sync_worker:
                recent_drive_ids = set(self.auto_sync_worker.recently_downloaded_ids)

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
                f["is_from_drive"] = bool(f.get("drive_file_id") in recent_drive_ids)

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

                # Di chuyển file trên Drive nếu sẵn sàng
                if self.drive_manager and self.drive_manager.is_configured() and record.get("drive_file_id"):
                    try:
                        target_folder_id = self.drive_manager.resolve_folder_hierarchy(
                            subject=new_subject,
                            document_type=new_type,
                        )
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

                # Cập nhật worker nếu có
                worker = getattr(DashboardRequestHandler, "auto_sync_worker", None)
                if worker:
                    enabled = body.get("auto_sync_drive")
                    mins = body.get("drive_sync_interval_minutes")
                    secs = int(mins) * 60 if mins is not None else None
                    worker.update_settings(enabled=enabled, interval_seconds=secs)

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

        if path == "/api/sync-down":
            from src.sync import sync_from_drive_to_local
            try:
                worker = getattr(DashboardRequestHandler, "auto_sync_worker", None)
                if worker:
                    downloaded = worker.trigger_now()
                else:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    root_folder = Path(cfg["root_folder"])
                    classifier = getattr(DashboardRequestHandler, "classifier", None)
                    downloaded = sync_from_drive_to_local(
                        drive_manager=DashboardRequestHandler.drive_manager,
                        database=DashboardRequestHandler.database,
                        root_folder=root_folder,
                        classifier=classifier,
                    )
                self._send_json({"ok": True, "count": len(downloaded), "files": downloaded})
                return
            except Exception as exc:
                logger.error("Lỗi khi đồng bộ từ Drive về: %s", exc, exc_info=True)
                self._send_json({"ok": False, "error": str(exc)}, 500)
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
