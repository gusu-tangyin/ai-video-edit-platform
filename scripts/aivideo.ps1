param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = 'Stop'
$SkillRoot = Split-Path -Parent $PSScriptRoot
$ProjectPython = Join-Path $SkillRoot 'runtime\.venv\Scripts\python.exe'
$BasePython = if ($env:AIVIDEO_BASE_PYTHON) {
    $env:AIVIDEO_BASE_PYTHON
} elseif (Test-Path -LiteralPath 'F:\workspace\runtime\python\base\python.exe') {
    'F:\workspace\runtime\python\base\python.exe'
} else {
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1).Source
}

$Python = if (Test-Path -LiteralPath $ProjectPython) {
    $ProjectPython
} elseif ($BasePython -and (Test-Path -LiteralPath $BasePython)) {
    $BasePython
} else {
    throw "Python was not found. Run scripts\setup.ps1 or set AIVIDEO_BASE_PYTHON."
}

& $Python (Join-Path $PSScriptRoot 'aivideo.py') @Arguments
exit $LASTEXITCODE
