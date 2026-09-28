# One-time setup on Windows (PowerShell).
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$python = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
$pyArgs = if ($python -eq "py") { @("-3") } else { @() }

Write-Host "==> Creating Python virtual environment (.venv)"
& $python @pyArgs -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "==> Installing and building the frontend"
Push-Location frontend
npm ci
npm run build
Pop-Location

& .\.venv\Scripts\python.exe -m memory_museum doctor
Write-Host ""
Write-Host "Done. Try the demo:  .\.venv\Scripts\python.exe -m memory_museum demo --open"
