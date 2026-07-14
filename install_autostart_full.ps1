# Полная установка автозапуска 24/7 (запустить один раз)
$projectDir = "C:\Users\user\Desktop\ai-golos-zapisi"
$startBat = Join-Path $projectDir "start_all.bat"
$watchdog = Join-Path $projectDir "watchdog.ps1"
$desktop = [Environment]::GetFolderPath("Desktop")
$wsh = New-Object -ComObject WScript.Shell

Write-Host "Устанавливаю автозапуск 24/7..."

# 1. Сервер при входе в Windows (через 30 сек после логина)
$actionStart = New-ScheduledTaskAction -Execute $startBat -Argument "silent"
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn
$triggerLogon.Delay = "PT30S"
$settingsStart = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "AI-Golos-Server-Start" -Action $actionStart -Trigger $triggerLogon `
    -Settings $settingsStart -Force -RunLevel Highest | Out-Null

# 2. Сторож: сервер + туннель + Surge — каждые 5 мин + при старте Windows
$actionWatch = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$watchdog`""
$triggerBoot = New-ScheduledTaskTrigger -AtStartup
$triggerBoot.Delay = "PT3M"
$triggerRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settingsWatch = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName "AI-Golos-Watchdog" -Action $actionWatch -Trigger @($triggerBoot, $triggerRepeat) `
    -Settings $settingsWatch -Force -RunLevel Highest | Out-Null

# 3. Убрать старую задачу (дублирует watchdog)
Unregister-ScheduledTask -TaskName "AI-Golos-AutoTunnel" -Confirm:$false -ErrorAction SilentlyContinue

# 4. Отключить спящий режим при питании от сети
powercfg /change standby-timeout-ac 0 2>$null
powercfg /change hibernate-timeout-ac 0 2>$null
powercfg /change monitor-timeout-ac 30 2>$null

# 5. Ярлыки на рабочем столе
$lnkStart = $wsh.CreateShortcut((Join-Path $desktop "ИИ Анализ - Запуск.lnk"))
$lnkStart.TargetPath = $startBat
$lnkStart.WorkingDirectory = $projectDir
$lnkStart.Description = "Запустить сервер ИИ Анализ"
$lnkStart.Save()

$lnkStop = $wsh.CreateShortcut((Join-Path $desktop "ИИ Анализ - Стоп.lnk"))
$lnkStop.TargetPath = (Join-Path $projectDir "stop_all.bat")
$lnkStop.WorkingDirectory = $projectDir
$lnkStop.Description = "Остановить сервер"
$lnkStop.Save()

$lnkStatus = $wsh.CreateShortcut((Join-Path $desktop "ИИ Анализ - Статус.lnk"))
$lnkStatus.TargetPath = "http://127.0.0.1:8002/login"
$lnkStatus.Description = "Открыть сайт локально"
$lnkStatus.Save()

# 6. Дублирующий автозапуск в папке Startup (на случай если задача не сработает)
$startupFolder = [Environment]::GetFolderPath("Startup")
$lnkAuto = $wsh.CreateShortcut((Join-Path $startupFolder "AI-Golos-24x7.lnk"))
$lnkAuto.TargetPath = $startBat
$lnkAuto.Arguments = "silent"
$lnkAuto.WorkingDirectory = $projectDir
$lnkAuto.WindowStyle = 7
$lnkAuto.Description = "Автозапуск ИИ Анализ 24/7"
$lnkAuto.Save()

Write-Host ""
Write-Host "=========================================="
Write-Host "  АВТОЗАПУСК 24/7 УСТАНОВЛЕН"
Write-Host "=========================================="
Write-Host ""
Write-Host "Что работает автоматически:"
Write-Host "  [1] Сервер стартует при входе в Windows"
Write-Host "  [2] Сторож проверяет каждые 5 минут"
Write-Host "  [3] Туннель + Surge обновляются сами"
Write-Host "  [4] Спящий режим отключён (от сети)"
Write-Host "  [5] Экран гаснет через 30 мин (сервер работает)"
Write-Host ""
Write-Host "Ссылки:"
Write-Host "  Локально:  http://127.0.0.1:8002"
Write-Host "  Wi-Fi:     http://192.168.0.171:8002"
Write-Host "  Интернет:  https://edik-ai-golos.surge.sh"
Write-Host ""
Write-Host "Ярлыки на рабочем столе:"
Write-Host "  - ИИ Анализ - Запуск"
Write-Host "  - ИИ Анализ - Стоп"
Write-Host "  - ИИ Анализ - Статус"
Write-Host ""
Write-Host "Лог сторожа: data\watchdog.log"
Write-Host "=========================================="