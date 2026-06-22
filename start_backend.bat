@echo off
echo     Django后台服务启动 (ASGI/Daphne)
start /MIN venv\Scripts\daphne -b 0.0.0.0 -p 8000 backend.asgi:application > server.log 2>&1
exit