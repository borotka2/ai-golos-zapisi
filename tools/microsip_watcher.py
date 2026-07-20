#!/usr/bin/env python3
"""
Синхронизация папки записей MicroSIP → сайт «ИИ Анализ разговоров».

На ПК менеджера:
  1. MicroSIP пишет .wav/.mp3 в папку (Settings → Recording)
  2. Этот скрипт следит за папкой и заливает новые файлы на сервер
  3. В кабинете менеджера запись появляется с датой/временем
  4. Анализ ИИ — вручную кнопкой на сайте

Конфиг: tools/microsip_config.json (создаётся при первом запуске)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "microsip_config.json"
STATE_PATH = ROOT / "microsip_state.json"
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma"}

DEFAULT_CONFIG = {
    "server_url": "http://127.0.0.1:8002",
    "ingest_token": "ВСТАВЬТЕ_ТОКЕН_ИЗ_КАБИНЕТА",
    "watch_folder": r"C:\MicroSIP\Recordings",
    "poll_seconds": 15,
    "auto_analyze": False,
    "stable_seconds": 3,
}


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_config() -> dict:
    if not CONFIG_PATH.exists():
        save_json(CONFIG_PATH, DEFAULT_CONFIG)
        print(f"[setup] Создан {CONFIG_PATH}")
        print("  1) Откройте кабинет менеджера на сайте → блок MicroSIP")
        print("  2) Скопируйте server_url и токен в microsip_config.json")
        print("  3) Укажите watch_folder = папка Recording в MicroSIP")
        print("  4) Запустите скрипт снова")
        sys.exit(0)
    cfg = load_json(CONFIG_PATH, DEFAULT_CONFIG)
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def file_is_stable(path: Path, stable_seconds: float) -> bool:
    """Файл дописан (MicroSIP закончил запись) — размер не меняется."""
    try:
        s1 = path.stat().st_size
        time.sleep(stable_seconds)
        s2 = path.stat().st_size
        return s1 > 0 and s1 == s2
    except OSError:
        return False


def upload_file(cfg: dict, path: Path) -> dict:
    server = cfg["server_url"].rstrip("/")
    url = f"{server}/api/microsip/ingest"
    token = (cfg.get("ingest_token") or "").strip()
    if not token or token.startswith("ВСТАВЬТЕ"):
        raise RuntimeError("В microsip_config.json укажите ingest_token из кабинета")

    boundary = f"----ms{int(time.time()*1000)}"
    body = bytearray()

    def add_field(name: str, value: str) -> None:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")

    add_field("auto_analyze", "true" if cfg.get("auto_analyze") else "false")
    mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    add_field("recorded_at", mtime)

    data = path.read_bytes()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode("utf-8")
    )
    body.extend(b"Content-Type: application/octet-stream\r\n\r\n")
    body.extend(data)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        url,
        data=bytes(body),
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Ingest-Token": token,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {"ok": True}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {err[:400]}") from e


def main() -> int:
    cfg = ensure_config()
    folder = Path(cfg["watch_folder"])
    poll = max(5, int(cfg.get("poll_seconds") or 15))
    stable = float(cfg.get("stable_seconds") or 3)

    if not folder.exists():
        print(f"[error] Папка не найдена: {folder}")
        print("  Создайте её или укажите правильный путь Recording из MicroSIP")
        return 1

    state = load_json(STATE_PATH, {"done": {}})
    done: dict = state.get("done") or {}

    print(f"[watch] {folder}")
    print(f"[server] {cfg['server_url']}")
    print(f"[poll] каждые {poll} сек · auto_analyze={cfg.get('auto_analyze')}")
    print("Ctrl+C — стоп\n")

    while True:
        try:
            files = sorted(
                [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTS],
                key=lambda p: p.stat().st_mtime,
            )
            for path in files:
                key = f"{path.resolve()}|{path.stat().st_size}"
                if key in done or str(path.resolve()) in done:
                    # уже заливали этот путь с таким размером
                    prev = done.get(str(path.resolve()))
                    if prev and prev.get("size") == path.stat().st_size:
                        continue
                    if key in done:
                        continue

                if not file_is_stable(path, stable):
                    continue

                print(f"[upload] {path.name} ({path.stat().st_size // 1024} KB)…", end=" ", flush=True)
                try:
                    result = upload_file(cfg, path)
                    done[str(path.resolve())] = {
                        "size": path.stat().st_size,
                        "at": datetime.now().isoformat(timespec="seconds"),
                        "recording_id": result.get("recording_id"),
                        "duplicate": result.get("duplicate"),
                    }
                    save_json(STATE_PATH, {"done": done})
                    if result.get("duplicate"):
                        print(f"уже есть id={result.get('recording_id')}")
                    else:
                        print(
                            f"OK id={result.get('recording_id')} "
                            f"{result.get('recorded_at') or ''} — {result.get('message', '')}"
                        )
                except Exception as exc:
                    print(f"FAIL: {exc}")

            time.sleep(poll)
        except KeyboardInterrupt:
            print("\n[stop] остановлено")
            return 0
        except Exception as exc:
            print(f"[loop] {exc}")
            time.sleep(poll)


if __name__ == "__main__":
    raise SystemExit(main())
