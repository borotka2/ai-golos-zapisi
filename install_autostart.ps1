# Один раз: ставит автопроверку туннеля каждые 5 минут + при входе в Windows
$script = "C:\Users\user\Desktop\ai-golos-zapisi\keep_tunnel.ps1"
$taskName = "AI-Golos-AutoTunnel"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""

$triggerBoot = New-ScheduledTaskTrigger -AtStartup
$triggerBoot.Delay = "PT2M"

$start = Get-Date
$triggerRepeat = New-ScheduledTaskTrigger -Once -At $start `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($triggerBoot, $triggerRepeat) `
    -Settings $settings -Force -RunLevel Highest | Out-Null

Write-Host "OK: задача '$taskName' установлена (каждые 5 мин + при старте Windows)"
Write-Host "Ссылка для всех навсегда: https://edik-ai-golos.surge.sh"