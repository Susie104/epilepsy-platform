$ErrorActionPreference = 'Stop'
$deploymentRoot = Split-Path $PSScriptRoot -Parent
$venvPath = Join-Path $deploymentRoot '.venv'
$pythonPath = Join-Path $venvPath 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create Python virtual environment.' }
}
& $pythonPath -m pip install --timeout 120 -r (Join-Path $PSScriptRoot 'requirements.lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $pythonPath -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }
