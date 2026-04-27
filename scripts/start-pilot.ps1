# SuezCanal pilot startup
$ROOT = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ROOT

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker non trovato. Usa Docker Desktop oppure avvio locale manuale."
    exit 1
}

docker compose -f deploy/docker-compose.pilot.yml up --build
