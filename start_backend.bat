@echo off
echo     Django后台服务启动
start /MIN venv\Scripts\python manage.py runserver 0.0.0.0:8000 > server.log 2>&1
exit