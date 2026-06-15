@echo off
echo ����Django��˷���...
call venv\Scripts\activate
python manage.py runserver 0.0.0.0:8000
pause