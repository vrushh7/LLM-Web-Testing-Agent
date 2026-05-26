$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

Write-Host "Cleaning old HINSA AI dev servers..."
& (Join-Path $root "stop-local.ps1")

Start-Sleep -Seconds 2

Write-Host "Starting backend at http://127.0.0.1:8000 ..."
Start-Process powershell.exe -WorkingDirectory $backend -ArgumentList @(
    "-NoExit",
    "-Command",
    ".\.venv\Scripts\python.exe run.py"
)

Start-Sleep -Seconds 3

Write-Host "Starting frontend at http://127.0.0.1:5173 ..."
Start-Process powershell.exe -WorkingDirectory $frontend -ArgumentList @(
    "-NoExit",
    "-Command",
    "npm run dev -- --host 127.0.0.1"
)

Write-Host ""
Write-Host "Open: http://127.0.0.1:5173/"
Write-Host "API docs: http://127.0.0.1:8000/docs"
