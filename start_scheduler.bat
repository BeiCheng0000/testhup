@echo off
echo 启动定时任务调度器...
call venv\Scripts\activate
python manage.py run_all_scheduled_tasks
pause
