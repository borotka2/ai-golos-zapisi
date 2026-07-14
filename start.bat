@echo off
chcp 65001 >nul
title AI-Server - НЕ ЗАКРЫВАТЬ
cd /d "%~dp0"

if not exist ".venv\Scripts\uvicorn.exe" (
    echo Создаю окружение...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
)

echo.
echo  ==========================================
echo   ИИ Анализ разговоров — ОБЩИЙ СЕРВЕР
echo  ==========================================
echo.
echo   ДЛЯ ВСЕХ из интернета (ПОСТОЯННАЯ ссылка):
echo   https://edik-ai-golos.surge.sh
echo.
echo   Туннель обновляется автоматически — менять ничего не нужно.
echo   Админ: admin / admin123
echo.
echo   Локально на этом ПК:
echo   http://127.0.0.1:8002
echo.
echo   В вашей Wi-Fi сети:
echo   http://192.168.0.171:8002
echo.
echo   Менеджеры регистрируются сами.
echo   Вы (админ) одобряете в разделе Менеджеры.
echo.
echo   НЕ ЗАКРЫВАЙТЕ ЭТО ОКНО!
echo  ==========================================
echo.

start "" "http://127.0.0.1:8002/login"

.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8002 --workers 4

pause