@echo off
chcp 65001 >nul
cd /d "%~dp0"
set SILENT=%1

if not exist ".venv\Scripts\uvicorn.exe" (
    if /I not "%SILENT%"=="silent" (
        echo Создаю окружение...
        python -m venv .venv
        call .venv\Scripts\activate.bat
        pip install -r requirements.txt
    ) else (
        exit /b 1
    )
)

curl -s -o nul http://127.0.0.1:8002/login 2>nul
if %errorlevel%==0 goto :tunnel

if /I "%SILENT%"=="silent" (
    start /MIN "AI-Server - НЕ ЗАКРЫВАТЬ" /D "%~dp0" cmd /k "chcp 65001 >nul && title AI-Server - НЕ ЗАКРЫВАТЬ && cd /d %~dp0 && echo. && echo  ИИ Анализ — сервер 24/7 && echo  http://127.0.0.1:8002 && echo  https://edik-ai-golos.surge.sh && echo. && echo  НЕ ЗАКРЫВАТЬ! && echo. && .venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8002 --workers 4"
) else (
    echo Запускаю сервер...
    start "AI-Server - НЕ ЗАКРЫВАТЬ" /D "%~dp0" cmd /k "chcp 65001 >nul && title AI-Server - НЕ ЗАКРЫВАТЬ && cd /d %~dp0 && echo. && echo  ИИ Анализ — сервер 24/7 && echo  Локально: http://127.0.0.1:8002 && echo  Wi-Fi:    http://192.168.0.171:8002 && echo  Интернет: https://edik-ai-golos.surge.sh && echo. && echo  НЕ ЗАКРЫВАЙТЕ ЭТО ОКНО! && echo. && .venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8002 --workers 4"
)

:wait_server
timeout /t 3 /nobreak >nul
curl -s -o nul http://127.0.0.1:8002/login 2>nul
if %errorlevel% neq 0 goto :wait_server

:tunnel
where cloudflared >nul 2>&1
if %errorlevel% neq 0 goto :finish

wmic process where "name='cloudflared.exe' and commandline like '%%localhost:8002%%'" get processid 2>nul | findstr /R "[0-9]" >nul
if %errorlevel% neq 0 (
    if /I not "%SILENT%"=="silent" echo Запускаю туннель...
    start /MIN "" cloudflared tunnel --url http://localhost:8002
    timeout /t 8 /nobreak >nul
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0watchdog.ps1" >nul 2>&1

:finish
if /I "%SILENT%"=="silent" exit /b 0

echo.
echo  ==========================================
echo   Сервер запущен — работает 24/7
echo  ==========================================
echo.
echo   Локально:  http://127.0.0.1:8002
echo   Wi-Fi:      http://192.168.0.171:8002
echo   Интернет:   https://edik-ai-golos.surge.sh
echo.
echo   Автозапуск: включён (при входе в Windows)
echo   Сторож:     проверка каждые 5 минут
echo   Остановить: stop_all.bat
echo  ==========================================
echo.
start "" "http://127.0.0.1:8002/login"
pause