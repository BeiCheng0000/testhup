@echo off
chcp 65001 >nul
cd /d "%~dp0."
echo     Django后台服务启动 (ASGI/Daphne) —— 后台隐藏运行，无任务栏图标，日志: server.log

rem 用 PowerShell 以「隐藏窗口」方式启动：服务在后台常驻运行，桌面/任务栏不出现窗口与图标
powershell -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','venv\Scripts\daphne -b 0.0.0.0 -p 8000 backend.asgi:application > server.log 2>&1' -WorkingDirectory '%~dp0.' -WindowStyle Hidden"

exit /b
