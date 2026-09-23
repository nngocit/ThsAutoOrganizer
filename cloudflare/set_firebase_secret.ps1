param(
    [string]$JsonPath = ""
)
Set-Location "$PSScriptRoot\workers"

Write-Host "=== Set FIREBASE_SERVICE_ACCOUNT Secret ===" -ForegroundColor Cyan
Write-Host ""

if (-not $JsonPath) {
    Write-Host "Chua co file Firebase JSON." -ForegroundColor Yellow
    Write-Host "Tai file tu: Firebase Console -> Project Settings -> Service Accounts -> Generate new private key" -ForegroundColor Gray
    Write-Host ""
    $JsonPath = Read-Host "Nhap duong dan day du den file Firebase .json"
}

if (-not (Test-Path $JsonPath)) {
    Write-Host "ERROR: Khong tim thay file: $JsonPath" -ForegroundColor Red
    exit 1
}

Write-Host "Doc file: $JsonPath" -ForegroundColor Gray
$jsonObj = Get-Content $JsonPath -Raw | ConvertFrom-Json
$jsonMinified = $jsonObj | ConvertTo-Json -Compress -Depth 10
Write-Host "Doc OK - project_id: $($jsonObj.project_id)" -ForegroundColor Green
Write-Host ""

Write-Host "Setting FIREBASE_SERVICE_ACCOUNT..." -ForegroundColor Yellow
$jsonMinified | npx wrangler secret put FIREBASE_SERVICE_ACCOUNT

Write-Host ""
Write-Host "Setting GOOGLE_CLIENT_ID..." -ForegroundColor Yellow
$gClientId = Read-Host "Nhap Google Client ID (ends with .apps.googleusercontent.com)"
$gClientId | npx wrangler secret put GOOGLE_CLIENT_ID

Write-Host ""
Write-Host "Kiem tra secrets hien tai:" -ForegroundColor Yellow
npx wrangler secret list

Write-Host ""
Write-Host "Redeploy Worker..." -ForegroundColor Yellow
npx wrangler deploy src/index.js

Write-Host ""
Write-Host "=== XONG - Test lai Agent ===" -ForegroundColor Green
Write-Host "Chay: python -m local_agent.main" -ForegroundColor Cyan
