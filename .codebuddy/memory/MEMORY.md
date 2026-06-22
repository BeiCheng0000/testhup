# TestHub Platform - 项目记忆

## 项目位置
- 根目录: `e:/wk/wk_python/testhub_platform-main/`
- 后端: Django REST Framework + Daphne (ASGI)
- 前端: Vue.js + Element Plus, 目录 `frontend/`

## 启动脚本
- 后端: `start_backend.bat` (Daphne ASGI 服务器, 端口 8000)
- Celery: `start_celery.bat`
- 定时任务: `start_scheduler.bat`

## Python 版本
- 运行 Python 3.13
- **重要**: Python 3.13 不兼容 `asyncio.create_task(Future)`, 只接受 coroutine

## 关键技术点
- WebSocket 通过 Daphne + Django Channels 实现
- Agent 设备代理: 远程主机通过 WebSocket 连接, 代理本地 ADB 设备
- Agent 通信: `threading.Event` (非 asyncio.Future) 实现跨事件循环安全
- Channel Layer: `InMemoryChannelLayer` (Windows 不支持 Redis BZPOPMIN)
