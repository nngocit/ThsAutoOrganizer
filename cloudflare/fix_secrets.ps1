# fix_secrets.ps1 — Set lai AGENT_SECRET va deploy Worker
# Chay sau khi da xac thuc email Cloudflare

Set-Location "$PSScriptRoot\workers"

Write-Host "=== Fix AGENT_SECRET + Deploy Worker ===" -ForegroundColor Cyan
Write-Host ""

# Sinh AGENT_SECRET bang cach tuong thich voi moi phien ban PowerShell
$guid1 = [System.Guid]::NewGuid().ToString("N")
$guid2 = [System.Guid]::NewGuid().ToString("N")
$agentSecret = "$guid1$guid2"
Write-Host "AGENT_SECRET da tao: $agentSecret" -ForegroundColor Yellow
Write-Host "(Luu lai de dung trong config.json)" -ForegroundColor Gray
Write-Host ""

# Set AGENT_SECRET
Write-Host "Setting AGENT_SECRET..." -ForegroundColor Yellow
$agentSecret | npx wrangler secret put AGENT_SECRET
Write-Host ""

# Deploy Worker
Write-Host "Deploying Worker..." -ForegroundColor Yellow
npx wrangler deploy src/index.js
Write-Host ""

Write-Host "=== XONG ===" -ForegroundColor Green
Write-Host "AGENT_SECRET: $agentSecret" -ForegroundColor Cyan
Write-Host ""
Write-Host "Buoc tiep theo - Deploy Pages:" -ForegroundColor Yellow
Write-Host "  cd ..\pages" -ForegroundColor Gray
Write-Host "  npx wrangler pages deploy src --project-name=ths-organizer" -ForegroundColor Gray
