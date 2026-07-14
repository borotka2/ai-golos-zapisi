Set sh = CreateObject("WScript.Shell")
dir = "C:\Users\Edik\Desktop\ai-golos-zapisi"
cmd = "cmd /k cd /d """ & dir & """ && .venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8002"
sh.Run cmd, 1, False
WScript.Sleep 8000
sh.Run "http://127.0.0.1:8002/login", 1, False