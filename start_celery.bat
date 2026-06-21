@echo off
echo 启动 Celery Worker (线程池模式)...
set DJANGO_SETTINGS_MODULE=backend.settings
start /MIN "" venv\Scripts\celery -A backend worker -l info --pool=threads --concurrency=4 --logfile=celery.log
exit