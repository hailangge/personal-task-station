param(
    [string]$OutputDir = "dist\windows-client",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if ($DryRun) {
    Write-Host "[dry-run] would package Windows client into $OutputDir"
    exit 0
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.12+ is required on the Windows packaging host."
}

Remove-Item -Recurse -Force $OutputDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $OutputDir | Out-Null
$Venv = Join-Path $OutputDir ".venv-build"
python -m venv $Venv
$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -e ".[client]" pyinstaller
& $Python -m PyInstaller --name pts-client --onefile --windowed --collect-all PySide6 src\personal_task_station\client\main.py

New-Item -ItemType Directory -Force (Join-Path $OutputDir "bin") | Out-Null
Copy-Item "dist\pts-client.exe" (Join-Path $OutputDir "bin\pts-client.exe") -Force
@"
Run bin\pts-client.exe. Configure server URL, API key, and certificate paths in the Connection tab on first launch.
This script should be run on a Windows host or Windows CI runner.
"@ | Set-Content -Encoding UTF8 (Join-Path $OutputDir "README.txt")
Write-Host "Windows client package written to $OutputDir"
