# Сторож: следит за сервером и туннелем 24/7, перезапускает если упали
$projectDir = "C:\Users\user\Desktop\ai-golos-zapisi"
$logFile = Join-Path $projectDir "data\watchdog.log"
$checkUrl = "http://127.0.0.1:8002/login"
$uvicorn = Join-Path $projectDir ".venv\Scripts\uvicorn.exe"
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"

function Write-Log {
    param([string]$Msg)
    $dir = Split-Path $logFile -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Msg"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

function Test-Server {
    try {
        $r = Invoke-WebRequest -Uri $checkUrl -UseBasicParsing -TimeoutSec 8
        return $r.StatusCode -eq 200
    } catch { return $false }
}

function Start-Server {
    $bat = Join-Path $projectDir "start_server_hidden.bat"
    if (-not (Test-Path $bat)) {
        Write-Log "ERROR: start_server_hidden.bat not found"
        return $false
    }
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "`"$bat`"" -WorkingDirectory $projectDir -WindowStyle Minimized
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 3
        if (Test-Server) {
            Write-Log "OK: server started"
            return $true
        }
    }
    Write-Log "ERROR: server failed to start"
    return $false
}

function Test-TunnelProcess {
    $procs = Get-Process cloudflared -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        $cl = (Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)").CommandLine
        if ($cl -match "localhost:8002") { return $true }
    }
    return $false
}

function Start-TunnelProcess {
    $exe = if (Test-Path $cf) { $cf } else { "cloudflared" }
    $logDir = "C:\Users\user\.grok"
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Start-Process -FilePath $exe -ArgumentList "tunnel","--url","http://localhost:8002" -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir "tunnel8002.log") `
        -RedirectStandardError (Join-Path $logDir "tunnel8002_err.log")
    Write-Log "OK: tunnel process started"
}

if (-not (Test-Server)) {
    Write-Log "WARN: server down, restarting..."
    Start-Server | Out-Null
}

if (Test-Server) {
    if (-not (Test-TunnelProcess)) {
        Write-Log "WARN: tunnel process missing, starting..."
        Start-TunnelProcess
        Start-Sleep -Seconds 8
    }
    $kt = & (Join-Path $projectDir "keep_tunnel.ps1") 2>&1
    foreach ($line in $kt) { Write-Log $line }
    Write-Log "OK: watchdog check complete"
} else {
    Write-Log "ERROR: server still down"
    exit 1
}
exit 0