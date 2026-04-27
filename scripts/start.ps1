# SeaCommons local dev startup
# Runs API from apps/api and Vite from apps/web

$ROOT = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$API_DIR = Join-Path $ROOT "apps\api"
$WEB_DIR = Join-Path $ROOT "apps\web"
Set-Location $ROOT

$PORT = 8000

$taken = Get-NetTCPConnection -LocalPort $PORT -ErrorAction SilentlyContinue
if ($taken) {
    $taken | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

Write-Host ""
Write-Host "=== SeaCommons Dev ===" -ForegroundColor Cyan
Write-Host ""

$env:MOCK = if ($env:MOCK) { $env:MOCK } else { "true" }
$env:DEMO_PUBLIC_MODE = if ($env:DEMO_PUBLIC_MODE) { $env:DEMO_PUBLIC_MODE } else { "true" }

Write-Host "[1/2] Backend  -> http://localhost:$PORT" -ForegroundColor Green
$backend = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "core.api.main:app", "--host", "0.0.0.0", "--port", "$PORT", "--reload" `
    -WorkingDirectory $API_DIR `
    -PassThru -NoNewWindow

Start-Sleep -Seconds 3

Write-Host "[2/2] Frontend -> http://localhost:5173" -ForegroundColor Green
$frontend = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm run dev" `
    -WorkingDirectory $WEB_DIR `
    -PassThru -NoNewWindow

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "  Backend:  http://localhost:$PORT" -ForegroundColor White
Write-Host "  Docs API: http://localhost:$PORT/docs" -ForegroundColor White
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor White
Write-Host ""
Write-Host "Premi INVIO per fermare tutto..." -ForegroundColor Yellow
Read-Host | Out-Null

Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
Write-Host "Fermato." -ForegroundColor Red
