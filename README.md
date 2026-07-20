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

## MicroSIP → кабинет менеджера (без ручной загрузки)

Нужно менеджерам, которые звонят через **MicroSIP**: записи сами попадают на сайт по **дате и времени**, анализ ИИ — **кнопкой вручную**.

### На ПК менеджера

1. Скачать MicroSIP: https://www.microsip.org/downloads  
2. **Settings → Recording** — включить запись звонков, папка например `C:\MicroSIP\Recordings`
3. Зайти в свой кабинет на сайте → блок **«MicroSIP → автоматически»** → скопировать **URL** и **токен**
4. На том же ПК:
   ```bat
   start_microsip_sync.bat
   ```
   В `tools\microsip_config.json` вписать:
   - `server_url` — адрес сайта
   - `ingest_token` — токен из кабинета
   - `watch_folder` — папка Recording
5. После звонка файл появляется в «История разговоров» → **Анализ ИИ**

| Поле на сайте | Откуда |
|---------------|--------|
| Дата и время | Имя файла MicroSIP или время сохранения |
| Телефон | Из имени файла (если есть) |
| Источник | 📞 MicroSIP |
| Анализ | Кнопка вручную (по умолчанию не авто) |

### API (для watcher)

- `GET /api/microsip/setup` — токен (нужна сессия менеджера)
- `POST /api/microsip/ingest` — заголовок `X-Ingest-Token`, form-file `file`, опционально `auto_analyze=true`
- `POST /recording/{id}/analyze` — ручной запуск ИИ

**MicroSIP на сервер анализа ставить не обязательно** — только на ПК, где менеджер звонит.

## Онлайн

Сервер должен быть запущен на ПК + Cloudflare Tunnel (`cloudflared`).  
Актуальная публичная ссылка пишется в `data/tunnel_url.json` и на рабочий стол (`ССЫЛКИ-ПРОЕКТЫ.txt`).

## Render (опционально)

Есть `render.yaml` — можно подключить free Web Service на [render.com](https://render.com) и задать env-ключи.
