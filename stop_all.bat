@echo off
echo 停止TestHub生产环境...

echo 停止Nginx...
taskkill /F /IM nginx.exe

echo 查找并停止Python进程...
taskkill /F /IM python.exe

echo 所有服务已停止!
pause
