param(
    [Parameter(Mandatory = $true)]
    [string]$BackendUrl,
    [Parameter(Mandatory = $true)]
    [string]$WorkerToken,
    [ValidateSet("chrome", "edge", "firefox")]
    [string]$Browser = "chrome"
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallRoot = Join-Path $env:LOCALAPPDATA "FeishuVideoWorker"
$TaskName = "Feishu Video Download Worker"
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if ($WorkerToken.Length -lt 32) {
    throw "WorkerToken must contain at least 32 characters."
}

$KnownPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
if (Test-Path $KnownPython) {
    $PythonCommand = $KnownPython
    $PythonArgs = @()
} else {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $PythonCommand -and $Python) {
    $PythonCommand = $Python.Source
    $PythonArgs = @("-3")
} elseif (-not $PythonCommand) {
    $Python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $Python) {
        throw "Python 3 was not found. Install Python 3.11 or newer and retry."
    }
    $PythonCommand = $Python.Source
    $PythonArgs = @()
}

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
Copy-Item (Join-Path $SourceRoot "worker.py") $InstallRoot -Force
Copy-Item (Join-Path $SourceRoot "run-worker.ps1") $InstallRoot -Force
Copy-Item (Join-Path $SourceRoot "open-douyin-login.ps1") $InstallRoot -Force
Copy-Item (Join-Path $SourceRoot "requirements.txt") $InstallRoot -Force

$VenvPath = Join-Path $InstallRoot ".venv"
& $PythonCommand @PythonArgs -m venv $VenvPath
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $InstallRoot "requirements.txt")

$ConfigPath = Join-Path $InstallRoot "config.json"
$BrowserProfile = ""
if ($Browser -in @("chrome", "edge")) {
    $BrowserProfile = Join-Path $InstallRoot "browser-profile\Default"
}
$Config = [ordered]@{
    backend_url = $BackendUrl.TrimEnd("/")
    worker_token = $WorkerToken
    worker_id = $env:COMPUTERNAME
    browser = $Browser
    browser_profile = $BrowserProfile
}
$Config | ConvertTo-Json | Set-Content -Path $ConfigPath -Encoding UTF8
& icacls $ConfigPath /inheritance:r /grant:r "${CurrentUser}:(F)" | Out-Null

if ($Browser -eq "edge") {
    $ShortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "Douyin Worker Login.lnk"
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = "powershell.exe"
    $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $InstallRoot 'open-douyin-login.ps1')`""
    $Shortcut.WorkingDirectory = $InstallRoot
    $Shortcut.Description = "Open the dedicated Douyin login used by the Feishu download worker."
    $Shortcut.Save()
}

$WorkerScript = Join-Path $InstallRoot "worker.py"
$Action = New-ScheduledTaskAction `
    -Execute $VenvPython `
    -Argument "-u `"$WorkerScript`"" `
    -WorkingDirectory $InstallRoot
$Triggers = @(
    (New-ScheduledTaskTrigger -AtStartup),
    (New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser)
)
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 20 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650)
$Principal = New-ScheduledTaskPrincipal `
    -UserId $CurrentUser `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Triggers `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Downloads authorized media for the Feishu field shortcut using this user's browser session." `
    -Force `
    -ErrorAction Stop | Out-Null

Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
Write-Host "Installed and started: $TaskName"
Write-Host "Worker directory: $InstallRoot"
