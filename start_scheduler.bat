@echo off
echo 启动定时任务调度器...
start /MIN venv\Scripts\python manage.py run_all_scheduled_tasks > scheduler.log 2>&1
exit