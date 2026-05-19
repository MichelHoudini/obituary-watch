@echo off
start "uvicorn" cmd /k "cd /d %USERPROFILE%\obituary-watch && venv\Scripts\activate && uvicorn app.main:app --reload"
timeout /t 3
start "watcher" cmd /k "cd /d %USERPROFILE%\obituary-watch && venv\Scripts\activate && python -m app.watcher"
timeout /t 3
start "ngrok" cmd /k "ngrok http --domain=saturday-rockslide-showroom.ngrok-free.dev 8000"
echo Tudo iniciado! Acesse: https://saturday-rockslide-showroom.ngrok-free.dev
pause
