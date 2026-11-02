@echo off
chcp 65001 >nul
cd /d "%~dp0."
echo 启动 Celery Worker (线程池模式) —— 后台隐藏运行，无任务栏图标，日志: celery.log
set DJANGO_SETTINGS_MODULE=backend.settings

rem 用 PowerShell 以「隐藏窗口」方式启动：worker 在后台常驻运行，桌面/任务栏不出现窗口与图标
powershell -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','venv\Scripts\celery -A backend worker -l info --pool=threads --concurrency=4 --logfile=celery.log' -WorkingDirectory '%~dp0.' -WindowStyle Hidden"

exit /b
