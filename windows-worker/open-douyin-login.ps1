$ErrorActionPreference = "Stop"

$WorkerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProfileRoot = Join-Path $WorkerRoot "browser-profile"
$EdgeCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"),
    (Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe")
)
$EdgePath = $EdgeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $EdgePath) {
    throw "Microsoft Edge was not found."
}

New-Item -ItemType Directory -Force -Path $ProfileRoot | Out-Null
Start-Process `
    -FilePath $EdgePath `
    -ArgumentList @("--user-data-dir=`"$ProfileRoot`"", "https://www.douyin.com/")
