"""Запуск сервера, проверка входа admin, открытие Chrome."""
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import httpx

ROOT = Path(__file__).parent
PORT = 8002
BASE = f"http://127.0.0.1:{PORT}"
UVICORN = ROOT / ".venv" / "Scripts" / "uvicorn.exe"


def wait_server(client: httpx.Client, timeout: float = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = client.get(f"{BASE}/login")
            if r.status_code == 200:
                return True
        except httpx.RequestError:
            pass
        time.sleep(0.5)
    return False


def main():
    if not UVICORN.exists():
        print("ERROR: venv not found. Run start.bat first.")
        sys.exit(1)

    proc = subprocess.Popen(
        [str(UVICORN), "app.main:app", "--host", "0.0.0.0", "--port", str(PORT)],
        cwd=str(ROOT),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )

    with httpx.Client(follow_redirects=True, timeout=10) as client:
        print("Жду сервер...")
        if not wait_server(client):
            proc.kill()
            print("ERROR: сервер не запустился")
            sys.exit(1)

        print("OK: страница входа открывается")

        r = client.post(f"{BASE}/login", data={"username": "admin", "password": "admin123"})
        if "Панель администратора" not in r.text and "администратор" not in r.text.lower():
            proc.kill()
            print("ERROR: вход не удался")
            print(r.text[:300])
            sys.exit(1)

        print("OK: ВОШЁЛ как admin — Панель администратора")
        print(f"URL: {BASE}/dashboard")

    chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    url = f"{BASE}/static/autologin.html"
    if chrome.exists():
        subprocess.Popen([str(chrome), url])
    else:
        webbrowser.open(url)

    print("Chrome открыт. Сервер работает в отдельном окне.")
    print("НЕ ЗАКРЫВАЙТЕ окно AI-Server!")
    proc.wait()


if __name__ == "__main__":
    main()