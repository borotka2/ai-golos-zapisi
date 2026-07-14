@echo off
chcp 65001 >nul
echo Отключаю автозапуск 24/7...

schtasks /Delete /TN "AI-Golos-Server-Start" /F 2>nul
schtasks /Delete /TN "AI-Golos-Watchdog" /F 2>nul
schtasks /Delete /TN "AI-Golos-AutoTunnel" /F 2>nul

del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AI-Golos-24x7.lnk" 2>nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AI-Golos-Server.lnk" 2>nul

echo Готово. Автозапуск отключён.
pause