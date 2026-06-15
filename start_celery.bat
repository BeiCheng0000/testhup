@echo off
echo Æô¶¯Celery·þÎñ...
call venv\Scripts\activate
celery -A backend worker -l info
pause
