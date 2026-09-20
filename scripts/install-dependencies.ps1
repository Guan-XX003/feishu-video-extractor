$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir

npm ci
Push-Location field-shortcut
npm ci
Pop-Location

$PythonLauncher = if (Get-Command py -ErrorAction SilentlyContinue) { @("py", "-3.11") } else { @("python") }
if ($PythonLauncher.Count -eq 2) {
    & $PythonLauncher[0] $PythonLauncher[1] -m venv backend/.venv
} else {
    & $PythonLauncher[0] -m venv backend/.venv
}
& backend/.venv/Scripts/python.exe -m pip install --upgrade pip
& backend/.venv/Scripts/pip.exe install -r backend/requirements.txt

Write-Host "Dependencies installed. Run scripts/doctor.ps1 again, then execute tests."
