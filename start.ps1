# SuezCanal — avvio completo
# Esegui: powershell -ExecutionPolicy Bypass -File start.ps1

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

$PYTHON = "C:\Users\repub\AppData\Local\Programs\Python\Python312\python.exe"
$FRONTEND_DIR = "$ROOT\watch\frontend"
$PORT = 8000

# Libera porta 8000 se occupata
$taken = Get-NetTCPConnection -LocalPort $PORT -ErrorAction SilentlyContinue
if ($taken) {
    $taken | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

Write-Host ""
Write-Host "=== SuezCanal ===" -ForegroundColor Cyan
Write-Host ""

# ── Backend ──────────────────────────────────────────────────────────────────
Write-Host "[1/2] Backend  -> http://localhost:$PORT" -ForegroundColor Green
$env:MOCK = "false"

$backend = Start-Process -FilePath $PYTHON `
    -ArgumentList "-m", "uvicorn", "core.api.main:app",
                  "--host", "0.0.0.0", "--port", "$PORT" `
    -WorkingDirectory $ROOT `
    -PassThru -NoNewWindow

Start-Sleep -Seconds 4

# ── Frontend ─────────────────────────────────────────────────────────────────
Write-Host "[2/2] Frontend -> http://localhost:5173" -ForegroundColor Green

Remove-Item -Recurse -Force "$FRONTEND_DIR\node_modules\.vite" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$ROOT\node_modules\.vite" -ErrorAction SilentlyContinue

$env:VITE_API_URL = "http://localhost:$PORT"

# Su Windows npx e' un .cmd — va lanciato tramite cmd.exe
$frontend = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npx vite --port 5173 --force" `
    -WorkingDirectory $FRONTEND_DIR `
    -PassThru -NoNewWindow

Start-Sleep -Seconds 4

Write-Host ""
Write-Host "  Backend:  http://localhost:$PORT" -ForegroundColor White
Write-Host "  Docs API: http://localhost:$PORT/docs" -ForegroundColor White
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor White
Write-Host ""
Write-Host "Premi INVIO per fermare tutto..." -ForegroundColor Yellow
Read-Host | Out-Null

Stop-Process -Id $backend.Id  -Force -ErrorAction SilentlyContinue
Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
Write-Host "Fermato." -ForegroundColor Red
