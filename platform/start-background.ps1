param([int]$Port = 3000, [switch]$OpenBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$deploymentRoot = Split-Path $projectRoot -Parent
$pythonPath = Join-Path $deploymentRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run install.ps1 first.' }
$url = "http://127.0.0.1:$Port"
$statePath = Join-Path $deploymentRoot 'service.json'
if (Test-Path -LiteralPath $statePath) {
    $old = Get-Content -Raw -Encoding UTF8 -LiteralPath $statePath | ConvertFrom-Json
    $running = Get-CimInstance Win32_Process -Filter "ProcessId=$($old.pid)" -ErrorAction SilentlyContinue
    if ($running -and $running.ExecutablePath -eq $pythonPath -and $running.CommandLine -like '*serve_local.py*') {
        Write-Host "Already running: $($old.url)"
        if ($OpenBrowser) { Start-Process $old.url }
        return
    }
}
$logs = Join-Path $deploymentRoot 'evidence'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$env:PORT = "$Port"
$env:CHANNEL2 = '0'
$env:APP_VAR_DIR = Join-Path $projectRoot 'var'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$service = Start-Process -FilePath $pythonPath -ArgumentList 'serve_local.py' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'local-server.stdout.log') -RedirectStandardError (Join-Path $logs 'local-server.stderr.log') -PassThru
@{ pid=$service.Id; port=$Port; url=$url; python=$pythonPath; application=$projectRoot } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
for ($attempt=0; $attempt -lt 60; $attempt++) {
    if ($service.HasExited) { throw "Server exited. Check $logs" }
    try {
        $ready = Invoke-RestMethod "$url/readyz" -TimeoutSec 2
        if ($ready.model_integrity -and $ready.audit_chain.ok) {
            Write-Host "Ready: $url"
            if ($OpenBrowser) { Start-Process $url }
            return
        }
    } catch { }
    Start-Sleep -Milliseconds 300
}
throw "Startup timed out. Check $logs"
