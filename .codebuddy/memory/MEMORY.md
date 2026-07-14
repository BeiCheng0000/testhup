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

## CE 文件部署发布方式
- GitHub Actions 或手动部署：前后端构建/测试在同一 workflow 中执行，发布（deploy）为独立步骤（手动触发），使用 scp 将构建产物和代码上传到服务器
- 前端 dev 构建产物 (`frontend/dist/`) 不上传，仅在包构建时生产构建产物上传
- 部署后重启 gunicorn/nginx：服务器根目录 `deploy_restart.sh`，一次性执行停止、覆盖文件、启动
- deploy_staticfiles.bat: 构建前端项目 -> requiremnts 依赖安装 -> collectstatic 执行（迁移带--merge= （注意部署前备份 db）

## 关键技术点
- WebSocket 通过 Daphne + Django Channels 实现
- Agent 设备代理: 远程主机通过 WebSocket 连接, 代理本地 ADB 设备
- Agent 通信: `threading.Event` (非 asyncio.Future) 实现跨事件循环安全
- Channel Layer: `InMemoryChannelLayer` (Windows 不支持 Redis BZPOPMIN)

## 静态文件部署规范
- daphne 不自带静态文件服务，需要 `collectstatic` 生成到 `static_files/`
- `static_files/` 整个目录已在 `.gitignore` 中忽略，不入版本库
- 新环境部署时执行：`python manage.py collectstatic --noinput`

## Nginx 配置注意事项（2026-07-13 更新）
- 本项目 nginx 配置中存在 `location /` 块内嵌 `location ~* \.(js|css|ico|png|...)$` 用于前端静态资源缓存。正则 location 的匹配优先级高于普通前缀 location，会导致 `/media/.../app.js`、`/static/.../admin.css` 等请求被错误路由到 `frontend/dist/` 而 404。
- **规则**：所有需要代理/alias 到后端的特殊路径（`/media/`、`/static/`、`/admin/`、`/app-automation-reports/`、`/app-automation-templates/`、`/api-testing-reports/`）必须使用 `^~` 修饰符，例如 `location ^~ /media/ { ... }`，强制优先于正则 location。
- 已修复位置：`e:\it_install\nginx-1.31.1\conf\testhub.conf`、`frontend\nginx.conf`。
- 另外，nginx 默认监听端口在 Windows 本地环境中改为 8090，避免与 Java 进程占用的 8080 冲突。
`
