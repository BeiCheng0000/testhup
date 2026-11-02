@echo off
chcp 65001 >nul
cd /d "%~dp0."
echo 启动TestHub生产环境（各服务均为后台隐藏运行，任务栏不出现图标）...

echo 启动Django后端服务...
call "%~dp0start_backend.bat"

echo 启动Celery服务...
call "%~dp0start_celery.bat"

echo 启动定时任务调度器...
call "%~dp0start_scheduler.bat"

echo 正在启动 Nginx...
if exist "C:\nginx\nginx.exe" (
    start "" /d "C:\nginx" nginx.exe
    echo Nginx 已启动
) else (
    echo 未找到 C:\nginx\nginx.exe，跳过 Nginx
)

echo 所有服务已启动!
echo 前端地址: http://localhost
echo 后端API: http://localhost/api/
timeout /t 5 >nul
