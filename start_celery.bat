@echo off
venv\Scripts\celery -A backend worker -l info --detach --logfile=celery.log --pidfile=celery.pid
exit