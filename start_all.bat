@echo off
echo 启动TestHub生产环境...

echo 启动Django后端服务...
start "Django Backend" cmd /k start_backend.bat

echo 启动Celery服务...
start "Celery Worker" cmd /k start_celery.bat

echo 启动定时任务调度器...
start "Task Scheduler" cmd /k start_scheduler.bat

echo 正在启动 Nginx...
cd /d C:\nginx
start nginx
echo Nginx 已启动

echo 所有服务已启动!
echo 前端地址: http://localhost
echo 后端API: http://localhost/api/
pause
