param(
    [switch]$WithRembg,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$SkillRoot = Split-Path -Parent $PSScriptRoot
$VenvRoot = Join-Path $SkillRoot 'runtime\.venv'
$Python = Join-Path $VenvRoot 'Scripts\python.exe'
$BasePython = if ($env:AIVIDEO_BASE_PYTHON) {
    $env:AIVIDEO_BASE_PYTHON
} elseif (Test-Path -LiteralPath 'F:\workspace\runtime\python\base\python.exe') {
    'F:\workspace\runtime\python\base\python.exe'
} else {
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1).Source
}
$env:PIP_CACHE_DIR = 'F:\workspace\runtime\cache\pip'

if (-not $BasePython -or -not (Test-Path -LiteralPath $BasePython)) {
    throw "Base Python not found. Set AIVIDEO_BASE_PYTHON to python.exe."
}

if ($Force -and (Test-Path -LiteralPath $VenvRoot)) {
    throw "Refusing to delete an existing runtime automatically. Remove it manually after review: $VenvRoot"
}

if (-not (Test-Path -LiteralPath $Python)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $VenvRoot) | Out-Null
    & $BasePython -m venv $VenvRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create Python virtual environment."
    }
}

& $Python -m pip install --disable-pip-version-check --no-input --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) {
    throw "Failed to update Python packaging tools."
}

$CorePackages = @(
    'numpy>=2.1,<3',
    'opencv-python-headless>=4.10',
    'onnx>=1.17',
    'imageio-ffmpeg>=0.5'
)
& $Python -m pip install --disable-pip-version-check --no-input @CorePackages
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install core video-edit packages."
}

& $Python -m pip install --disable-pip-version-check --no-input 'onnxruntime-directml>=1.20'
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'DirectML runtime failed; trying standard CPU onnxruntime.'
    & $Python -m pip install --disable-pip-version-check --no-input 'onnxruntime>=1.20'
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install onnxruntime."
    }
}

if ($WithRembg) {
    & $Python -m pip install --disable-pip-version-check --no-input 'rembg[cpu]>=2.0'
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install optional rembg backend."
    }
}

& $Python (Join-Path $PSScriptRoot 'aivideo.py') doctor --json
if ($LASTEXITCODE -ne 0) {
    throw "Runtime setup finished, but doctor reported a problem."
}

Write-Output "Runtime ready: $Python"
