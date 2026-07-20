@echo off
chcp 65001 >nul
cd /d "%~dp0"
title MicroSIP → ИИ Анализ (синхронизация)

echo.
echo  === MicroSIP → сайт анализа ===
echo  Папка записей заливается в кабинет менеджера.
echo  Анализ ИИ — кнопка на сайте, вручную.
echo.

if not exist "tools\microsip_config.json" (
  echo  Первый запуск: создаём config...
  python tools\microsip_watcher.py
  echo.
  echo  Откройте tools\microsip_config.json
  echo  - server_url  = адрес сайта (как в кабинете)
  echo  - ingest_token = токен из кабинета менеджера
  echo  - watch_folder = папка Recording MicroSIP
  echo.
  notepad tools\microsip_config.json
  pause
)

python tools\microsip_watcher.py
if errorlevel 1 pause
