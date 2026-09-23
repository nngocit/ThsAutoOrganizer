param()
Set-Location "$PSScriptRoot\workers"

Write-Host "ThsAutoOrganizer -- Deploy Setup" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# BUOC 1: Cap nhat Wrangler v4
Write-Host "[1] Updating Wrangler to v4..." -ForegroundColor Yellow
npm install --save-dev wrangler@4 --silent
Write-Host "OK - Wrangler updated" -ForegroundColor Green
Write-Host ""

# BUOC 2: Dang nhap Cloudflare (mo browser)
Write-Host "[2] Login to Cloudflare (browser will open)..." -ForegroundColor Yellow
npx wrangler login
Write-Host "OK - Logged in" -ForegroundColor Green
Write-Host ""

# BUOC 3: Firebase Service Account JSON
Write-Host "[3] Firebase Service Account" -ForegroundColor Yellow
Write-Host "    Get file from: Firebase Console -> Project Settings -> Service Accounts -> Generate new private key" -ForegroundColor Gray
Write-Host ""
$jsonPath = Read-Host "    Enter full path to Firebase .json file"
if (-not (Test-Path $jsonPath)) {
    Write-Host "ERROR: File not found: $jsonPath" -ForegroundColor Red
    exit 1
}
$jsonRaw = Get-Content $jsonPath -Raw
$jsonObj = $jsonRaw | ConvertFrom-Json
$jsonMinified = $jsonObj | ConvertTo-Json -Compress -Depth 10
Write-Host "    Read OK ($($jsonMinified.Length) chars)" -ForegroundColor Green
Write-Host ""

# BUOC 4: Set secrets
Write-Host "[4] Setting Wrangler secrets..." -ForegroundColor Yellow

Write-Host "    -> FIREBASE_SERVICE_ACCOUNT" -ForegroundColor Gray
$jsonMinified | npx wrangler secret put FIREBASE_SERVICE_ACCOUNT

Write-Host ""
Write-Host "    -> GOOGLE_CLIENT_ID" -ForegroundColor Gray
$gClientId = Read-Host "    Enter Google Client ID (ends with .apps.googleusercontent.com)"
$gClientId | npx wrangler secret put GOOGLE_CLIENT_ID

Write-Host ""
Write-Host "    -> GOOGLE_CLIENT_SECRET" -ForegroundColor Gray
$gClientSecret = Read-Host "    Enter Google Client Secret"
$gClientSecret | npx wrangler secret put GOOGLE_CLIENT_SECRET

Write-Host ""
Write-Host "    -> AGENT_SECRET (auto-generated)" -ForegroundColor Gray
$bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
$agentSecret = [System.Convert]::ToBase64String($bytes)
$agentSecret | npx wrangler secret put AGENT_SECRET
Write-Host "    AGENT_SECRET = $agentSecret" -ForegroundColor Cyan
Write-Host "    (Save this! Add to config.json as agent_secret)" -ForegroundColor Gray

Write-Host ""

# BUOC 5: Deploy Worker
Write-Host "[5] Deploying Cloudflare Worker..." -ForegroundColor Yellow
npx wrangler deploy src/index.js

Write-Host ""
Write-Host "==================================" -ForegroundColor Cyan
Write-Host "Worker deployed!" -ForegroundColor Green
Write-Host ""
Write-Host "AGENT_SECRET: $agentSecret" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next step - Deploy Pages:" -ForegroundColor Yellow
Write-Host "  cd ..\pages" -ForegroundColor Gray
Write-Host "  npx wrangler pages deploy src --project-name=ths-organizer" -ForegroundColor Gray
Write-Host "==================================" -ForegroundColor Cyan
