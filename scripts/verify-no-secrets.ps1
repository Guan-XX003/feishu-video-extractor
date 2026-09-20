$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir

$InsideGit = $false
try {
    git rev-parse --is-inside-work-tree 2>$null | Out-Null
    $InsideGit = ($LASTEXITCODE -eq 0)
} catch {}

$Tracked = if ($InsideGit) {
    git ls-files
} else {
    Get-ChildItem -Recurse -File | ForEach-Object { $_.FullName.Substring($ProjectDir.Length + 1).Replace("\\", "/") }
}
$Forbidden = $Tracked | Where-Object { $_ -match '(^|/)(cookies[^/]*\.txt|\.env)$' }
if ($Forbidden) {
    Write-Host "ERROR: tracked cookie or .env file detected:"
    $Forbidden | ForEach-Object { Write-Host $_ }
    exit 1
}

$Pattern = '(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|gho_[A-Za-z0-9]{20,}|sessionid\s*[=:]\s*[A-Za-z0-9%_-]{16,}|refreshToken\s*[=:]|accessToken\s*[=:])'
if ($InsideGit) {
    $Matches = git grep -nEI $Pattern -- ':!package-lock.json' ':!field-shortcut/package-lock.json'
} else {
    $Matches = Get-ChildItem -Recurse -File |
        Where-Object { $_.Name -ne 'package-lock.json' -and $_.FullName -notmatch '(node_modules|\.venv)' } |
        Select-String -Pattern $Pattern
}
if ($Matches) {
    Write-Host "ERROR: possible secret material detected:"
    Write-Host $Matches
    exit 1
}

Write-Host "No tracked Cookie, .env, or obvious access-token material detected."
