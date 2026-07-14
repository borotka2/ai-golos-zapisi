# Ставит автозапуск сервера при входе в Windows (без Cursor)
$projectDir = "C:\Users\user\Desktop\ai-golos-zapisi"
$startBat = Join-Path $projectDir "start_all.bat"
$startupFolder = [Environment]::GetFolderPath("Startup")
$desktop = [Environment]::GetFolderPath("Desktop")
$wsh = New-Object -ComObject WScript.Shell

function New-Shortcut {
    param([string]$Path, [string]$Name, [string]$Description)
    $lnk = $wsh.CreateShortcut((Join-Path $Path "$Name.lnk"))
    $lnk.TargetPath = $startBat
    $lnk.WorkingDirectory = $projectDir
    $lnk.WindowStyle = 1
    $lnk.Description = $Description
    $lnk.Save()
}

New-Shortcut -Path $startupFolder -Name "AI-Golos-Server" -Description "Автозапуск ИИ Анализ"
New-Shortcut -Path $desktop -Name "ИИ Анализ - Запуск" -Description "Запустить сервер"
New-Shortcut -Path $desktop -Name "ИИ Анализ - Стоп" -Description "Остановить сервер" 
$stopLnk = $wsh.CreateShortcut((Join-Path $desktop "ИИ Анализ - Стоп.lnk"))
$stopLnk.TargetPath = (Join-Path $projectDir "stop_all.bat")
$stopLnk.WorkingDirectory = $projectDir
$stopLnk.Save()

Write-Host "OK:"
Write-Host "  - Автозапуск при входе в Windows"
Write-Host "  - Ярлык на рабочем столе: ИИ Анализ - Запуск"
Write-Host "  - Ярлык на рабочем столе: ИИ Анализ - Стоп"
Write-Host ""
Write-Host "Локально:  http://127.0.0.1:8002"
Write-Host "Wi-Fi:     http://192.168.0.171:8002"
Write-Host "Интернет:  https://edik-ai-golos.surge.sh"