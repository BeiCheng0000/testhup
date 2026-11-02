@echo off
chcp 65001 >nul
cd /d "%~dp0."
echo 启动定时任务调度器 —— 后台隐藏运行，无任务栏图标，日志: scheduler.log

rem 用 PowerShell 以「隐藏窗口」方式启动：调度器在后台常驻运行，桌面/任务栏不出现窗口与图标
powershell -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','venv\Scripts\python manage.py run_all_scheduled_tasks > scheduler.log 2>&1' -WorkingDirectory '%~dp0.' -WindowStyle Hidden"

exit /b
