#!/usr/bin/env pwsh
# deploy_setup.ps1 — Script hướng dẫn deploy ThsAutoOrganizer lên Cloudflare
# Chạy script này trong PowerShell THÔNG THƯỜNG (không qua IDE)
# Cách chạy: .\cloudflare\deploy_setup.ps1

Set-Location "$PSScriptRoot\workers"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  ThsAutoOrganizer — Deploy Setup" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# ─── BƯỚC 1: Cập nhật Wrangler ─────────────────────────────────────────────
Write-Host "[BƯỚC 1] Cập nhật Wrangler lên v4..." -ForegroundColor Yellow
npm install --save-dev wrangler@4 --silent
Write-Host "✓ Wrangler đã cập nhật" -ForegroundColor Green
Write-Host ""

# ─── BƯỚC 2: Đăng nhập Cloudflare ──────────────────────────────────────────
Write-Host "[BƯỚC 2] Đăng nhập Cloudflare..." -ForegroundColor Yellow
Write-Host "         Trình duyệt sẽ tự mở. Đăng nhập tài khoản Cloudflare của bạn." -ForegroundColor Gray
npx wrangler login
Write-Host "✓ Đã đăng nhập Cloudflare" -ForegroundColor Green
Write-Host ""

# ─── BƯỚC 3: Tìm file Firebase Service Account ─────────────────────────────
Write-Host "[BƯỚC 3] Firebase Service Account JSON" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Nếu chưa có file JSON, hãy tạo theo hướng dẫn:" -ForegroundColor Gray
Write-Host "  1. Vào: https://console.firebase.google.com → Project của bạn" -ForegroundColor Gray
Write-Host "  2. Project Settings → Service Accounts" -ForegroundColor Gray
Write-Host "  3. Nhấn 'Generate new private key' → Download file .json" -ForegroundColor Gray
Write-Host ""

$jsonPath = Read-Host "Nhập đường dẫn đầy đủ tới file Firebase .json (vd: C:\Users\xuann\Downloads\firebase-key.json)"

if (-not (Test-Path $jsonPath)) {
    Write-Host "✗ File không tìm thấy: $jsonPath" -ForegroundColor Red
    Write-Host "  Vui lòng kiểm tra lại đường dẫn." -ForegroundColor Red
    exit 1
}

# Minify JSON (loại bỏ xuống dòng để paste vào wrangler)
$jsonContent = Get-Content $jsonPath -Raw | ConvertFrom-Json | ConvertTo-Json -Compress
Write-Host "✓ Đã đọc Firebase JSON ($($jsonContent.Length) ký tự)" -ForegroundColor Green
Write-Host ""

# ─── BƯỚC 4: Set tất cả secrets ────────────────────────────────────────────
Write-Host "[BƯỚC 4] Set Wrangler Secrets..." -ForegroundColor Yellow

# FIREBASE_SERVICE_ACCOUNT
Write-Host "  → FIREBASE_SERVICE_ACCOUNT" -ForegroundColor Gray
$jsonContent | npx wrangler secret put FIREBASE_SERVICE_ACCOUNT
Write-Host ""

# GOOGLE_CLIENT_ID
Write-Host "  → GOOGLE_CLIENT_ID" -ForegroundColor Gray
$googleClientId = Read-Host "  Nhập Google Client ID (kết thúc bằng .apps.googleusercontent.com)"
$googleClientId | npx wrangler secret put GOOGLE_CLIENT_ID
Write-Host ""

# GOOGLE_CLIENT_SECRET
Write-Host "  → GOOGLE_CLIENT_SECRET" -ForegroundColor Gray
$googleClientSecret = Read-Host "  Nhập Google Client Secret"
$googleClientSecret | npx wrangler secret put GOOGLE_CLIENT_SECRET
Write-Host ""

# AGENT_SECRET
Write-Host "  → AGENT_SECRET (tạo random nếu chưa có)" -ForegroundColor Gray
$agentSecret = [System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
Write-Host "  Secret được tạo tự động: $agentSecret" -ForegroundColor Cyan
Write-Host "  (Lưu lại secret này để dùng trong config.json của Python agent)" -ForegroundColor Gray
$agentSecret | npx wrangler secret put AGENT_SECRET
Write-Host ""

# ─── BƯỚC 5: Deploy Worker ─────────────────────────────────────────────────
Write-Host "[BƯỚC 5] Deploy Cloudflare Worker..." -ForegroundColor Yellow
npx wrangler deploy src/index.js

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "✅ Worker deployed thành công!" -ForegroundColor Green
Write-Host ""
Write-Host "AGENT_SECRET để dùng trong config.json:" -ForegroundColor Yellow
Write-Host $agentSecret -ForegroundColor Cyan
Write-Host ""
Write-Host "Bước tiếp theo — Deploy Cloudflare Pages:" -ForegroundColor Yellow
Write-Host "  cd ..\pages" -ForegroundColor Gray
Write-Host "  npx wrangler pages deploy src --project-name=ths-organizer" -ForegroundColor Gray
Write-Host "==================================================" -ForegroundColor Cyan
