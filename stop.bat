@echo off
taskkill /F /IM uvicorn.exe 2>nul
echo Server stopped.
pause