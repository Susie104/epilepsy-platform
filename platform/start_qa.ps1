# 连服务器 / 千问模式一键启动：SSH 隧道 + 带 LLM 环境的应用 + 打开问答页。
# 依赖：已连校园网 henu-student；服务器端 vLLM 服务在跑（看门狗会自动维持）。
param([int]$Port = 3000, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot  = $PSScriptRoot
$deploymentRoot = Split-Path $projectRoot -Parent
$pythonPath   = Join-Path $deploymentRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run install.ps1 first.' }
$url        = "http://127.0.0.1:$Port"
$statePath  = Join-Path $deploymentRoot 'service.json'
$tunState   = Join-Path $deploymentRoot 'tunnel.json'
$TOKENFILE  = Join-Path $deploymentRoot 'llm_token'

$KEY  = Join-Path $env:USERPROFILE '.ssh\epilepsy_deploy_20261107'
$SRV  = 'zxyaicenter2@10.12.246.11'
$RDIR = '/home/zxyaicenter2/epilepsy_llm_20261107'

function Stop-Tracked($path) {
    if (Test-Path -LiteralPath $path) {
        try {
            $o = Get-Content -Raw -Encoding UTF8 -LiteralPath $path | ConvertFrom-Json
            $kids = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($o.pid)" -ErrorAction SilentlyContinue
            foreach ($k in $kids) { Stop-Process -Id $k.ProcessId -Force -ErrorAction SilentlyContinue }
            Stop-Process -Id $o.pid -Force -ErrorAction SilentlyContinue
        } catch { }
    }
}
# 干净重启：先停掉上次的 app / tunnel
Stop-Tracked $statePath
Stop-Tracked $tunState

# 1) 服务器可达？不通就直接停（这是“连服务器”模式，不半启动）
try { ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15 $SRV 'hostname' | Out-Null }
catch {
    Write-Host '连不上服务器 10.12.246.11。请先：(1) 连校园网 henu-student；(2) 若密钥已过 2026-11-08 13:40，先运行 authorize_server.ps1 重新授权。' -ForegroundColor Red
    Write-Host '只想普通用平台（不连服务器/无 AI 回答）的话，改用 start.cmd。' -ForegroundColor Yellow
    exit 1
}

# 2) 取 api-key（稳定，可复用）
scp -i $KEY -o IdentitiesOnly=yes -q ($SRV + ':' + $RDIR + '/runtime/api-key') $TOKENFILE
$tok = (Get-Content -LiteralPath $TOKENFILE -Raw).Trim()

# 3) 起 SSH 隧道 127.0.0.1:8001 -> 服务器:8001（脱离会话）
$tp = Start-Process ssh -ArgumentList @('-i',$KEY,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=30','-N','-L','127.0.0.1:8001:127.0.0.1:8001',$SRV) -WindowStyle Hidden -PassThru
@{ pid = $tp.Id } | ConvertTo-Json | Set-Content -LiteralPath $tunState -Encoding UTF8
Start-Sleep 4

# 4) LLM 环境变量（下面应用进程继承）
$env:EPILEPSY_LLM_BASE_URL = 'http://127.0.0.1:8001'
$env:EPILEPSY_LLM_MODEL    = 'epilepsy-qwen3-8b'
$env:EPILEPSY_LLM_TOKEN    = $tok
$env:EPILEPSY_LLM_DISABLE_THINKING = 'true'

# 5) 起 Flask 应用（与 start-background.ps1 同一套 service.json 约定）
$logs = Join-Path $deploymentRoot 'evidence'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$env:PORT = "$Port"; $env:CHANNEL2 = '0'; $env:APP_VAR_DIR = Join-Path $projectRoot 'var'
$env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'
$service = Start-Process -FilePath $pythonPath -ArgumentList 'serve_local.py' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'local-server.stdout.log') -RedirectStandardError (Join-Path $logs 'local-server.stderr.log') -PassThru
@{ pid=$service.Id; port=$Port; url=$url; python=$pythonPath; application=$projectRoot } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
for ($attempt=0; $attempt -lt 60; $attempt++) {
    if ($service.HasExited) { throw "Server exited. Check $logs" }
    try {
        $ready = Invoke-RestMethod "$url/readyz" -TimeoutSec 2
        if ($ready.model_integrity -and $ready.audit_chain.ok) {
            Write-Host "千问模式就绪: $url/knowledge-qa/" -ForegroundColor Green
            if (-not $NoBrowser) { Start-Process "$url/knowledge-qa/" }
            return
        }
    } catch { }
    Start-Sleep -Milliseconds 300
}
throw "Startup timed out. Check $logs"
