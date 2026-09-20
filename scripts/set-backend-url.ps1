param(
    [Parameter(Mandatory = $true)]
    [string]$BackendUrl
)

$ErrorActionPreference = "Stop"
$BackendUrl = $BackendUrl.TrimEnd("/")
if ($BackendUrl -notmatch '^https://[A-Za-z0-9.-]+(:[0-9]+)?$') {
    throw "Production BACKEND_URL must be an HTTPS origin without a path."
}

$ProjectDir = Split-Path -Parent $PSScriptRoot
$ConfigFile = Join-Path $ProjectDir "field-shortcut/src/config.ts"
$Text = Get-Content $ConfigFile -Raw -Encoding UTF8
$Pattern = 'export const BACKEND_URL = [''\"][^''\"]+[''\"];'
$Replacement = "export const BACKEND_URL = '$BackendUrl';"
$Updated = [regex]::Replace($Text, $Pattern, $Replacement)
if ($Updated -eq $Text) {
    throw "Could not update BACKEND_URL."
}
Set-Content $ConfigFile $Updated -Encoding UTF8
Write-Host "Updated field-shortcut backend URL to: $BackendUrl"
