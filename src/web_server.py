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
    """Trả về giao diện Web ThsAutoOrganizer Studio Responsive đa thiết bị (Desktop, iPad, Mobile)."""
    return """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>ThsAutoOrganizer – Hệ Thống Hóa Học Tập & Quản Lý Tài Liệu Số | Studio Edition</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-base: #111113;
      --bg-sidebar: #141416;
      --bg-main: #111113;
      --bg-surface: #18181B;
      --bg-card: #18181B;
      --bg-card-hover: #222226;
      --bg-subtle: #222226;
      --border-color: rgba(255, 255, 255, 0.08);
      --border-subtle: rgba(255, 255, 255, 0.08);
      --border-focus: rgba(255, 255, 255, 0.22);
      --text-main: #F4F4F5;
      --text-primary: #F4F4F5;
      --text-muted: #A1A1AA;
      --text-secondary: #A1A1AA;
      --text-dim: #71717A;
      --text-tertiary: #71717A;

      --accent-purple: #A855F7;
      --accent-emerald: #10B981;
      --accent-amber: #F59E0B;
      --accent-red: #EF4444;
      --accent-blue: #3B82F6;
      --accent-cyan: #A855F7;
      --accent-green: #10B981;

      --radius-sm: 6px;
      --radius-md: 8px;
      --radius-lg: 12px;
      --radius-xl: 16px;
      --radius-full: 9999px;
      --shadow-glass: 0 4px 20px rgba(0, 0, 0, 0.4);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg-base);
      color: var(--text-main);
      min-height: 100vh;
      overflow-x: hidden;
    }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: var(--bg-base); }
    ::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.15); border-radius: var(--radius-full); }

    /* Layout: Fixed Left Sidebar + Main Content */
    .app-layout {
      display: flex;
      min-height: 100vh;
      width: 100vw;
      position: relative;
    }

    /* ==================== LEFT SIDEBAR ==================== */
    .ths-sidebar {
      width: 240px;
      min-width: 240px;
      background: var(--bg-sidebar);
      border-right: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      position: sticky;
      top: 0;
      height: 100vh;
      z-index: 200;
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      user-select: none;
    }

    .ths-sidebar.collapsed {
      width: 72px;
      min-width: 72px;
    }

    .sidebar-brand {
      padding: 20px 18px 16px;
      display: flex;
      align-items: center;
      gap: 10px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }
    .brand-logo-circle {
      width: 38px;
      height: 38px;
      border-radius: 50%;
      background: linear-gradient(135deg, #0ea5e9, #6366f1, #a855f7);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 16px rgba(14, 165, 233, 0.5);
      flex-shrink: 0;
    }
    .brand-logo-circle svg { width: 22px; height: 22px; fill: white; }
    .brand-title-group {
      display: flex;
      align-items: baseline;
      gap: 6px;
      overflow: hidden;
      white-space: nowrap;
    }
    .brand-title-text {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-weight: 800;
      font-size: 1.25rem;
      letter-spacing: -0.5px;
      color: #ffffff;
    }
    .brand-lang-badge {
      display: flex;
      align-items: center;
      background: rgba(255, 255, 255, 0.08);
      border-radius: var(--radius-full);
      padding: 2px 6px;
      font-size: 0.65rem;
      font-weight: 700;
      color: #94a3b8;
      gap: 4px;
      margin-left: auto;
    }
    .brand-lang-badge span.active { color: var(--accent-cyan); }

    .ths-sidebar.collapsed .brand-title-group,
    .ths-sidebar.collapsed .brand-lang-badge {
      display: none;
    }

    /* Navigation */
    .sidebar-nav {
      padding: 16px 10px;
      flex: 1;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .nav-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 14px;
      border-radius: var(--radius-md);
      color: var(--text-muted);
      font-size: 0.86rem;
      font-weight: 600;
      text-decoration: none;
      transition: all 0.2s;
      cursor: pointer;
      position: relative;
    }
    .nav-item:hover {
      background: rgba(255, 255, 255, 0.05);
      color: #ffffff;
    }
    .nav-item.active {
      background: rgba(0, 242, 254, 0.1);
      color: var(--accent-cyan);
      border-left: 3px solid var(--accent-cyan);
    }
    .nav-item .nav-icon {
      font-size: 1.15rem;
      width: 22px;
      text-align: center;
      flex-shrink: 0;
    }
    .nav-badge-ver {
      margin-left: auto;
      font-size: 0.68rem;
      padding: 2px 6px;
      border-radius: var(--radius-full);
      background: rgba(255, 255, 255, 0.08);
      color: var(--text-dim);
      font-family: 'JetBrains Mono', monospace;
    }

    .nav-section-title {
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 1px;
      font-weight: 700;
      color: var(--text-dim);
      padding: 18px 14px 6px;
    }

    .ths-sidebar.collapsed .nav-label,
    .ths-sidebar.collapsed .nav-badge-ver,
    .ths-sidebar.collapsed .nav-section-title {
      display: none;
    }
    .ths-sidebar.collapsed .nav-item {
      justify-content: center;
      padding: 12px;
    }

    /* Sidebar Footer */
    .sidebar-footer {
      padding: 12px 14px;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .sidebar-collapse-btn {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      font-size: 0.8rem;
      transition: all 0.2s;
      align-self: flex-start;
    }
    .sidebar-collapse-btn:hover {
      background: rgba(255, 255, 255, 0.1);
      color: #fff;
    }
    .ths-sidebar.collapsed .sidebar-collapse-btn {
      align-self: center;
      transform: rotate(180deg);
    }

    .btn-sidebar-auth {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: var(--radius-md);
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--accent-cyan);
      background: rgba(0, 242, 254, 0.08);
      border: 1px solid rgba(0, 242, 254, 0.25);
      cursor: pointer;
      width: 100%;
      justify-content: center;
      transition: all 0.2s;
    }
    .btn-sidebar-auth:hover {
      background: rgba(0, 242, 254, 0.16);
      border-color: var(--accent-cyan);
    }
    .ths-sidebar.collapsed .btn-sidebar-auth span.text { display: none; }

    /* ==================== MAIN CONTENT AREA ==================== */
    .ths-main-area {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
      background: var(--bg-main);
      background-image: var(--grad-glow);
      background-attachment: fixed;
      min-height: 100vh;
      overflow-y: auto;
    }

    /* Top Bar */
    .ths-topbar {
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      background: rgba(7, 11, 22, 0.8);
      border-bottom: 1px solid var(--border-color);
      padding: 12px 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    .topbar-left {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .mobile-menu-toggle {
      display: none;
      background: none;
      border: none;
      color: #fff;
      font-size: 1.4rem;
      cursor: pointer;
    }
    .topbar-subtitle {
      font-size: 0.82rem;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .badge-edition {
      font-size: 0.65rem;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: var(--radius-full);
      background: rgba(0, 242, 254, 0.15);
      color: var(--accent-cyan);
      border: 1px solid rgba(0, 242, 254, 0.3);
      text-transform: uppercase;
    }

    .topbar-right {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    /* Buttons */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 8px 16px;
      border-radius: var(--radius-md);
      font-size: 0.84rem;
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
      box-shadow: 0 2px 14px rgba(0, 242, 254, 0.25);
    }
    .btn-primary:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 20px rgba(0, 242, 254, 0.45);
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

    /* User Profile Chip */
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
      border-color: rgba(0, 242, 254, 0.4);
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
      font-size: 0.8rem;
      color: #fff;
    }
    .user-name-text {
      font-size: 0.82rem;
      font-weight: 600;
      max-width: 140px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    /* Google One-Tap Quick Widget */
    .google-onetap-widget {
      position: absolute;
      top: 64px;
      right: 28px;
      width: 320px;
      background: #1e2433;
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-radius: var(--radius-md);
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.6);
      padding: 14px;
      z-index: 150;
      animation: fadeInDown 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    }
    @keyframes fadeInDown {
      from { opacity: 0; transform: translateY(-10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .onetap-header {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.76rem;
      color: var(--text-muted);
      margin-bottom: 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding-bottom: 8px;
    }
    .onetap-user-item {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px;
      border-radius: var(--radius-sm);
      cursor: pointer;
      transition: background 0.15s;
    }
    .onetap-user-item:hover {
      background: rgba(255, 255, 255, 0.08);
    }
    .onetap-avatar {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 0.85rem;
      color: #fff;
    }
    .onetap-info {
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .onetap-name { font-size: 0.82rem; font-weight: 600; color: #fff; }
    .onetap-email { font-size: 0.72rem; color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

    /* ==================== VIEW 1: HOMEPAGE VIEW ==================== */
    .view-content {
      padding: 32px 36px 60px;
      max-width: 1400px;
      width: 100%;
      margin: 0 auto;
    }

    /* Hero Section */
    .ths-hero-section {
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 40px;
      align-items: center;
      padding: 20px 0 50px;
      position: relative;
    }

    .hero-content-left {
      display: flex;
      flex-direction: column;
      gap: 16px;
      z-index: 2;
    }
    .hero-title {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 2.75rem;
      font-weight: 800;
      line-height: 1.2;
      color: #ffffff;
      letter-spacing: -1px;
    }
    .gradient-text-hero {
      background: var(--grad-hero-text);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .hero-subtitle-en {
      font-size: 1.1rem;
      font-weight: 600;
      color: #cbd5e1;
      margin-top: -6px;
    }
    .hero-description {
      font-size: 0.92rem;
      line-height: 1.65;
      color: var(--text-muted);
      max-width: 580px;
    }

    /* Dual Action Cards */
    .dual-action-cards {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-top: 14px;
    }
    .action-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 18px 20px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      cursor: pointer;
      position: relative;
      overflow: hidden;
      backdrop-filter: blur(16px);
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .action-card:hover {
      transform: translateY(-3px);
      border-color: rgba(255, 255, 255, 0.2);
    }
    .action-card.card-cyan:hover {
      border-color: rgba(0, 242, 254, 0.45);
      box-shadow: var(--shadow-glow-cyan);
    }
    .action-card.card-purple:hover {
      border-color: rgba(139, 92, 246, 0.45);
      box-shadow: var(--shadow-glow-purple);
    }

    .action-card-badge-icon {
      width: 36px;
      height: 36px;
      border-radius: var(--radius-md);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.1rem;
    }
    .badge-icon-cyan {
      background: rgba(0, 242, 254, 0.12);
      color: var(--accent-cyan);
      border: 1px solid rgba(0, 242, 254, 0.25);
    }
    .badge-icon-purple {
      background: rgba(139, 92, 246, 0.12);
      color: var(--accent-purple);
      border: 1px solid rgba(139, 92, 246, 0.25);
    }

    .action-card-title {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 0.98rem;
      font-weight: 700;
      color: #ffffff;
    }
    .action-card-desc {
      font-size: 0.78rem;
      color: var(--text-dim);
      line-height: 1.45;
    }
    .action-card-arrow {
      margin-top: 6px;
      align-self: flex-end;
      font-size: 1.2rem;
      transition: transform 0.2s;
    }
    .action-card:hover .action-card-arrow {
      transform: translateX(4px);
    }
    .arrow-cyan { color: var(--accent-cyan); }
    .arrow-purple { color: var(--accent-purple); }

    /* Cosmic Rocket Artwork (Hero Right) */
    .hero-content-right {
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 360px;
    }
    .cosmic-artwork-container {
      position: relative;
      width: 100%;
      max-width: 440px;
      height: 380px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .art-glow-nebula {
      position: absolute;
      width: 340px;
      height: 340px;
      background: radial-gradient(circle, rgba(139, 92, 246, 0.3) 0%, rgba(14, 165, 233, 0.2) 50%, transparent 70%);
      border-radius: 50%;
      filter: blur(40px);
      animation: pulseGlow 8s infinite alternate ease-in-out;
    }
    @keyframes pulseGlow {
      0% { transform: scale(0.9); opacity: 0.6; }
      100% { transform: scale(1.15); opacity: 0.9; }
    }

    .art-orbit-ring {
      position: absolute;
      border: 1px solid rgba(139, 92, 246, 0.25);
      border-radius: 50%;
      transform: rotate(-30deg);
    }
    .ring-1 { width: 320px; height: 180px; border-color: rgba(14, 165, 233, 0.35); }
    .ring-2 { width: 420px; height: 240px; border-color: rgba(139, 92, 246, 0.25); }

    .rocket-svg {
      width: 260px;
      height: 260px;
      z-index: 2;
      filter: drop-shadow(0 0 30px rgba(139, 92, 246, 0.6));
      animation: rocketHover 6s infinite ease-in-out;
    }
    @keyframes rocketHover {
      0%, 100% { transform: translateY(0) rotate(0deg); }
      50% { transform: translateY(-10px) rotate(1.5deg); }
    }

    /* THỬ NGAY Interactive Section */
    .ths-tester-section {
      background: linear-gradient(180deg, rgba(16, 23, 42, 0.6) 0%, rgba(10, 15, 28, 0.8) 100%);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: var(--radius-xl);
      padding: 36px 40px;
      margin-top: 30px;
      position: relative;
      overflow: hidden;
    }
    .ths-tester-section::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 2px;
      background: var(--grad-studio);
    }

    .tester-tag-label {
      font-size: 0.72rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      color: var(--accent-cyan);
      margin-bottom: 6px;
    }
    .tester-title {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 1.65rem;
      font-weight: 800;
      color: #ffffff;
      margin-bottom: 4px;
    }
    .tester-sub-en {
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 12px;
    }
    .tester-desc {
      font-size: 0.86rem;
      line-height: 1.6;
      color: var(--text-muted);
      max-width: 760px;
      margin-bottom: 22px;
    }

    .tester-input-bar {
      display: flex;
      align-items: center;
      gap: 12px;
      background: rgba(4, 7, 16, 0.75);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: var(--radius-md);
      padding: 6px 6px 6px 16px;
      box-shadow: inset 0 2px 6px rgba(0,0,0,0.4);
      transition: border-color 0.2s;
    }
    .tester-input-bar:focus-within {
      border-color: var(--accent-cyan);
      box-shadow: 0 0 16px rgba(0, 242, 254, 0.25);
    }
    .tester-input {
      flex: 1;
      background: transparent;
      border: none;
      color: #fff;
      font-size: 0.9rem;
      font-family: inherit;
      outline: none;
    }
    .tester-btn {
      background: var(--grad-studio);
      color: #ffffff;
      border: none;
      border-radius: var(--radius-sm);
      padding: 10px 20px;
      font-weight: 700;
      font-size: 0.84rem;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s;
      white-space: nowrap;
    }
    .tester-btn:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 16px rgba(0, 242, 254, 0.4);
    }

    /* Samples chips */
    .tester-samples {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 14px;
      flex-wrap: wrap;
    }
    .tester-samples-label {
      font-size: 0.74rem;
      color: var(--text-dim);
      font-weight: 600;
    }
    .sample-chip {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-full);
      padding: 4px 10px;
      font-size: 0.72rem;
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.15s;
    }
    .sample-chip:hover {
      background: rgba(0, 242, 254, 0.12);
      border-color: var(--accent-cyan);
      color: #fff;
    }

    /* AI Live Result Preview Card */
    .tester-result-box {
      margin-top: 20px;
      background: rgba(8, 12, 24, 0.9);
      border: 1px solid rgba(0, 242, 254, 0.3);
      border-radius: var(--radius-md);
      padding: 16px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
      animation: fadeInDown 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .result-info-left {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .result-subject-title {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 1rem;
      font-weight: 800;
      color: #ffffff;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .result-path-text {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      color: var(--accent-cyan);
    }
    .result-tags-right {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    /* Feature Grid */
    .ths-features-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 18px;
      margin-top: 36px;
    }
    .feature-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 22px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      transition: all 0.2s;
    }
    .feature-card:hover {
      border-color: rgba(255, 255, 255, 0.18);
      background: var(--bg-card-hover);
      transform: translateY(-2px);
    }
    .feature-icon-wrapper {
      width: 42px;
      height: 42px;
      border-radius: var(--radius-md);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.3rem;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-color);
    }
    .feature-title {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 0.98rem;
      font-weight: 700;
      color: #ffffff;
    }
    .feature-desc {
      font-size: 0.8rem;
      color: var(--text-muted);
      line-height: 1.5;
    }

    /* ==================== VIEW 2: WORKSPACE VIEW ==================== */
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
      margin-bottom: 24px;
    }
    .upload-banner-text { display: flex; flex-direction: column; gap: 2px; }
    .upload-banner-title {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-weight: 700;
      font-size: 0.98rem;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .upload-banner-sub { font-size: 0.78rem; color: var(--text-muted); }
    .upload-btn-group { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

    /* Stats Row */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .stat-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 18px 20px;
      backdrop-filter: blur(16px);
      display: flex;
      flex-direction: column;
      gap: 6px;
      transition: all 0.2s;
    }
    .stat-card:hover { border-color: rgba(255, 255, 255, 0.2); }
    .stat-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: var(--text-muted);
      font-size: 0.78rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .stat-value {
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 1.85rem;
      font-weight: 800;
      color: #ffffff;
      line-height: 1.1;
    }
    .stat-subtitle {
      font-size: 0.74rem;
      color: var(--text-dim);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    /* Toolbar */
    .toolbar-container {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 14px 18px;
      margin-bottom: 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .toolbar-row-top, .toolbar-row-bottom {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }
    .search-box {
      flex: 1;
      min-width: 220px;
      position: relative;
      display: flex;
      align-items: center;
    }
    .search-box svg { position: absolute; left: 12px; color: var(--text-dim); }
    .search-box input {
      width: 100%;
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid var(--border-color);
      padding: 8px 12px 8px 36px;
      border-radius: var(--radius-md);
      color: #fff;
      font-size: 0.84rem;
      outline: none;
      transition: all 0.2s;
    }
    .search-box input:focus {
      border-color: var(--accent-cyan);
      box-shadow: 0 0 12px rgba(0, 242, 254, 0.25);
    }
    .filter-chips { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      border-radius: var(--radius-full);
      font-size: 0.76rem;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.2s;
    }
    .chip:hover { background: rgba(255, 255, 255, 0.08); color: #fff; }
    .chip.active {
      background: rgba(0, 242, 254, 0.15);
      border-color: var(--accent-cyan);
      color: var(--accent-cyan);
    }
    .chip-badge {
      padding: 1px 6px;
      border-radius: var(--radius-full);
      background: rgba(255, 255, 255, 0.1);
      font-size: 0.68rem;
    }

    .filter-select {
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 7px 12px;
      border-radius: var(--radius-md);
      font-size: 0.8rem;
      outline: none;
      cursor: pointer;
    }
    .view-switcher {
      display: flex;
      background: rgba(0, 0, 0, 0.4);
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
      transition: all 0.2s;
    }
    .view-btn.active {
      background: rgba(255, 255, 255, 0.12);
      color: #ffffff;
    }

    /* Cards Grid */
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

    /* Badges */
    .badge-new {
      display: inline-flex;
      align-items: center;
      padding: 2px 7px;
      border-radius: var(--radius-full);
      font-size: 0.65rem;
      font-weight: 800;
      background: var(--grad-new);
      color: #031326;
      box-shadow: 0 0 10px rgba(0, 242, 254, 0.4);
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

    /* Table View */
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
      background: rgba(0, 0, 0, 0.8);
      backdrop-filter: blur(12px);
      z-index: 1000;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }
    .modal-box {
      background: #0f1422;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: var(--radius-lg);
      width: 100%;
      max-width: 480px;
      overflow: hidden;
      box-shadow: var(--shadow-glass);
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
      bottom: 24px; right: 24px;
      padding: 12px 18px;
      background: #101626;
      border: 1px solid rgba(0, 242, 254, 0.4);
      color: #ffffff;
      border-radius: var(--radius-md);
      font-size: 0.82rem;
      z-index: 2000;
      display: none;
      box-shadow: var(--shadow-glass);
    }

    /* Mobile Responsive */
    @media (max-width: 900px) {
      .ths-hero-section {
        grid-template-columns: 1fr;
        padding: 10px 0 30px;
      }
      .hero-content-right {
        order: -1;
        min-height: 240px;
      }
      .cosmic-artwork-container { height: 260px; }
      .rocket-svg { width: 180px; height: 180px; }
      .art-orbit-ring.ring-2 { display: none; }
      .hero-title { font-size: 2.1rem; }
      .google-onetap-widget {
        display: none;
      }
    }

    @media (max-width: 768px) {
      .ths-sidebar {
        position: fixed;
        left: -240px;
      }
      .ths-sidebar.mobile-open {
        left: 0;
      }
      .mobile-menu-toggle { display: block; }
      .view-content { padding: 18px 16px 40px; }
      .dual-action-cards { grid-template-columns: 1fr; }
      .upload-action-banner { flex-direction: column; align-items: stretch; }
      .upload-btn-group { justify-content: stretch; }
      .upload-btn-group button { flex: 1; }
      .cards-grid { grid-template-columns: 1fr; }
      .stats-grid { grid-template-columns: 1fr 1fr; }
      .tester-input-bar { flex-direction: column; padding: 10px; }
      .tester-btn { width: 100%; justify-content: center; }
    }
  </style>
</head>
<body>

  <div class="app-layout">
    <!-- ==================== LEFT SIDEBAR ==================== -->
    <aside class="ths-sidebar" id="thsSidebar">
      <!-- Brand Logo & Lang -->
      <div class="sidebar-brand">
        <div class="brand-logo-circle" title="ThsAutoOrganizer Studio">
          <svg viewBox="0 0 24 24"><path d="M12 2L1 21h22L12 2zm0 3.84L19.53 19H4.47L12 5.84zM11 10h2v4h-2zm0 6h2v2h-2z"/></svg>
        </div>
        <div class="brand-title-group">
          <span class="brand-title-text">ThsOrganizer</span>
        </div>
        <div class="brand-lang-badge">
          <span class="active">VI</span>
          <span>EN</span>
        </div>
      </div>

      <!-- Navigation Links -->
      <nav class="sidebar-nav">
        <a href="javascript:void(0)" class="nav-item active" id="navHome" onclick="showView('home')">
          <span class="nav-icon">🏠</span>
          <span class="nav-label">Trang chủ</span>
        </a>
        <a href="javascript:void(0)" class="nav-item" id="navWorkspace" onclick="showView('workspace')">
          <span class="nav-icon">📚</span>
          <span class="nav-label">Tổ chức tài liệu</span>
        </a>
        <a href="javascript:void(0)" class="nav-item" id="navSearch" onclick="focusSearch()">
          <span class="nav-icon">🔍</span>
          <span class="nav-label">Tra cứu</span>
        </a>
        <a href="javascript:void(0)" class="nav-item" id="navAbout" onclick="openAboutModal()">
          <span class="nav-icon">ℹ️</span>
          <span class="nav-label">Giới thiệu</span>
        </a>
        <a href="javascript:void(0)" class="nav-item" id="navItemAdmin" onclick="showView('admin')" style="display: none;">
          <span class="nav-icon">⚙️</span>
          <span class="nav-label">Quản trị Đào tạo</span>
        </a>
        <div class="nav-item" style="opacity: 0.5; cursor: default; margin-top: auto;">
          <span class="nav-icon">📜</span>
          <span class="nav-label">Phiên bản</span>
          <span class="nav-badge-ver">v1.0</span>
        </div>
      </nav>

      <!-- Sidebar Bottom -->
      <div class="sidebar-footer">
        <button class="sidebar-collapse-btn" onclick="toggleSidebarCollapse()" title="Thu gọn">&lt;</button>
        <div id="sidebarUserBox" style="display:none;"></div>
      </div>
    </aside>

    <!-- ==================== MAIN AREA ==================== -->
    <div class="ths-main-area">
      <!-- Topbar Header -->
      <header class="ths-topbar">
        <div class="topbar-left">
          <button class="mobile-menu-toggle" onclick="toggleMobileMenu()">☰</button>
          <div class="topbar-subtitle">
            <span style="font-weight:700; color:var(--text-primary);">ThsAutoOrganizer</span>
            <span>•</span>
            <span class="badge-edition">Studio Edition</span>
          </div>
        </div>

        <div class="topbar-right">
          <!-- Single User Profile or Sign-in button -->
          <div id="userSection">
            <button class="btn btn-secondary" onclick="openLoginModal()" id="btnLoginGoogle" style="border: 1px solid var(--border-subtle); color: var(--text-primary); font-size: 0.85rem;">
              🔑 Đăng nhập
            </button>
          </div>

          <button class="btn btn-secondary" onclick="openSettingsModal()" title="Cài đặt">⚙️</button>
        </div>
      </header>

      <!-- VIEW 1: HOMEPAGE VIEW (STUDIO EDITION LANDING PAGE) -->
      <div id="homepageView" class="view-content">

        <!-- Hero Section -->
        <section class="ths-hero-section">
          <div class="hero-content-left">
            <h1 class="hero-title">
              Hệ thống hóa <span class="gradient-text-hero">học tập & tài liệu số.</span>
            </h1>
            <div class="hero-subtitle-en">Systemize your digital academic & research workspace.</div>
            <p class="hero-description">
              Xây dựng nền tảng dữ liệu đồng nhất cho học tập và nghiên cứu. Đảm bảo thông điệp và tài liệu nhất quán trên mọi kênh, giúp sinh viên và hệ thống AI luôn thấu hiểu và tự động sắp xếp khoa học.
            </p>

            <!-- Dual Action Cards -->
            <div class="dual-action-cards">
              <!-- Card 1: Local Folder -->
              <div class="action-card card-cyan" onclick="handleHeroCardClick('folder')">
                <div class="action-card-badge-icon badge-icon-cyan">
                  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                </div>
                <div>
                  <div class="action-card-title">Đã có thư mục máy tính</div>
                  <div class="action-card-desc">Quét & tự động phân loại cấu trúc môn học</div>
                </div>
                <div class="action-card-arrow arrow-cyan">➔</div>
              </div>

              <!-- Card 2: Upload & Drive -->
              <div class="action-card card-purple" onclick="handleHeroCardClick('upload')">
                <div class="action-card-badge-icon badge-icon-purple">
                  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 0 1 10 10c0 5.523-4.477 10-10 10S2 17.523 2 12 6.477 2 12 2zm1 5h-2v5H6l6 6 6-6h-5V7z"/></svg>
                </div>
                <div>
                  <div class="action-card-title">Nạp bài giảng & Đồng bộ Drive</div>
                  <div class="action-card-desc">Chụp ảnh điện thoại, iPad hoặc tải tệp lên đám mây</div>
                </div>
                <div class="action-card-arrow arrow-purple">➔</div>
              </div>
            </div>
          </div>

          <!-- Hero Right Graphic: Cosmic Rocket Artwork -->
          <div class="hero-content-right">
            <div class="cosmic-artwork-container">
              <div class="art-glow-nebula"></div>
              <div class="art-orbit-ring ring-1"></div>
              <div class="art-orbit-ring ring-2"></div>

              <!-- Futuristic Rocket Vector Graphic -->
              <svg class="rocket-svg" viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
                <!-- Rocket Flame / Trail -->
                <path d="M72 138 C60 155 45 175 35 185 C48 172 65 155 82 144 Z" fill="url(#flameGrad)" opacity="0.9"/>
                <path d="M78 142 C70 155 60 170 52 180 C60 168 72 154 84 144 Z" fill="#00f2fe" opacity="0.8"/>
                <!-- Rocket Wings -->
                <path d="M68 115 L50 148 L75 142 Z" fill="#3b82f6" opacity="0.9"/>
                <path d="M115 68 L148 50 L142 75 Z" fill="#8b5cf6" opacity="0.9"/>
                <!-- Rocket Main Body -->
                <path d="M145 55 C120 70 85 105 70 135 L90 145 C115 125 145 90 155 70 C156 64 151 54 145 55 Z" fill="url(#rocketBodyGrad)"/>
                <!-- Rocket Nose Cone -->
                <path d="M145 55 C150 48 160 38 168 32 C162 40 152 50 145 55 Z" fill="#00f2fe"/>
                <!-- Circular Window -->
                <circle cx="120" cy="80" r="10" fill="#0b1329" stroke="#00f2fe" stroke-width="2.5"/>
                <circle cx="118" cy="78" r="3" fill="#ffffff" opacity="0.8"/>
                <!-- Thruster Base -->
                <polygon points="68,132 80,144 74,150 62,138" fill="#1e293b"/>
                
                <!-- Gradients Defs -->
                <defs>
                  <linearGradient id="rocketBodyGrad" x1="160" y1="40" x2="70" y2="140" gradientUnits="userSpaceOnUse">
                    <stop stop-color="#ffffff"/>
                    <stop offset="0.4" stop-color="#cbd5e1"/>
                    <stop offset="1" stop-color="#475569"/>
                  </linearGradient>
                  <linearGradient id="flameGrad" x1="82" y1="140" x2="35" y2="185" gradientUnits="userSpaceOnUse">
                    <stop stop-color="#a855f7"/>
                    <stop offset="0.5" stop-color="#00f2fe"/>
                    <stop offset="1" stop-color="transparent"/>
                  </linearGradient>
                </defs>
              </svg>
            </div>
          </div>
        </section>

        <!-- THỬ NGAY: Interactive AI Document Classifier -->
        <section class="ths-tester-section" id="sectionTester">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; flex-wrap: wrap;">
            <div class="tester-tag-label">THỬ NGAY</div>
            <div style="font-size: 0.72rem; padding: 2px 8px; border-radius: var(--radius-full); background: rgba(168, 85, 247, 0.15); color: var(--accent-purple); font-weight: 600; display: inline-flex; align-items: center; gap: 4px;">
              <span>🧪</span> Sandbox Trải Nghiệm Thử AI
            </div>
          </div>
          <h2 class="tester-title">Thử ngay: AI đang nói gì về tài liệu của bạn?</h2>
          <div class="tester-sub-en">Build your AI document classification health check.</div>
          <p class="tester-desc">
            Chỉ cần chọn chuyên ngành và nhập tên tệp bài giảng của bạn. Hệ thống sẽ tự động phân tích từ khóa, cấu trúc môn học và gợi ý vị trí lưu trữ tối ưu theo quy chuẩn 4 thư mục con bất biến của từng ngành đào tạo Thạc sĩ.
          </p>

          <!-- Major Selector for Tester -->
          <div style="display: flex; gap: 10px; margin-bottom: 12px; align-items: center; flex-wrap: wrap;">
            <label style="font-size: 0.82rem; color: var(--text-secondary); font-weight: 600;">Chuyên ngành:</label>
            <select id="demoMajorSelect" class="form-control" style="max-width: 280px; font-size: 0.84rem; padding: 6px 10px;" onchange="onDemoMajorChange()">
              <option value="HTTT">Hệ thống thông tin (HTTT)</option>
              <option value="QTKD">Quản trị kinh doanh (QTKD)</option>
              <option value="LKT">Luật kinh tế (LKT)</option>
              <option value="TH">Toán học (TH)</option>
              <option value="QLGD">Quản lý giáo dục (QLGD)</option>
            </select>
          </div>

          <div class="tester-input-bar">
            <input type="text" id="demoInputFile" class="tester-input" placeholder="Ví dụ: BaiGiang_Chuong1.pdf, DeCuong_OnThi.docx...">
            <button class="tester-btn" onclick="runDemoClassifier()">
              <span>🪄</span> Tạo câu hỏi kiểm tra
            </button>
          </div>

          <!-- Quick Samples -->
          <div class="tester-samples" id="demoSampleChips">
            <span class="tester-samples-label">Gợi ý thử nhanh (HTTT):</span>
            <span class="sample-chip" onclick="setDemoInput('BaiGiang_Toan_Khoa_Hoc_Du_Lieu_Chuong2.pdf')">Toán KH Dữ liệu (Slide)</span>
            <span class="sample-chip" onclick="setDemoInput('De_Cuong_On_Thi_Triet_Hoc_Mac_Lenin.docx')">Triết học (Ôn thi)</span>
            <span class="sample-chip" onclick="setDemoInput('Slide_Co_So_Du_Lieu_Nang_Cao.pptx')">Cơ sở dữ liệu (Slide)</span>
            <span class="sample-chip" onclick="setDemoInput('Giao_Trinh_Phuong_Phap_Nghien_Cuu.pdf')">PP Nghiên cứu (Giáo trình)</span>
          </div>

          <!-- Live AI Output Card -->
          <div id="testerResultCard" class="tester-result-box" style="display: none;">
            <div class="result-info-left">
              <div class="result-subject-title">
                <span>🤖 Dự đoán AI:</span>
                <span id="resSubject" style="color:var(--accent-cyan);">Toán khoa học dữ liệu</span>
                <span style="font-size:0.75rem; color:var(--text-dim);">(Độ tin cậy: 99.4%)</span>
              </div>
              <div class="result-path-text" id="resPath">📁 Thư mục đề xuất: /Toan_Khoa_Hoc_Du_Lieu/02_Slide/BaiGiang_Toan_Khoa_Hoc_Du_Lieu_Chuong1.pdf</div>
            </div>
            <div class="result-tags-right" id="resTags">
              <span class="tag-subject">Toán khoa học dữ liệu</span>
              <span class="tag-type">Slide</span>
              <span class="ext-badge ext-pdf">PDF</span>
            </div>
          </div>
        </section>

        <!-- 4 Feature Highlights Grid -->
        <div class="ths-features-grid">
          <div class="feature-card">
            <div class="feature-icon-wrapper" style="color:var(--accent-cyan);">🤖</div>
            <div class="feature-title">AI Tự động Phân loại</div>
            <div class="feature-desc">Nhận diện môn học và loại tài liệu (Giáo trình, Slide, Ôn thi) dựa trên cấu trúc tên file thông minh.</div>
          </div>
          <div class="feature-card">
            <div class="feature-icon-wrapper" style="color:var(--accent-green);">🔒</div>
            <div class="feature-title">Băm SHA-256 Chống Trùng</div>
            <div class="feature-desc">Mỗi file được băm mã hóa SHA-256, tự động loại bỏ trùng lặp tuyệt đối, tiết kiệm dung lượng ổ cứng & Drive.</div>
          </div>
          <div class="feature-card">
            <div class="feature-icon-wrapper" style="color:var(--accent-purple);">☁️</div>
            <div class="feature-title">Đồng bộ Google Drive Riêng</div>
            <div class="feature-desc">Mỗi sinh viên được cô lập dữ liệu riêng biệt. Tệp tự động đẩy lên thư mục Google Drive của chính tài khoản đó.</div>
          </div>
          <div class="feature-card">
            <div class="feature-icon-wrapper" style="color:var(--accent-amber);">📱</div>
            <div class="feature-title">Nạp Tài liệu Đa Thiết bị</div>
            <div class="feature-desc">Chụp ảnh bài giảng bằng Camera điện thoại, kéo thả trên iPad hoặc chọn cả thư mục lớn trên Máy tính.</div>
          </div>
        </div>
      </div>

      <!-- VIEW 2: WORKSPACE VIEW (PERSONAL ORGANIZER & CLOUD STORAGE) -->
      <div id="workspaceView" class="view-content" style="display: none;">
        <!-- Workspace Header & Sub-Tabs Navigation -->
        <div class="workspace-header-bar" style="margin-bottom: 20px; display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; border-bottom: 1px solid var(--border-subtle); padding-bottom: 14px;">
          <div>
            <h1 style="font-size: 1.35rem; font-weight: 700; color: var(--text-primary); letter-spacing: -0.5px;">Tổ chức tài liệu</h1>
            <div style="font-size: 0.82rem; color: var(--text-secondary); margin-top: 4px;">Không gian quản lý tài liệu học tập cá nhân & đồng bộ đám mây.</div>
          </div>
          <!-- Sub-Tabs Switcher -->
          <div class="subtabs-bar" style="display: flex; gap: 6px; background: var(--bg-surface); padding: 4px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
            <button class="subtab-btn active" id="tabBtnDocs" onclick="switchSubTab('docs')" style="padding: 7px 14px; border-radius: var(--radius-sm); border: none; background: var(--bg-subtle); color: var(--text-primary); font-size: 0.84rem; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: all 0.2s;">
              <span>📁</span> Kho tài liệu & Phân loại
            </button>
            <button class="subtab-btn" id="tabBtnSync" onclick="switchSubTab('sync')" style="padding: 7px 14px; border-radius: var(--radius-sm); border: none; background: transparent; color: var(--text-secondary); font-size: 0.84rem; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: all 0.2s;">
              <span>⚡</span> Nạp & Kết nối
            </button>
          </div>
        </div>

        <!-- Unauthenticated Calm State (Chỉ hiện khi chưa login) -->
        <div id="unauthenticatedState" style="display: none; padding: 60px 24px; text-align: center; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-lg); margin: 20px 0;">
          <div style="font-size: 2.8rem; margin-bottom: 14px;">🏛️</div>
          <div style="font-size: 1.25rem; font-weight: 700; color: var(--text-primary); margin-bottom: 8px;">Không gian Học tập Cá nhân</div>
          <p style="font-size: 0.88rem; color: var(--text-secondary); max-width: 520px; margin: 0 auto 20px; line-height: 1.6;">
            Đăng nhập bằng tài khoản Google để hệ thống tự động kết nối thư mục máy tính và Google Drive cá nhân của bạn, giữ trọn vẹn sự riêng tư và bảo mật học thuật.
          </p>
          <button class="btn btn-secondary" onclick="openLoginModal()" style="border: 1px solid var(--border-focus); padding: 10px 24px; font-size: 0.9rem; font-weight: 600; color: var(--text-primary);">
            🔑 Đăng nhập Google
          </button>
          <div style="margin-top: 14px;">
            <a href="javascript:void(0)" onclick="openLoginModal()" style="font-size: 0.78rem; color: var(--text-tertiary); text-decoration: underline;">
              Hoặc đăng nhập nhanh bằng Email sinh viên (Chế độ kiểm thử)
            </a>
          </div>
        </div>

        <!-- SUBTAB 1: KHO TÀI LIỆU & PHÂN LOẠI -->
        <div id="subtabDocs" class="subtab-content">
          <!-- Stats Row -->
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-header">
                <span>Kho tài liệu của bạn</span>
                <span>📁</span>
              </div>
              <div class="stat-value" id="statTotalFiles">0</div>
              <div class="stat-subtitle" id="statStoragePath">Chưa kết nối thư mục</div>
            </div>

            <div class="stat-card">
              <div class="stat-header">
                <span>Google Drive cá nhân</span>
                <span style="color: var(--accent-emerald);">☁️</span>
              </div>
              <div class="stat-value" id="statUploaded" style="color: var(--accent-emerald);">0</div>
              <div class="stat-subtitle" id="statDriveFolder">Chưa kết nối Google Drive</div>
            </div>

            <div class="stat-card">
              <div class="stat-header">
                <span>Tài liệu mới (&lt;24h)</span>
                <span style="color: var(--accent-purple);">✨</span>
              </div>
              <div class="stat-value" id="statNewCount" style="color: var(--accent-purple);">0</div>
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
                  ✨ Mới (&lt;24h) <span class="chip-badge" id="countNew">0</span>
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
        </div>

        <!-- SUBTAB 2: NẠP & KẾT NỐI (Ingestion & Sync Hub) -->
        <div id="subtabSync" class="subtab-content" style="display: none;">
          <!-- Lock Card khi chưa đăng nhập -->
          <div id="syncLockCard" style="display:block; text-align: center; padding: 48px 24px; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); margin-bottom: 20px;">
            <div style="font-size: 2.4rem; margin-bottom: 12px;">🔒</div>
            <div style="font-size: 1.15rem; font-weight: 700; color: var(--text-primary); margin-bottom: 6px;">
              Tính năng yêu cầu định danh tài khoản
            </div>
            <div style="font-size: 0.88rem; color: var(--text-secondary); max-width: 460px; margin: 0 auto 20px; line-height: 1.6;">
              Vui lòng đăng nhập để sử dụng tính năng nạp tài liệu đa thiết bị, đồng bộ thư mục máy tính và lưu trữ vào Google Drive cá nhân của bạn.
            </div>
            <button class="btn btn-primary" onclick="openLoginModal()" style="padding: 10px 24px; font-size: 0.9rem;">
              🔑 Đăng nhập để nạp tài liệu
            </button>
          </div>

          <!-- Nội dung Nạp & Kết nối khi đã đăng nhập -->
          <div id="syncUploadContent" style="display:none;">
            <!-- User Machine Folder Bar (Chỉ hiển thị khi đã đăng nhập) -->
            <div id="userFolderBar" style="display:none; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px 18px; margin-bottom: 20px; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap;">
              <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 1.6rem;">📁</span>
                <div>
                  <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                    <span style="font-weight: 700; font-size: 0.92rem; color: var(--text-primary);">Thư mục máy tính của bạn:</span>
                    <span id="displayUserFolder" style="font-family: 'JetBrains Mono', monospace; color: var(--accent-purple); font-weight: 600; background: rgba(0,0,0,0.35); padding: 3px 10px; border-radius: 4px; font-size: 0.82rem;">--</span>
                  </div>
                  <div style="font-size: 0.76rem; color: var(--text-muted); margin-top: 3px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                    <span>Tài khoản: <b id="displayUserEmail" style="color: #93c5fd;">--</b></span>
                    <span>|</span>
                    <span id="displayUserDrive" style="font-size: 0.75rem; padding: 2px 8px; border-radius: 4px;">--</span>
                  </div>
                </div>
              </div>
              <div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">
                <button class="btn btn-secondary" onclick="openChangeFolderModal()" style="font-size: 0.8rem; padding: 7px 12px; border: 1px solid var(--border-subtle);">
                  ✏️ Đổi thư mục máy
                </button>
                <button class="btn btn-primary" onclick="triggerServerScan()" id="btnServerScan" style="font-size: 0.8rem; padding: 7px 16px;">
                  🔍 Quét & Đồng bộ thư mục ngay
                </button>
              </div>
            </div>

            <!-- Cross-Platform Upload Banner -->
            <div class="upload-action-banner" style="background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 20px;">
              <div class="upload-banner-text">
                <div class="upload-banner-title" style="font-size: 1.05rem; font-weight: 700; color: var(--text-primary);">
                  <span>⚡ Nạp tài liệu đa thiết bị</span>
                  <span style="font-size: 0.76rem; color: var(--accent-purple); font-weight: normal; margin-left: 6px;">(Tự động băm SHA-256, phân loại & lưu Drive)</span>
                </div>
                <div class="upload-banner-sub" style="font-size: 0.84rem; color: var(--text-secondary); margin-top: 4px;">
                  Hỗ trợ chụp bài giảng từ điện thoại, nạp tệp từ iPad hoặc kết nối thư mục trên Laptop/PC.
                </div>
              </div>

              <div class="upload-btn-group" style="margin-top: 16px; display: flex; gap: 10px; flex-wrap: wrap;">
                <input type="file" id="cameraInput" accept="image/*" capture="environment" style="display:none" onchange="handleFileInput(this.files)">
                <button class="btn btn-secondary" onclick="document.getElementById('cameraInput').click()" style="border: 1px solid var(--border-subtle);">
                  📸 Chụp bài giảng
                </button>

                <input type="file" id="fileInput" multiple style="display:none" onchange="handleFileInput(this.files)">
                <button class="btn btn-secondary" onclick="document.getElementById('fileInput').click()" style="border: 1px solid var(--border-subtle);">
                  📤 Nạp tệp (PDF/Word/Ảnh)
                </button>

                <button class="btn btn-primary" onclick="pickDirectoryOnDesktop()" id="btnPickFolder">
                  📁 Chọn thư mục máy tính
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- VIEW 3: ADMIN MANAGEMENT VIEW (CHƯƠNG TRÌNH ĐÀO TẠO & CHUYÊN NGÀNH) -->
      <div id="adminView" class="view-content" style="display: none; padding: 24px 28px;">
        <!-- Admin Header -->
        <div style="margin-bottom: 24px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 16px;">
          <div style="display: flex; align-items: center; gap: 12px;">
            <div style="width: 40px; height: 40px; border-radius: var(--radius-md); background: rgba(168, 85, 247, 0.15); display: flex; align-items: center; justify-content: center; font-size: 1.25rem;">⚙️</div>
            <div>
              <h1 style="font-size: 1.35rem; font-weight: 700; color: var(--text-primary); letter-spacing: -0.5px;">Quản trị Chương trình Đào tạo & Chuyên ngành</h1>
              <div style="font-size: 0.84rem; color: var(--text-secondary); margin-top: 2px;">
                Quản lý 14 Chuyên ngành Thạc sĩ và danh mục Học phần chuẩn 4 thư mục con (01_Giao_Trinh, 02_Slide, 03_Tai_Lieu_Tham_Khao, 04_On_Thi).
              </div>
            </div>
          </div>
        </div>

        <!-- 2-Column Obsidian Zinc Grid -->
        <div style="display: grid; grid-template-columns: 360px 1fr; gap: 20px; align-items: start;" class="admin-grid-layout">
          <!-- Left Column: Chuyên ngành -->
          <div style="background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 18px;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px;">
              <h3 style="font-size: 0.95rem; font-weight: 700; color: var(--text-primary); margin: 0; display: flex; align-items: center; gap: 8px;">
                <span>🎓</span> Chuyên ngành (<span id="adminMajorCount">0</span>)
              </h3>
              <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.78rem; border: 1px solid var(--border-subtle);" onclick="toggleAddMajorForm()">+ Thêm ngành</button>
            </div>

            <!-- Form thêm ngành (ẩn mặc định) -->
            <div id="adminAddMajorForm" style="display: none; background: var(--bg-subtle); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 12px; margin-bottom: 14px;">
              <div style="font-size: 0.8rem; font-weight: 600; color: var(--text-primary); margin-bottom: 8px;">Tạo chuyên ngành mới</div>
              <input type="text" id="newMajorCode" class="form-control" placeholder="Mã ngành (vd: KHMT, QTKD)" style="margin-bottom: 6px; font-size: 0.8rem;">
              <input type="text" id="newMajorName" class="form-control" placeholder="Tên chuyên ngành (vd: Khoa học máy tính)" style="margin-bottom: 6px; font-size: 0.8rem;">
              <input type="text" id="newMajorFolder" class="form-control" placeholder="Tên thư mục (vd: Khoa_Hoc_May_Tinh)" style="margin-bottom: 6px; font-size: 0.8rem;">
              <textarea id="newMajorDesc" class="form-control" placeholder="Mô tả ngành..." style="height: 50px; margin-bottom: 8px; font-size: 0.8rem;"></textarea>
              <div style="display: flex; justify-content: flex-end; gap: 6px;">
                <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.78rem;" onclick="toggleAddMajorForm()">Hủy</button>
                <button class="btn btn-primary" style="padding: 4px 12px; font-size: 0.78rem;" onclick="submitNewMajor()">Lưu</button>
              </div>
            </div>

            <!-- Danh sách chuyên ngành cuộn -->
            <div id="adminMajorsList" style="max-height: 560px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px;">
              <!-- Render by JS -->
            </div>
          </div>

          <!-- Right Column: Danh mục Học phần / Môn học của ngành đang chọn -->
          <div style="background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 18px;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px;">
              <div>
                <h3 style="font-size: 0.95rem; font-weight: 700; color: var(--text-primary); margin: 0; display: flex; align-items: center; gap: 8px;">
                  <span>📚</span> Học phần: <span id="adminSelectedMajorName" style="color: var(--accent-cyan); font-weight: 600;">--</span>
                </h3>
                <div style="font-size: 0.78rem; color: var(--text-secondary); margin-top: 2px;">
                  Mỗi học phần tự động chuẩn bị 4 thư mục: 01_Giao_Trinh, 02_Slide, 03_Tai_Lieu_Tham_Khao, 04_On_Thi.
                </div>
              </div>
              <button class="btn btn-primary" id="btnAdminAddSubject" style="padding: 4px 12px; font-size: 0.78rem;" onclick="toggleAddSubjectForm()" disabled>+ Thêm môn học</button>
            </div>

            <!-- Form thêm học phần (ẩn mặc định) -->
            <div id="adminAddSubjectForm" style="display: none; background: var(--bg-subtle); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 14px; margin-bottom: 14px;">
              <div style="font-size: 0.82rem; font-weight: 600; color: var(--text-primary); margin-bottom: 10px;">Thêm môn học vào chuyên ngành đang chọn</div>
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 8px;">
                <input type="text" id="newSubjectCode" class="form-control" placeholder="Mã môn (vd: KTTK_PM, ML)" style="font-size: 0.8rem;">
                <input type="text" id="newSubjectName" class="form-control" placeholder="Tên môn học (vd: Kiến trúc thiết kế PM)" style="font-size: 0.8rem;">
              </div>
              <div style="margin-bottom: 8px;">
                <input type="text" id="newSubjectFolder" class="form-control" placeholder="Tên thư mục lưu trữ (vd: Kien_Truc_Thiet_Ke_PM)" style="font-size: 0.8rem;">
              </div>
              <div style="margin-bottom: 10px;">
                <input type="text" id="newSubjectKeywords" class="form-control" placeholder="Từ khóa nhận diện AI (phân cách bằng dấu phẩy, vd: kientruc, software architecture)" style="font-size: 0.8rem;">
              </div>
              <div style="display: flex; justify-content: flex-end; gap: 6px;">
                <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.78rem;" onclick="toggleAddSubjectForm()">Hủy</button>
                <button class="btn btn-primary" style="padding: 4px 12px; font-size: 0.78rem;" onclick="submitNewSubject()">Lưu môn học</button>
              </div>
            </div>

            <!-- Danh sách học phần dạng bảng Obsidian Zinc -->
            <div style="overflow-x: auto;">
              <table style="width: 100%; border-collapse: collapse; font-size: 0.82rem;">
                <thead>
                  <tr style="border-bottom: 1px solid var(--border-subtle); text-align: left; color: var(--text-secondary);">
                    <th style="padding: 8px 10px; font-weight: 600;">Mã</th>
                    <th style="padding: 8px 10px; font-weight: 600;">Tên môn học</th>
                    <th style="padding: 8px 10px; font-weight: 600;">Thư mục</th>
                    <th style="padding: 8px 10px; font-weight: 600;">Từ khóa AI</th>
                    <th style="padding: 8px 10px; font-weight: 600; text-align: center;">4 Thư mục con</th>
                  </tr>
                </thead>
                <tbody id="adminSubjectsTableBody">
                  <tr>
                    <td colspan="5" style="text-align: center; padding: 24px; color: var(--text-dim);">
                      Vui lòng chọn một chuyên ngành từ cột bên trái để xem danh mục môn học.
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

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
              Ứng dụng Google Cloud đang ở chế độ <b>Testing</b>. Bạn hãy chọn nhanh tài khoản thử nghiệm bên dưới để đăng nhập ngay mà không bị Google chặn!
            </div>
          </div>

          <div style="text-align: center; font-size: 0.75rem; color: var(--text-dim); margin: 6px 0;">- CHỌN NHANH TÀI KHOẢN ĐỂ SỬ DỤNG -</div>

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
            <input type="email" id="testEmailInput" class="form-control" placeholder="Nhập email (vd: sv_httt@gmail.com)">
            <input type="text" id="testNameInput" class="form-control" placeholder="Họ và tên của bạn">
            <button class="btn btn-primary" onclick="submitTestLogin()" style="margin-top: 4px;">🚀 Vào kho tài liệu của tôi</button>
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
          Nhập đường dẫn thư mục chứa tài liệu học tập trên máy tính của bạn. Hệ thống sẽ quét các tài liệu trong thư mục này và liên kết riêng cho tài khoản của bạn.
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

  <!-- Modal Onboarding Chọn Chuyên Ngành Học Thuật -->
  <div class="modal-backdrop" id="onboardingModal" style="display:none; z-index: 1100;">
    <div class="modal-box" style="max-width: 680px; width: 92vw;">
      <div class="modal-header">
        <div>
          <div style="font-weight: 700; font-size: 1.1rem; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
            <span>🎓</span> Chọn Chuyên Ngành Đào Tạo Thạc Sĩ
          </div>
          <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 2px;">
            Chào mừng bạn! Hãy chọn chuyên ngành để hệ thống tự động chuẩn bị không gian học tập và cấu trúc thư mục chuẩn.
          </div>
        </div>
      </div>
      <div class="modal-body" style="max-height: 60vh; overflow-y: auto;">
        <input type="text" id="onboardingMajorSearch" class="form-control" placeholder="🔍 Tìm kiếm nhanh chuyên ngành (vd: Quản trị kinh doanh, Hệ thống thông tin...)" oninput="filterOnboardingMajors()" style="margin-bottom: 14px;">
        <div id="onboardingMajorsList" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px;">
          <!-- Danh sách thẻ chuyên ngành được render động bằng JS -->
        </div>
      </div>
      <div class="modal-footer" style="justify-content: space-between;">
        <div id="onboardingSelectedHint" style="font-size: 0.82rem; color: var(--text-secondary);">
          Chưa chọn chuyên ngành
        </div>
        <button id="btnConfirmOnboarding" class="btn btn-primary" onclick="confirmStudentMajorSelection()" disabled>
          🚀 Bắt đầu học tập
        </button>
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

  <!-- Modal Giới thiệu (About) -->
  <div class="modal-backdrop" id="aboutModal">
    <div class="modal-box">
      <div class="modal-header">
        <div style="font-weight: 700; font-size: 1rem;">ℹ️ Giới thiệu ThsAutoOrganizer Cloud Studio</div>
        <button style="background:none; border:none; color:var(--text-muted); cursor:pointer; font-size:1.2rem;" onclick="closeAboutModal()">&times;</button>
      </div>
      <div class="modal-body" style="font-size: 0.84rem; line-height: 1.6; color: var(--text-muted);">
        <p><b>ThsAutoOrganizer Studio</b> là nền tảng quản lý và tự động phân loại tài liệu học tập, nghiên cứu Thạc sĩ Hệ thống Thông tin đa thiết bị (PC, iPad, Điện thoại).</p>
        <div style="background:rgba(255,255,255,0.04); padding:12px; border-radius:8px; border:1px solid var(--border-color); margin-top:8px;">
          <div>⚡ <b>Phiên bản:</b> 0.29.0 Studio Edition</div>
          <div>☁️ <b>Kiến trúc:</b> Multi-User SaaS với Google Drive & Local Storage riêng biệt</div>
          <div>🔒 <b>Bảo mật:</b> Băm mã hóa SHA-256 chống trùng lặp dữ liệu</div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-primary" onclick="closeAboutModal()">Đã hiểu</button>
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
    let currentActiveView = 'home';
    let defaultRootFolder = '';

    function showToast(msg) {
      const t = document.getElementById('toastMsg');
      t.textContent = msg;
      t.style.display = 'block';
      setTimeout(() => { t.style.display = 'none'; }, 3500);
    }

    /* View Navigation (Homepage vs Workspace vs Admin) */
    function showView(viewName) {
      currentActiveView = viewName;
      const homeEl = document.getElementById('homepageView');
      const workEl = document.getElementById('workspaceView');
      const adminEl = document.getElementById('adminView');
      const navH = document.getElementById('navHome');
      const navW = document.getElementById('navWorkspace');
      const navA = document.getElementById('navItemAdmin');

      if (viewName === 'home') {
        if (homeEl) homeEl.style.display = 'block';
        if (workEl) workEl.style.display = 'none';
        if (adminEl) adminEl.style.display = 'none';
        if (navH) navH.classList.add('active');
        if (navW) navW.classList.remove('active');
        if (navA) navA.classList.remove('active');
      } else if (viewName === 'admin') {
        if (homeEl) homeEl.style.display = 'none';
        if (workEl) workEl.style.display = 'none';
        if (adminEl) adminEl.style.display = 'block';
        if (navH) navH.classList.remove('active');
        if (navW) navW.classList.remove('active');
        if (navA) navA.classList.add('active');
        loadAdminMajors();
      } else {
        if (homeEl) homeEl.style.display = 'none';
        if (workEl) workEl.style.display = 'block';
        if (adminEl) adminEl.style.display = 'none';
        if (navH) navH.classList.remove('active');
        if (navW) navW.classList.add('active');
        if (navA) navA.classList.remove('active');
        
        const unauth = document.getElementById('unauthenticatedState');
        const subDocs = document.getElementById('subtabDocs');
        const subSync = document.getElementById('subtabSync');
        if (!currentUser) {
          if (unauth) unauth.style.display = 'block';
          if (subDocs) subDocs.style.display = 'none';
          if (subSync) subSync.style.display = 'none';
        } else {
          if (unauth) unauth.style.display = 'none';
          switchSubTab('docs');
          loadStats();
          loadFiles();
        }
      }
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function switchSubTab(tabName) {
      const tabDocs = document.getElementById('subtabDocs');
      const tabSync = document.getElementById('subtabSync');
      const btnDocs = document.getElementById('tabBtnDocs');
      const btnSync = document.getElementById('tabBtnSync');
      if (!tabDocs || !tabSync) return;

      if (tabName === 'sync') {
        tabDocs.style.display = 'none';
        tabSync.style.display = 'block';
        if (btnDocs) { btnDocs.style.background = 'transparent'; btnDocs.style.color = 'var(--text-secondary)'; }
        if (btnSync) { btnSync.style.background = 'var(--bg-subtle)'; btnSync.style.color = 'var(--text-primary)'; }
      } else {
        tabDocs.style.display = 'block';
        tabSync.style.display = 'none';
        if (btnDocs) { btnDocs.style.background = 'var(--bg-subtle)'; btnDocs.style.color = 'var(--text-primary)'; }
        if (btnSync) { btnSync.style.background = 'transparent'; btnSync.style.color = 'var(--text-secondary)'; }
      }
    }

    function handleHeroCardClick(type) {
      if (type === 'folder') {
        if (!currentUser) {
          showToast('💡 Vui lòng đăng nhập để kết nối thư mục máy tính của bạn!');
          openLoginModal();
        } else {
          showView('workspace');
          switchSubTab('sync');
          openChangeFolderModal();
        }
      } else {
        if (!currentUser) {
          showToast('💡 Vui lòng đăng nhập để nạp tệp & đồng bộ Drive!');
          openLoginModal();
        } else {
          showView('workspace');
          switchSubTab('sync');
          document.getElementById('fileInput').click();
        }
      }
    }

    function triggerNavUpload() {
      showView('workspace');
      switchSubTab('sync');
    }

    function openDriveNav() {
      showView('workspace');
      switchSubTab('sync');
    }

    function scrollToTester() {
      showView('home');
      const sec = document.getElementById('sectionTester');
      if (sec) sec.scrollIntoView({ behavior: 'smooth' });
    }

    function openAboutModal() { document.getElementById('aboutModal').style.display = 'flex'; }
    function closeAboutModal() { document.getElementById('aboutModal').style.display = 'none'; }

    function focusSearch() {
      showView('workspace');
      const s = document.getElementById('searchInput');
      if (s) { s.focus(); s.scrollIntoView({ behavior: 'smooth' }); }
    }

    function filterBySubjectNav() {
      showView('workspace');
      const fs = document.getElementById('filterSubject');
      if (fs) { fs.focus(); }
    }

    function toggleSidebarCollapse() {
      const sb = document.getElementById('thsSidebar');
      sb.classList.toggle('collapsed');
    }

    function toggleMobileMenu() {
      const sb = document.getElementById('thsSidebar');
      sb.classList.toggle('mobile-open');
    }

    /* Interactive AI Tester */
    function onDemoMajorChange() {
      const sel = document.getElementById('demoMajorSelect');
      const major = sel ? sel.value : 'HTTT';
      const chipsContainer = document.getElementById('demoSampleChips');
      if (!chipsContainer) return;

      if (major === 'QTKD') {
        chipsContainer.innerHTML = `
          <span class="tester-samples-label">Gợi ý thử nhanh (QTKD):</span>
          <span class="sample-chip" onclick="setDemoInput('Marketing_Can_Ban_Chuong1.pptx')">Marketing căn bản (Slide)</span>
          <span class="sample-chip" onclick="setDemoInput('Giao_Trinh_Quan_Tri_Chien_Luoc.pdf')">Quản trị chiến lược (Giáo trình)</span>
          <span class="sample-chip" onclick="setDemoInput('De_Cuong_On_Thi_Marketing.docx')">Marketing (Ôn thi)</span>
        `;
      } else if (major === 'LKT') {
        chipsContainer.innerHTML = `
          <span class="tester-samples-label">Gợi ý thử nhanh (LKT):</span>
          <span class="sample-chip" onclick="setDemoInput('Phap_Luat_Hop_Dong_Thuong_Mai.pdf')">Pháp luật hợp đồng (Giáo trình)</span>
          <span class="sample-chip" onclick="setDemoInput('Slide_Phap_Luat_Doanh_Nghiep.pptx')">Pháp luật doanh nghiệp (Slide)</span>
          <span class="sample-chip" onclick="setDemoInput('On_Thi_Luat_Kinh_Te.docx')">Luật kinh tế (Ôn thi)</span>
        `;
      } else if (major === 'QLGD') {
        chipsContainer.innerHTML = `
          <span class="tester-samples-label">Gợi ý thử nhanh (QLGD):</span>
          <span class="sample-chip" onclick="setDemoInput('Quan_Ly_Truong_Hoc_Hien_Dai.pdf')">Quản lý trường học (Giáo trình)</span>
          <span class="sample-chip" onclick="setDemoInput('Slide_Danh_Gia_Trong_Giao_Duc.pptx')">Đánh giá trong GD (Slide)</span>
        `;
      } else if (major === 'TH') {
        chipsContainer.innerHTML = `
          <span class="tester-samples-label">Gợi ý thử nhanh (Toán học):</span>
          <span class="sample-chip" onclick="setDemoInput('Giao_Trinh_Dai_So_Truu_Tuong.pdf')">Đại số trừu tượng (Giáo trình)</span>
          <span class="sample-chip" onclick="setDemoInput('Slide_Giai_Tich_Thuc.pptx')">Giải tích thực (Slide)</span>
        `;
      } else {
        chipsContainer.innerHTML = `
          <span class="tester-samples-label">Gợi ý thử nhanh (HTTT):</span>
          <span class="sample-chip" onclick="setDemoInput('BaiGiang_Toan_Khoa_Hoc_Du_Lieu_Chuong2.pdf')">Toán KH Dữ liệu (Slide)</span>
          <span class="sample-chip" onclick="setDemoInput('De_Cuong_On_Thi_Triet_Hoc_Mac_Lenin.docx')">Triết học (Ôn thi)</span>
          <span class="sample-chip" onclick="setDemoInput('Slide_Co_So_Du_Lieu_Nang_Cao.pptx')">Cơ sở dữ liệu (Slide)</span>
          <span class="sample-chip" onclick="setDemoInput('Giao_Trinh_Phuong_Phap_Nghien_Cuu.pdf')">PP Nghiên cứu (Giáo trình)</span>
        `;
      }

      const curInput = (document.getElementById('demoInputFile').value || '').trim();
      if (curInput) {
        runDemoClassifier();
      } else {
        const resBox = document.getElementById('testerResultCard');
        if (resBox) resBox.style.display = 'none';
      }
    }

    function setDemoInput(filename) {
      document.getElementById('demoInputFile').value = filename;
      runDemoClassifier();
    }

    async function runDemoClassifier() {
      const input = document.getElementById('demoInputFile').value.trim();
      const resBox = document.getElementById('testerResultCard');
      if (!input) {
        if (resBox) resBox.style.display = 'none';
        return;
      }
      if (resBox) resBox.style.display = 'flex';

      const sel = document.getElementById('demoMajorSelect');
      const majorCode = sel ? sel.value : 'HTTT';

      const resSub = document.getElementById('resSubject');
      const resPath = document.getElementById('resPath');
      const resTags = document.getElementById('resTags');

      let subject = 'Tài liệu chung';
      let docType = 'Tài liệu tham khảo';
      const fnLower = input.toLowerCase();

      // Phân tích Môn học đa ngành
      if (fnLower.includes('marketing') || fnLower.includes('mkt')) subject = 'Marketing căn bản';
      else if (fnLower.includes('chien_luoc') || fnLower.includes('strategy')) subject = 'Quản trị chiến lược';
      else if (fnLower.includes('hop_dong')) subject = 'Pháp luật hợp đồng';
      else if (fnLower.includes('doanh_nghiep')) subject = 'Pháp luật doanh nghiệp';
      else if (fnLower.includes('truong_hoc')) subject = 'Quản lý trường học';
      else if (fnLower.includes('danh_gia')) subject = 'Đánh giá trong giáo dục';
      else if (fnLower.includes('dai_so')) subject = 'Đại số trừu tượng';
      else if (fnLower.includes('giai_tich')) subject = 'Giải tích thực';
      else if (fnLower.includes('triet')) subject = 'Triết học';
      else if (fnLower.includes('toan') || fnLower.includes('du_lieu') || fnLower.includes('data')) subject = 'Toán khoa học dữ liệu';
      else if (fnLower.includes('csdl') || fnLower.includes('du lieu') || fnLower.includes('database')) subject = 'Cơ sở dữ liệu';
      else if (fnLower.includes('nghien_cuu') || fnLower.includes('phuong_phap')) subject = 'Phương pháp nghiên cứu';
      else if (fnLower.includes('ghi_chu') || fnLower.includes('note')) subject = 'Phương pháp ghi chú';
      else {
        subject = (majorCode === 'QTKD') ? 'Marketing căn bản' : (majorCode === 'LKT') ? 'Pháp luật hợp đồng' : (majorCode === 'QLGD') ? 'Quản lý trường học' : 'Toán khoa học dữ liệu';
      }

      const ext = input.split('.').pop().toLowerCase();
      if (fnLower.includes('slide') || fnLower.includes('bai_giang') || fnLower.includes('baigiang') || ext === 'pptx' || ext === 'ppt') {
        docType = 'Slide';
      } else if (fnLower.includes('on_thi') || fnLower.includes('de_cuong') || fnLower.includes('onthi') || fnLower.includes('de_thi')) {
        docType = 'Ôn thi';
      } else if (fnLower.includes('giao_trinh') || fnLower.includes('giaotrinh') || fnLower.includes('book')) {
        docType = 'Giáo trình';
      } else {
        docType = 'Tài liệu tham khảo';
      }

      const safeSub = subject.replace(/\\s+/g, '_');
      const folderName = (docType === 'Giáo trình') ? '01_Giao_Trinh' : (docType === 'Slide') ? '02_Slide' : (docType === 'Ôn thi') ? '04_On_Thi' : '03_Tai_Lieu_Tham_Khao';

      resSub.textContent = subject;
      resPath.textContent = `📁 Thư mục đề xuất: /${majorCode}/${safeSub}/${folderName}/${input}`;
      resTags.innerHTML = `
        <span class="tag-subject">${subject}</span>
        <span class="tag-type">${docType}</span>
        ${getExtBadge(input)}
      `;

      resBox.style.display = 'flex';
      showToast(`✨ Đã phân loại: ${subject} (${docType})`);
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

    async function checkCurrentUser() {
      try {
        const res = await fetch('/api/me');
        const data = await res.json();
        defaultRootFolder = data.default_folder || '';
        const userSec = document.getElementById('userSection');
        const sidebarUserBox = document.getElementById('sidebarUserBox');
        const oneTap = document.getElementById('oneTapWidget');
        const folderBar = document.getElementById('userFolderBar');
        const banner = document.getElementById('loginPromptBanner');

        if (data.authenticated && data.user) {
          currentUser = data.user;
          if (oneTap) oneTap.style.display = 'none';
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
          const userHtml = `
            <div class="user-profile-chip" onclick="openSettingsModal()" title="${currentUser.email}">
              <div class="user-avatar">${initial}</div>
              <span class="user-name-text">${currentUser.name || currentUser.email}</span>
            </div>
          `;
          if (userSec) userSec.innerHTML = userHtml;
          if (sidebarUserBox) {
            sidebarUserBox.innerHTML = '';
          }

          const lockCard = document.getElementById('syncLockCard');
          const syncContent = document.getElementById('syncUploadContent');
          if (lockCard) lockCard.style.display = 'none';
          if (syncContent) syncContent.style.display = 'block';

          const navAdmin = document.getElementById('navItemAdmin');
          if (navAdmin) {
            navAdmin.style.display = data.is_admin ? 'flex' : 'none';
          }

          document.getElementById('settingsUserEmail').textContent = currentUser.email;
          const cfgInput = document.getElementById('cfgRootFolder');
          if (cfgInput) cfgInput.value = currentUser.local_folder || defaultRootFolder;

          await loadStats();
          await loadFiles();

          if (currentUser && !currentUser.major_id) {
            openOnboardingModal();
          }
        } else {
          currentUser = null;
          if (banner) banner.style.display = 'none';
          if (folderBar) folderBar.style.display = 'none';
          const navAdmin = document.getElementById('navItemAdmin');
          if (navAdmin) navAdmin.style.display = 'none';
          if (userSec) {
            userSec.innerHTML = `
              <button class="btn btn-secondary" onclick="openLoginModal()" style="border: 1px solid var(--border-subtle); color: var(--text-primary); font-size: 0.85rem;">
                🔑 Đăng nhập
              </button>
            `;
          }
          if (sidebarUserBox) {
            sidebarUserBox.innerHTML = '';
          }
          renderLoggedOutState();
        }
      } catch (e) {
        console.error('Lỗi check user:', e);
      }
    }

    function renderLoggedOutState() {
      allFiles = [];
      currentUser = null;
      const navAdmin = document.getElementById('navItemAdmin');
      if (navAdmin) navAdmin.style.display = 'none';
      if (currentActiveView === 'admin') {
        showView('home');
      }
      document.getElementById('statTotalFiles').textContent = '0';
      document.getElementById('statUploaded').textContent = '0';
      document.getElementById('statNewCount').textContent = '0';
      document.getElementById('statSubjectsCount').textContent = '0';
      document.getElementById('countAll').textContent = '0';
      document.getElementById('countNew').textContent = '0';
      document.getElementById('countDrive').textContent = '0';

      const lockCard = document.getElementById('syncLockCard');
      const syncContent = document.getElementById('syncUploadContent');
      if (lockCard) lockCard.style.display = 'block';
      if (syncContent) syncContent.style.display = 'none';

      const statPath = document.getElementById('statStoragePath');
      if (statPath) document.getElementById('statStoragePath').textContent = 'Chưa kết nối thư mục';

      const statDrive = document.getElementById('statDriveFolder');
      if (statDrive) document.getElementById('statDriveFolder').textContent = 'Chưa kết nối Google Drive';

      const dispFolder = document.getElementById('displayUserFolder');
      if (dispFolder) dispFolder.textContent = '--';

      const dispEmail = document.getElementById('displayUserEmail');
      if (dispEmail) dispEmail.textContent = '--';

      const dispDrive = document.getElementById('displayUserDrive');
      if (dispDrive) dispDrive.textContent = '--';

      const fSub = document.getElementById('filterSubject');
      if (fSub) fSub.innerHTML = '<option value="">Tất cả môn học</option>';

      // 1. Reset các form & input cá nhân trong Modal và View
      const setMail = document.getElementById('settingsUserEmail');
      if (setMail) document.getElementById('settingsUserEmail').textContent = '';
      const cfgRoot = document.getElementById('cfgRootFolder');
      if (cfgRoot) document.getElementById('cfgRootFolder').value = '';
      const inUserFolder = document.getElementById('inputUserFolder');
      if (inUserFolder) document.getElementById('inputUserFolder').value = '';
      const testMail = document.getElementById('testEmailInput');
      if (testMail) document.getElementById('testEmailInput').value = '';
      const testName = document.getElementById('testNameInput');
      if (testName) document.getElementById('testNameInput').value = '';
      const searchQ = document.getElementById('searchQuery');
      if (searchQ) document.getElementById('searchQuery').value = '';

      // 2. Reset khung Demo Trang chu
      const demoInput = document.getElementById('demoInputFile');
      if (demoInput) document.getElementById('demoInputFile').value = '';
      const demoRes = document.getElementById('testerResultCard');
      if (demoRes) document.getElementById('testerResultCard').style.display = 'none';

      // 3. Reset các bộ lọc và trạng thái tạm
      currentQuickFilter = 'ALL';
      const fType = document.getElementById('filterType');
      if (fType) fType.value = '';
      selectedOnboardingMajorId = null;
      adminSelectedMajor = null;

      const container = document.getElementById('cardsContainer');
      if (container) container.innerHTML = '';
      const tbody = document.getElementById('filesTableBody');
      if (tbody) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:36px; color:var(--text-dim);">Chưa có tài liệu nào.</td></tr>';
      }
    }

    async function loadStats() {
      if (!currentUser) return;
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
      if (!currentUser) return;
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
            Không tìm thấy tài liệu phù hợp.
          </div>`;
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
          <div class="file-card ${f.is_new ? 'is-new-card' : ''}">
            <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:8px;">
              ${getExtBadge(fileName)}
              <div style="display:flex; align-items:center; gap:6px;">
                ${newBadge}
                ${statusBadge}
              </div>
            </div>
            <div class="card-title">${fileName}</div>
            <div class="card-path">${f.path}</div>
            <div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:2px;">
              <span class="tag-subject">${f.subject || 'Chung'}</span>
              <span class="tag-type">${f.document_type || 'Tài liệu'}</span>
            </div>
            <div class="card-footer">
              <span style="font-size:0.72rem; color:var(--text-muted);">⏱️ ${relTime}</span>
              <div style="display:flex; gap:6px;">
                ${driveBtn}
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
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:36px; color:var(--text-dim);">Không có dữ liệu.</td></tr>`;
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
              showToast(`✅ Đã nạp thành công: ${file.name}`);
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
          await checkCurrentUser();
          showView('workspace');
        }
      } catch (e) {
        alert('Lỗi đăng nhập: ' + e);
      }
    }

    /* ĐĂNG XUẤT: HỦY SESSION VÀ ĐÁ VỀ TRANG CHỦ BAN ĐẦU */
    async function logoutUser() {
      try {
        await fetch('/auth/logout', { method: 'POST' });
        showToast('🚪 Đã đăng xuất thành công.');
        closeSettingsModal();
        closeChangeFolderModal();
        closeLoginModal();
        closeOnboardingModal();
        currentUser = null;
        allFiles = [];
        renderLoggedOutState();
        showView('home');
        await checkCurrentUser();
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

    // ==================== Onboarding Modal Logic ====================
    let allOnboardingMajors = [];
    let selectedOnboardingMajorId = null;

    async function openOnboardingModal() {
      const modal = document.getElementById('onboardingModal');
      if (!modal) return;
      modal.style.display = 'flex';
      selectedOnboardingMajorId = null;
      const confirmBtn = document.getElementById('btnConfirmOnboarding');
      if (confirmBtn) confirmBtn.disabled = true;
      document.getElementById('onboardingSelectedHint').textContent = 'Chưa chọn chuyên ngành';

      try {
        const res = await fetch('/api/majors');
        const data = await res.json();
        if (data.ok && data.majors) {
          allOnboardingMajors = data.majors;
          renderOnboardingMajors(allOnboardingMajors);
        }
      } catch (e) {
        console.error('Lỗi nạp chuyên ngành:', e);
      }
    }

    function closeOnboardingModal() {
      const modal = document.getElementById('onboardingModal');
      if (modal) modal.style.display = 'none';
    }

    function renderOnboardingMajors(majors) {
      const container = document.getElementById('onboardingMajorsList');
      if (!container) return;
      if (!majors || majors.length === 0) {
        container.innerHTML = '<div style="color:var(--text-dim); padding:20px; text-align:center;">Không tìm thấy chuyên ngành phù hợp.</div>';
        return;
      }
      container.innerHTML = majors.map(m => {
        const isSelected = selectedOnboardingMajorId === m.id;
        return `
          <div class="card card-hover" style="cursor:pointer; padding:12px 14px; border:1px solid ${isSelected ? 'var(--accent-purple)' : 'var(--border-subtle)'}; background:${isSelected ? 'rgba(168, 85, 247, 0.1)' : 'var(--bg-surface)'}; border-radius:8px; transition:all 0.2s;" onclick="selectMajorCard(${m.id}, '${m.name.replace(/'/g, "\\'")}')">
            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:4px;">
              <span style="font-weight:600; font-size:0.9rem; color:${isSelected ? 'var(--accent-purple)' : 'var(--text-primary)'};">${m.name}</span>
              <span class="badge" style="background:var(--bg-subtle); color:var(--text-secondary); font-size:0.7rem; font-family:'JetBrains Mono',monospace;">${m.code}</span>
            </div>
            <div style="font-size:0.75rem; color:var(--text-secondary); line-height:1.4;">${m.description || 'Chương trình đào tạo Thạc sĩ'}</div>
          </div>
        `;
      }).join('');
    }

    function filterOnboardingMajors() {
      const q = (document.getElementById('onboardingMajorSearch').value || '').trim().toLowerCase();
      const filtered = allOnboardingMajors.filter(m => 
        m.name.toLowerCase().includes(q) || m.code.toLowerCase().includes(q) || (m.description && m.description.toLowerCase().includes(q))
      );
      renderOnboardingMajors(filtered);
    }

    function selectMajorCard(id, name) {
      selectedOnboardingMajorId = id;
      renderOnboardingMajors(allOnboardingMajors);
      const hint = document.getElementById('onboardingSelectedHint');
      if (hint) hint.innerHTML = `Đã chọn: <b style="color:var(--accent-purple);">${name}</b>`;
      const btn = document.getElementById('btnConfirmOnboarding');
      if (btn) btn.disabled = false;
    }

    async function confirmStudentMajorSelection() {
      if (!selectedOnboardingMajorId) return;
      const btn = document.getElementById('btnConfirmOnboarding');
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Đang khởi tạo thư mục...';
      }
      try {
        const res = await fetch('/api/user/select-major', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ major_id: selectedOnboardingMajorId })
        });
        const data = await res.json();
        if (data.ok) {
          if (currentUser) {
            currentUser.major_id = selectedOnboardingMajorId;
            currentUser.major = data.major;
          }
          closeOnboardingModal();
          showToast(`Đã thiết lập chuyên ngành ${data.major.name} và khởi tạo 4 thư mục con!`);
          await loadStats();
          await loadFiles();
        } else {
          alert('Lỗi: ' + (data.error || 'Không thể chọn chuyên ngành'));
        }
      } catch (e) {
        alert('Lỗi kết nối: ' + e);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = '🚀 Bắt đầu học tập';
        }
      }
    }

    /* ==================== ADMIN MANAGEMENT VIEW JS ==================== */
    let adminSelectedMajor = null;
    let adminMajorsList = [];

    async function loadAdminMajors() {
      try {
        const res = await fetch('/api/admin/majors');
        if (res.status === 403) {
          showToast('Bạn không có quyền truy cập trang Quản trị');
          showView('home');
          return;
        }
        const data = await res.json();
        if (data.ok) {
          adminMajorsList = data.majors || [];
          const countEl = document.getElementById('adminMajorCount');
          if (countEl) countEl.textContent = adminMajorsList.length;
          renderAdminMajors();
          if (adminMajorsList.length > 0) {
            if (!adminSelectedMajor || !adminMajorsList.find(m => m.id === adminSelectedMajor.id)) {
              selectAdminMajor(adminMajorsList[0].id);
            } else {
              selectAdminMajor(adminSelectedMajor.id);
            }
          } else {
            adminSelectedMajor = null;
            document.getElementById('adminSelectedMajorName').textContent = '--';
            document.getElementById('btnAdminAddSubject').disabled = true;
            document.getElementById('adminSubjectsTableBody').innerHTML = '<tr><td colspan="5" style="text-align:center; padding:24px; color:var(--text-dim);">Chưa có chuyên ngành nào.</td></tr>';
          }
        }
      } catch (e) {
        console.error('Lỗi khi tải danh sách ngành:', e);
      }
    }

    function renderAdminMajors() {
      const container = document.getElementById('adminMajorsList');
      if (!container) return;
      container.innerHTML = adminMajorsList.map(m => {
        const isSel = adminSelectedMajor && adminSelectedMajor.id === m.id;
        return `
          <div onclick="selectAdminMajor(${m.id})" style="padding: 10px 12px; border-radius: var(--radius-sm); border: 1px solid ${isSel ? 'var(--accent-purple)' : 'var(--border-subtle)'}; background: ${isSel ? 'rgba(168, 85, 247, 0.12)' : 'var(--bg-subtle)'}; cursor: pointer; transition: all 0.2s;">
            <div style="display: flex; align-items: center; justify-content: space-between;">
              <span style="font-weight: 600; font-size: 0.84rem; color: ${isSel ? 'var(--accent-purple)' : 'var(--text-primary)'};">${m.name}</span>
              <span class="badge" style="background: var(--bg-card); color: var(--text-secondary); font-size: 0.7rem; font-family: 'JetBrains Mono', monospace;">${m.code}</span>
            </div>
            <div style="font-size: 0.74rem; color: var(--text-dim); margin-top: 3px; font-family: 'JetBrains Mono', monospace;">Thư mục: ${m.folder_name}</div>
          </div>
        `;
      }).join('');
    }

    async function selectAdminMajor(majorId) {
      const m = adminMajorsList.find(item => item.id === majorId);
      if (!m) return;
      adminSelectedMajor = m;
      renderAdminMajors();
      const nameEl = document.getElementById('adminSelectedMajorName');
      if (nameEl) nameEl.textContent = `${m.name} (${m.code})`;
      const btnAdd = document.getElementById('btnAdminAddSubject');
      if (btnAdd) btnAdd.disabled = false;

      const tbody = document.getElementById('adminSubjectsTableBody');
      if (!tbody) return;
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:18px; color:var(--text-dim);">Đang tải danh mục môn học...</td></tr>';

      try {
        const res = await fetch(`/api/majors/${majorId}/subjects`);
        const data = await res.json();
        if (data.ok) {
          const subjects = data.subjects || [];
          if (subjects.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:24px; color:var(--text-dim);">Chuyên ngành này chưa có môn học nào. Hãy bấm "+ Thêm môn học" để tạo.</td></tr>';
            return;
          }
          tbody.innerHTML = subjects.map(s => {
            let kwStr = '--';
            try {
              const kwList = typeof s.keywords === 'string' ? JSON.parse(s.keywords) : s.keywords;
              if (Array.isArray(kwList) && kwList.length > 0) {
                kwStr = kwList.slice(0, 3).join(', ') + (kwList.length > 3 ? '...' : '');
              }
            } catch (e) {}

            return `
              <tr style="border-bottom: 1px solid var(--border-subtle);">
                <td style="padding: 10px; font-weight: 600; font-family: 'JetBrains Mono', monospace; color: var(--accent-cyan);">${s.code}</td>
                <td style="padding: 10px; font-weight: 500; color: var(--text-primary);">${s.name}</td>
                <td style="padding: 10px; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: var(--text-secondary);">${s.folder_name}</td>
                <td style="padding: 10px; font-size: 0.75rem; color: var(--text-dim);">${kwStr}</td>
                <td style="padding: 10px; text-align: center;">
                  <span title="01_Giao_Trinh, 02_Slide, 03_Tai_Lieu_Tham_Khao, 04_On_Thi" style="display: inline-flex; gap: 4px; justify-content: center;">
                    <span style="background: rgba(16, 185, 129, 0.15); color: #34d399; font-size: 0.68rem; padding: 2px 6px; border-radius: 4px; font-weight: 600;">01-04 Chuẩn</span>
                  </span>
                </td>
              </tr>
            `;
          }).join('');
        }
      } catch (e) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:18px; color:var(--accent-red);">Lỗi tải môn học: ${e}</td></tr>`;
      }
    }

    function toggleAddMajorForm() {
      const form = document.getElementById('adminAddMajorForm');
      if (form) {
        form.style.display = form.style.display === 'none' ? 'block' : 'none';
      }
    }

    async function submitNewMajor() {
      const code = (document.getElementById('newMajorCode').value || '').trim();
      const name = (document.getElementById('newMajorName').value || '').trim();
      const folder_name = (document.getElementById('newMajorFolder').value || '').trim();
      const description = (document.getElementById('newMajorDesc').value || '').trim();

      if (!code || !name || !folder_name) {
        alert('Vui lòng điền đủ Mã ngành, Tên ngành và Thư mục lưu trữ');
        return;
      }

      try {
        const res = await fetch('/api/admin/majors', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code, name, folder_name, description })
        });
        const data = await res.json();
        if (data.ok) {
          showToast(`Đã thêm chuyên ngành "${name}" thành công!`);
          document.getElementById('newMajorCode').value = '';
          document.getElementById('newMajorName').value = '';
          document.getElementById('newMajorFolder').value = '';
          document.getElementById('newMajorDesc').value = '';
          toggleAddMajorForm();
          await loadAdminMajors();
        } else {
          alert('Lỗi: ' + (data.error || 'Không thể tạo chuyên ngành'));
        }
      } catch (e) {
        alert('Lỗi kết nối: ' + e);
      }
    }

    function toggleAddSubjectForm() {
      const form = document.getElementById('adminAddSubjectForm');
      if (form) {
        form.style.display = form.style.display === 'none' ? 'block' : 'none';
      }
    }

    async function submitNewSubject() {
      if (!adminSelectedMajor) {
        alert('Vui lòng chọn một chuyên ngành trước');
        return;
      }
      const code = (document.getElementById('newSubjectCode').value || '').trim();
      const name = (document.getElementById('newSubjectName').value || '').trim();
      const folder_name = (document.getElementById('newSubjectFolder').value || '').trim();
      const kwInput = (document.getElementById('newSubjectKeywords').value || '').trim();

      if (!code || !name || !folder_name) {
        alert('Vui lòng điền đủ Mã môn, Tên môn và Thư mục lưu trữ');
        return;
      }

      const keywords = kwInput ? kwInput.split(',').map(k => k.trim()).filter(Boolean) : [];

      try {
        const res = await fetch('/api/admin/subjects', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            major_id: adminSelectedMajor.id,
            code,
            name,
            folder_name,
            keywords
          })
        });
        const data = await res.json();
        if (data.ok) {
          showToast(`Đã thêm môn học "${name}" thành công!`);
          document.getElementById('newSubjectCode').value = '';
          document.getElementById('newSubjectName').value = '';
          document.getElementById('newSubjectFolder').value = '';
          document.getElementById('newSubjectKeywords').value = '';
          toggleAddSubjectForm();
          await selectAdminMajor(adminSelectedMajor.id);
        } else {
          alert('Lỗi: ' + (data.error || 'Không thể tạo môn học'));
        }
      } catch (e) {
        alert('Lỗi kết nối: ' + e);
      }
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

    def _is_admin(self, current_user: Optional[Dict[str, Any]]) -> bool:
        """Kiểm tra xem người dùng hiện tại có phải là Admin hệ thống không."""
        if not current_user:
            return False
        user_email = current_user.get("email", "").strip().lower()
        root_email = "xuanngocit@gmail.com"
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                root_email = cfg.get("root_account_email", "xuanngocit@gmail.com")
        except Exception:
            pass
        return user_email == root_email.strip().lower()

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
                "is_admin": self._is_admin(current_user),
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

        if path == "/api/majors":
            if not self.database:
                self._send_json({"ok": False, "majors": []}, 500)
                return
            majors = self.database.get_all_majors()
            self._send_json({"ok": True, "majors": majors})
            return

        if path.startswith("/api/majors/") and path.endswith("/subjects"):
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[1] == "majors" and parts[3] == "subjects":
                try:
                    major_id = int(parts[2])
                    subjects = self.database.get_subjects_by_major(major_id) if self.database else []
                    self._send_json({"ok": True, "subjects": subjects})
                    return
                except ValueError:
                    self._send_json({"ok": False, "error": "Invalid major ID"}, 400)
                    return

        if path == "/api/admin/majors":
            if not self._is_admin(current_user):
                self._send_json({"ok": False, "error": "Forbidden: Admin access required"}, 403)
                return
            majors = self.database.get_all_majors() if self.database else []
            self._send_json({"ok": True, "majors": majors})
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

        if path == "/api/user/select-major":
            if not current_user or not self.database:
                self._send_json({"ok": False, "error": "Vui lòng đăng nhập tài khoản"}, 401)
                return

            major_id = body.get("major_id")
            if not major_id:
                self._send_json({"ok": False, "error": "Vui lòng chọn chuyên ngành"}, 400)
                return

            try:
                major_id_int = int(major_id)
                major = self.database.get_major_by_id(major_id_int)
                if not major:
                    self._send_json({"ok": False, "error": "Chuyên ngành không tồn tại"}, 404)
                    return

                # Cập nhật major_id cho user trong DB
                self.database.set_user_major(current_user["email"], major_id_int)
                current_user["major_id"] = major_id_int

                # Tự động tạo cây thư mục 4 cấp con chuẩn mực
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                config_root = cfg.get("root_folder", "")
                user_storage = get_user_storage_folder(current_user, config_root)
                major_dir = user_storage / major["folder_name"]
                major_dir.mkdir(parents=True, exist_ok=True)

                subjects = self.database.get_subjects_by_major(major_id_int)
                for sub in subjects:
                    sub_dir = major_dir / sub["folder_name"]
                    (sub_dir / "01_Giao_Trinh").mkdir(parents=True, exist_ok=True)
                    (sub_dir / "02_Slide").mkdir(parents=True, exist_ok=True)
                    (sub_dir / "03_Tai_Lieu_Tham_Khao").mkdir(parents=True, exist_ok=True)
                    (sub_dir / "04_On_Thi").mkdir(parents=True, exist_ok=True)

                self._send_json({
                    "ok": True,
                    "major": major,
                    "subjects_count": len(subjects),
                    "storage_path": str(major_dir),
                })
                return
            except Exception as exc:
                logger.error("Lỗi khi chọn chuyên ngành: %s", exc, exc_info=True)
                self._send_json({"ok": False, "error": str(exc)}, 500)
                return


        if path == "/api/admin/majors":
            if not self._is_admin(current_user):
                self._send_json({"ok": False, "error": "Forbidden: Admin access required"}, 403)
                return

            code = body.get("code", "").strip()
            name = body.get("name", "").strip()
            folder_name = body.get("folder_name", "").strip()
            description = body.get("description", "").strip()

            if not code or not name or not folder_name:
                self._send_json({"ok": False, "error": "Vui lòng cung cấp đầy đủ code, name, folder_name"}, 400)
                return

            try:
                major_id = self.database.add_major(code, name, folder_name, description)
                self._send_json({"ok": True, "major_id": major_id, "message": "Thêm chuyên ngành thành công"})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, 500)
            return

        if path == "/api/admin/subjects":
            if not self._is_admin(current_user):
                self._send_json({"ok": False, "error": "Forbidden: Admin access required"}, 403)
                return

            major_id = body.get("major_id")
            code = body.get("code", "").strip()
            name = body.get("name", "").strip()
            folder_name = body.get("folder_name", "").strip()
            keywords = body.get("keywords", "[]")
            if isinstance(keywords, list):
                keywords = json.dumps(keywords, ensure_ascii=False)

            if not major_id or not code or not name or not folder_name:
                self._send_json({"ok": False, "error": "Vui lòng cung cấp đầy đủ major_id, code, name, folder_name"}, 400)
                return

            try:
                sub_id = self.database.add_subject(
                    major_id=int(major_id),
                    code=code,
                    name=name,
                    folder_name=folder_name,
                    keywords=keywords,
                    is_default=1,
                    created_by=current_user.get("email", "admin")
                )
                self._send_json({"ok": True, "subject_id": sub_id, "message": "Thêm môn học thành công"})
            except Exception as exc:
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
