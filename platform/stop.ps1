$ErrorActionPreference = 'Stop'
$statePath = Join-Path (Split-Path $PSScriptRoot -Parent) 'service.json'
if (-not (Test-Path -LiteralPath $statePath)) { Write-Host 'No recorded service.'; return }
$info = Get-Content -Raw -Encoding UTF8 -LiteralPath $statePath | ConvertFrom-Json
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($info.pid)" -ErrorAction SilentlyContinue
if ($process -and $process.ExecutablePath -eq $info.python -and $process.CommandLine -like '*serve_local.py*' -and $info.application -eq $PSScriptRoot) {
    Stop-Process -Id $info.pid
    Write-Host "Stopped PID $($info.pid)"
} elseif ($process) {
    throw 'Recorded PID belongs to a different process; refusing to stop it.'
} else { Write-Host 'Service is already stopped.' }
