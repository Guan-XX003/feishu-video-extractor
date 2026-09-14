$ErrorActionPreference = "Stop"

$WorkerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $WorkerRoot "config.json"
$PythonPath = Join-Path $WorkerRoot ".venv\Scripts\python.exe"
$LogPath = Join-Path $WorkerRoot "worker.log"

if (-not (Test-Path $ConfigPath)) {
    throw "Worker config not found: $ConfigPath"
}
if (-not (Test-Path $PythonPath)) {
    throw "Worker Python not found: $PythonPath"
}

$Config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$env:FEISHU_WORKER_BACKEND_URL = $Config.backend_url
$env:FEISHU_WORKER_TOKEN = $Config.worker_token
$env:FEISHU_WORKER_ID = $Config.worker_id
$env:FEISHU_WORKER_BROWSER = $Config.browser
$env:FEISHU_WORKER_BROWSER_PROFILE = $Config.browser_profile

& $PythonPath -u (Join-Path $WorkerRoot "worker.py")
exit $LASTEXITCODE
