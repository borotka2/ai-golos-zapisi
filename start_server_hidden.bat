@echo off
chcp 65001 >nul
cd /d "%~dp0"
title AI-Server - НЕ ЗАКРЫВАТЬ
echo.
echo  ИИ Анализ - сервер 24/7
echo  http://127.0.0.1:8002
echo  https://edik-ai-golos.surge.sh
echo.
echo  НЕ ЗАКРЫВАТЬ ЭТО ОКНО!
echo.
.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8002 --workers 1