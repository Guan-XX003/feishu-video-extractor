$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$Errors = 0

function Test-Command([string]$Name, [bool]$Required) {
    $Command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($Command) {
        Write-Host "OK   $Name`t$($Command.Source)"
    } elseif ($Required) {
        Write-Host "MISS $Name`trequired"
        $script:Errors++
    } else {
        Write-Host "INFO $Name`toptional/not installed"
    }
}

Write-Host "Project: $ProjectDir"
Test-Command git $true
Test-Command node $true
Test-Command npm $true
Test-Command gh $false
Test-Command railway $false
Test-Command docker $false

$PythonCommand = Get-Command py -ErrorAction SilentlyContinue
if ($PythonCommand) {
    try {
        $PythonVersion = & py -3.11 --version 2>&1
        Write-Host "OK   Python`t$PythonVersion"
    } catch {
        Write-Host "MISS Python 3.10+ required"
        $Errors++
    }
} else {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        $PythonCheck = & python -c "import sys; print(int(sys.version_info >= (3, 10)))"
        if ($PythonCheck -eq "1") {
            Write-Host "OK   Python`t$(& python --version 2>&1)"
        } else {
            Write-Host "MISS Python 3.10+ required"
            $Errors++
        }
    } else {
        Write-Host "MISS Python 3.10+ required"
        $Errors++
    }
}

foreach ($File in @("backend/app/main.py", "field-shortcut/src/index.ts", "field-shortcut/src/config.ts", "backend/railway.env.example")) {
    if (Test-Path (Join-Path $ProjectDir $File)) {
        Write-Host "OK   file: $File"
    } else {
        Write-Host "MISS file: $File"
        $Errors++
    }
}

if ($Errors -gt 0) {
    throw "Environment check failed with $Errors issue(s)."
}
Write-Host "Environment check passed. Confirm Node.js 20+ and Python 3.10+."
