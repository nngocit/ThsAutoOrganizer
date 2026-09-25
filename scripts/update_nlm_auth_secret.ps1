<#
.SYNOPSIS
  Cập nhật phiên NotebookLM lên GitHub Secret NOTEBOOKLM_AUTH_B64 (dùng khi cookie hết hạn).

.DESCRIPTION
  Cookie Google hết hạn sau vài tuần. Khi "NLM Drain" báo lỗi smoke test:
    1) Nếu chưa đăng nhập: chạy  nlm login  (mở trình duyệt, đăng nhập Google)
    2) Chạy script này để sinh lại auth.json GỐC và đẩy secret — không cần tay thao tác base64.

  Script:
    - Kiểm tra profile hiện có (cookies.json)
    - Sinh ~/.notebooklm-mcp-cli/auth.json (định dạng AuthTokens mà CLI >= 0.11 đọc)
    - base64 → `gh secret set NOTEBOOKLM_AUTH_B64`

.PARAMETER CheckOnly
  Chỉ kiểm tra phiên còn hiệu lực hay không (nlm notebook list) — không đụng secret.

.PARAMETER Repo
  Repo GitHub chứa secret. Mặc định: nngocit/ThsAutoOrganizer

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\update_nlm_auth_secret.ps1 -CheckOnly
  powershell -ExecutionPolicy Bypass -File scripts\update_nlm_auth_secret.ps1
#>
[CmdletBinding()]
param(
  [switch]$CheckOnly,
  [string]$Repo = 'nngocit/ThsAutoOrganizer'
)
$ErrorActionPreference = 'Stop'

$storage  = Join-Path $env:USERPROFILE '.notebooklm-mcp-cli'
$cookies  = Join-Path $storage 'profiles\default\cookies.json'
$authJson = Join-Path $storage 'auth.json'

if ($CheckOnly) {
  Write-Host "Đang kiểm tra phiên NotebookLM (nlm notebook list)..."
  & nlm notebook list --json > $null 2>&1
  if ($LASTEXITCODE -eq 0) {
    Write-Host "OK — phiên NotebookLM còn hiệu lực." -ForegroundColor Green
    exit 0
  }
  Write-Host "HẾT HẠN hoặc lỗi — chạy: nlm login  rồi chạy lại script này (không có -CheckOnly)." -ForegroundColor Red
  exit 1
}

if (-not (Test-Path $cookies)) {
  throw "Không tìm thấy $cookies — hãy chạy 'nlm login' trước."
}

# 1) Sinh auth.json GỐC từ profile (định dạng AuthTokens — chỉ đọc cookies.json/metadata.json của profile)
$py = @'
import json, time, pathlib
p = pathlib.Path.home() / ".notebooklm-mcp-cli" / "profiles" / "default"
cookies = json.loads((p / "cookies.json").read_text(encoding="utf-8"))
meta = json.loads((p / "metadata.json").read_text(encoding="utf-8")) if (p / "metadata.json").exists() else {}
data = {
    "cookies": cookies,
    "csrf_token": meta.get("csrf_token") or "",
    "session_id": meta.get("session_id") or "",
    "build_label": meta.get("build_label") or "",
    "base_host": meta.get("base_host") or "",
    "extracted_at": time.time(),
}
out = pathlib.Path.home() / ".notebooklm-mcp-cli" / "auth.json"
out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Đã sinh {out} ({out.stat().st_size} bytes, {len(cookies)} cookies)")
'@
$py | python -
if ($LASTEXITCODE -ne 0) { throw "Sinh auth.json thất bại (cần python trong PATH)." }

# 2) Đẩy lên GitHub Secret (pipe để tránh giới hạn độ dài lệnh)
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "Chưa cài gh CLI: winget install GitHub.cli" }
$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($authJson))
$b64 | gh secret set NOTEBOOKLM_AUTH_B64 --repo $Repo
if ($LASTEXITCODE -ne 0) { throw "gh secret set thất bại — kiểm tra đã 'gh auth login' chưa." }

Write-Host "OK — đã cập nhật NOTEBOOKLM_AUTH_B64 ($($b64.Length) ký tự base64) trên repo $Repo." -ForegroundColor Green
Write-Host "Chạy thử: gh workflow run nlm-drain.yml -f dry_run=false -f max_passes=1"
