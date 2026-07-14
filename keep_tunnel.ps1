# Автоматически следит за туннелем и обновляет Surge (ссылка edik-ai-golos.surge.sh не меняется)
$projectDir = "C:\Users\user\Desktop\ai-golos-zapisi"
$logDir = "C:\Users\user\.grok"
$tunnelLog = Join-Path $logDir "tunnel8002_err.log"
$localState = Join-Path $projectDir "data\tunnel_url.json"
$surgeState = Join-Path $projectDir "surge-dist\tunnel-url.json"
$checkUrl = "http://localhost:8002/login"
$node = "C:\Program Files\nodejs\node.exe"
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"

function Get-TunnelUrlFromLog {
    param([string]$LogPath)
    if (Test-Path $LogPath) {
        $m = Select-String -Path $LogPath -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -Last 1
        if ($m) { return $m.Matches[0].Value }
    }
    return $null
}

function Get-SavedTunnelUrl {
    foreach ($path in @($localState, $surgeState)) {
        if (Test-Path $path) {
            try {
                $data = Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($data.url) { return [string]$data.url }
            } catch {}
        }
    }
    return $null
}

function Save-TunnelUrl {
    param([string]$Url)
    $payload = @{
        url = $Url.TrimEnd("/")
        updated = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    } | ConvertTo-Json -Compress
    Set-Content $localState -Value $payload -Encoding UTF8 -NoNewline
    Set-Content $surgeState -Value $payload -Encoding UTF8 -NoNewline
}

function Test-LocalServer {
    try {
        $r = Invoke-WebRequest -Uri $checkUrl -UseBasicParsing -TimeoutSec 8
        return $r.StatusCode -eq 200
    } catch { return $false }
}

function Test-TunnelUrl {
    param([string]$Url)
    try {
        $r = Invoke-WebRequest -Uri "$($Url.TrimEnd('/'))/login" -UseBasicParsing -TimeoutSec 15
        return $r.StatusCode -eq 200
    } catch { return $false }
}

function Deploy-Surge {
    if (-not (Test-Path $node)) { return $false }
    Push-Location $projectDir
    & $node ".\node_modules\surge\bin\surge" surge-dist --domain edik-ai-golos.surge.sh | Out-Null
    Pop-Location
    return $true
}

function Restart-Tunnel {
    Get-Process cloudflared -ErrorAction SilentlyContinue | Where-Object {
        (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -match "localhost:8002"
    } | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Remove-Item $tunnelLog -ErrorAction SilentlyContinue
    $exe = if (Test-Path $cf) { $cf } else { "cloudflared" }
    Start-Process -FilePath $exe -ArgumentList "tunnel","--url","http://localhost:8002" -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir "tunnel8002.log") `
        -RedirectStandardError $tunnelLog
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 2
        $url = Get-TunnelUrlFromLog -LogPath $tunnelLog
        if ($url -and (Test-TunnelUrl -Url $url)) { return $url }
    }
    return $null
}

if (-not (Test-LocalServer)) {
    Write-Host "[keep_tunnel] local server down on 8002"
    exit 1
}

$url = Get-SavedTunnelUrl
if (-not $url) { $url = Get-TunnelUrlFromLog -LogPath $tunnelLog }

if ($url -and (Test-TunnelUrl -Url $url)) {
    Write-Host "[keep_tunnel] OK $url"
    exit 0
}

Write-Host "[keep_tunnel] tunnel dead, restarting..."
$newUrl = Restart-Tunnel
if (-not $newUrl) {
    Write-Host "[keep_tunnel] failed to get new tunnel url"
    exit 2
}

Save-TunnelUrl -Url $newUrl
Deploy-Surge | Out-Null
Write-Host "[keep_tunnel] restarted and updated surge -> $newUrl"
exit 0