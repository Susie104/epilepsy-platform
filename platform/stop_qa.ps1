# 停止千问模式：关掉本机 Flask 应用 + SSH 隧道。服务器端服务/看门狗不受影响。
$ErrorActionPreference = 'SilentlyContinue'
$deploymentRoot = Split-Path $PSScriptRoot -Parent
$statePath = Join-Path $deploymentRoot 'service.json'
$tunState  = Join-Path $deploymentRoot 'tunnel.json'
foreach ($path in $statePath, $tunState) {
    if (Test-Path -LiteralPath $path) {
        $o = Get-Content -Raw -Encoding UTF8 -LiteralPath $path | ConvertFrom-Json
        $kids = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($o.pid)"
        foreach ($k in $kids) { Stop-Process -Id $k.ProcessId -Force }
        Stop-Process -Id $o.pid -Force
        Write-Host ("stopped pid " + $o.pid)
    }
}
Write-Host '千问模式已停止（应用 + 本机隧道）。'
