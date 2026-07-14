# ИИ Анализ голосовых записей

Веб-панель: загрузка mp3/wav/txt → транскрипция (Groq) → анализ (DeepSeek) → отчёт с ошибками и рекомендациями.

## Репозиторий

https://github.com/borotka2/ai-golos-zapisi

## Локальный запуск (Windows)

1. Python 3.11+ и venv:
   ```bat
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
2. Скопируйте `.env.example` → `.env` и вставьте ключи `GROQ_API_KEY`, `DEEPSEEK_API_KEY` (или `OPENAI_API_KEY`).
3. Старт:
   ```bat
   start_server_hidden.bat
   ```
   или: `.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8002`
4. Открыть: http://127.0.0.1:8002  
   Админ по умолчанию: `admin` / `admin123`

## Онлайн

Сервер должен быть запущен на ПК + Cloudflare Tunnel (`cloudflared`).  
Актуальная публичная ссылка пишется в `data/tunnel_url.json` и на рабочий стол (`ССЫЛКИ-ПРОЕКТЫ.txt`).

## Render (опционально)

Есть `render.yaml` — можно подключить free Web Service на [render.com](https://render.com) и задать env-ключи.
