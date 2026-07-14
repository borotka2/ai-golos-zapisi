@echo off
chcp 65001 >nul
echo Останавливаю сервер и туннель...

for /f "tokens=2" %%a in ('wmic process where "name='cloudflared.exe' and commandline like '%%localhost:8002%%'" get processid 2^>nul ^| findstr /R "[0-9]"') do taskkill /F /PID %%a 2>nul

taskkill /F /IM uvicorn.exe 2>nul

echo.
echo Готово. Сервер остановлен.
echo Примечание: при следующем входе в Windows запустится снова автоматически.
echo Чтобы отключить автозапуск: uninstall_autostart.bat
echo.
pause