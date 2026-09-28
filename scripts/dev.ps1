# Development mode on Windows: API server + Vite dev server with hot reload.
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1            (uses the demo data)
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -DataDir data
param([string]$DataDir = "data\demo")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path "$DataDir\museum.db") -and $DataDir -eq "data\demo") {
  & .\.venv\Scripts\python.exe -m memory_museum demo --no-serve
}
$api = Start-Process -PassThru -NoNewWindow .\.venv\Scripts\python.exe -ArgumentList "-m", "memory_museum", "serve", "--data-dir", $DataDir
try {
  Push-Location frontend
  Write-Host "Open http://127.0.0.1:5173/"
  npm run dev
} finally {
  Pop-Location
  Stop-Process -Id $api.Id -ErrorAction SilentlyContinue
}
