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

## API 测试平台数据模型要点（apps/api_testing）
- **导入/写库方式**：用 Django（不是 CLI），脚本头部 `os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.settings'); django.setup()`，DB 走 `.env`（MySQL）。
- **项目**：`ApiProject`；`内容中台` 项目 id=5（type=HTTP, owner=周锟 id=2）。创建者/owner 用现有 user（superuser=zhoukun id=1，或项目 owner）。
- **集合**：`ApiCollection(project, name, parent)`；`parent=None` 为顶层，可嵌套子集合。`ApiCollection` 有 `children` 反向关系。
- **请求**：`ApiRequest(collection FK related_name='requests', name, method 默认 GET, url TextField, headers JSONField **默认 dict**, params dict, body dict, auth dict, assertions JSONField, created_by FK 必填)`。
- **断言格式**：状态码 `{"name":"状态码断言","type":"status_code","expected":200}`；JSON 路径 `{"name":"code断言","type":"json_path","json_path":"$.code","expected":0}`（utils.execute_assertions 中 json_path 用 `str(actual)==str(expected)` 比较）。
- **请求头格式**：dict，如 `{"authorization":"{{token}}","cookie":"{{cookie}}"}`（平台用 `{{var}}` 占位符从环境变量解析）。
- **去重经验**：跨集合相同 URL 应保留（同一接口可属于多个集合）；去重应按 `(collection, url)` 在集合内去重，而非全局去重，否则会丢失跨集合归属。集合中可放空（仅作为分组文件夹）。
- **批量导入 Excel 经验（内容中心接口响应统计.xlsx）**：
  - 结构：表格列0=知识体系(仅作标签/名称来源)，有 URL 行为接口；**无 URL 行（4个：属性与标签/映射关系/内容资产库/开放服务）才是真正的集合**，"出现一次刷新一次"=遇到无URL行就切换当前集合，其后接口归入该集合。最前面0-49行（教材/知识树类）无对应无URL行，单独归到「教材与知识树」顶层集合；最后241-246行在开放服务段下，归开放服务。
  - **去重必须全局按原始URL字符串去重**（=171个），不能按"集合内去重、跨集合保留"（那样会变211个，错误）。跨集合重复URL只保留首次出现的那个集合里一份。
  - **命名=集合名+序号**（用户确认）：如 `属性与标签1`、`内容资产库1`。注意用户原始说"路径列+序号"但最后确认用"集合名+序号"，二者易混，以最终确认为准。
  - **最终采用的两级结构（用户第三次确认）**：无URL行=顶层集合(一层)；其下URL行的第一列(col0/知识体系)名称=子集合(二层，col0为空时沿用上一个非空col0作为当前子集合)；接口命名=`子集合名+序号`(如 `通用属性1`)。全局去重171。最前0-49行(无对应无URL行)归入第5个顶层「教材与知识树」，其col0值作其子集合。
  - 域名 `https://portal.xuexizhiwang.com`（含 `//` 双斜杠变体）统一去除，仅留路径；基础断言 status_code 200 + json_path $.code==0；请求头 `{"authorization":"{{token}}","cookie":"{{cookie}}"}`。
  - 重导方式：先 `ApiRequest.objects.filter(collection__project=proj).delete()` + `ApiCollection.objects.filter(project=proj).delete()` 清空再写，保证幂等干净。
  - **前端分页坑（重要）**：DRF 全局 `PAGE_SIZE=20`（backend/settings.py `REST_FRAMEWORK`）。`ApiCollectionViewSet`、请求列表都分页，而前端 `InterfaceManagement.vue`/`AutomationTesting.vue` 原来只取 `response.data.results`（第一页 20 条）。集合/请求 >20 时会被截断，导致前端只显示部分顶层集合（如只看到 2 个）和少量请求（如只看到 16 个）——**不是数据缺失**。已修复：两文件均加 `fetchAllPages()` 循环翻页拉全量。
  - **改前端必须重新构建**：生产环境 `start_all.bat` 用 `C:\nginx` 提供的是**已构建的** `frontend/dist`（`npm run build` 产物），不是 vite dev。仅改 `.vue` 源码不会自动生效，**必须 `cd frontend && npm run build`**，然后浏览器**硬刷新（Ctrl+Shift+R）** 绕过缓存。仅靠"刷新"若还在看旧哈希的 JS 则无效。
  - **为什么偏偏是某批集合显示空（根因）**：请求列表按 id 默认排序，旧前端只取第一页 20 条。导入时 **教材与知识树的请求 id 最小（最先写入）落在第一页，属性与标签/内容资产库的请求 id 靠后落在第 2~4 页**——所以旧版恰好显示教材与知识树、却丢属性与标签（用户两次分别报"6个子集合没接口"和"属性与标签9个都没接口"，正是旧构建只取首20条所致）。新构建 `fetchAllPages` 翻全量后全部正常。验证方法：DB 按 `collection_id` 排序看请求分布，或前端 hard refresh 后核对。无 Service Worker 干扰，缓存仅是 nginx(JS immutable/index.html no-cache)+浏览器。
  - **2026-07-22 实战**：用户报"属性与标签 通用属性/教材属性/.../试卷标签 一个接口都没有"。DB 核查：属性与标签9个子集合共45接口全在（通用8教材6试题4资源2教材知识点2知识点3试题6试卷5资源标签9），全局171。根因=旧前端未加载新构建（只取首20条请求）。已 `npm run build`，产物 `InterfaceManagement-CpBpXYCM.js` 含翻页逻辑。用户需硬刷新。
  - **全量排查方法**：用 Django shell + 实际 `ApiCollectionSerializer`/`ApiRequestSerializer` 模拟前端"建树→按 collection id 挂请求"流程，可确定是数据缺失还是前端显示问题（本次确认 44 个子集合全部正确挂接，无空集合）。
  - **测试套件执行超时（重要）**：`POST /api-testing/test-suites/<id>/execute/` 原先在**单个 HTTP 请求内同步串行执行全部接口**（每个 `requests.request(timeout=30)` 阻塞）。171 个接口串行耗时 >300s，触发 nginx `proxy_read_timeout 300s` → 504，并触发 Daphne 日志 `Application instance ... took too long to shut down and was killed`。**已修复（2026-07-22）**：`TestSuiteViewSet.execute` 改为立即创建 `RUNNING` 执行记录并 `threading.Thread(target=_run_test_suite_execution, daemon=True).start()` 后台执行，马上返回；前端 `AutomationTesting.vue runTestSuite` 轮询 `GET /api-testing/test-executions/<id>/` 每 1.5s 直到 `COMPLETED`/`FAILED`。`_run_test_suite_execution` 为模块级函数（含变量替换 `_replace_vars` 等），线程内用 `close_old_connections()` 收尾。**改后端必须重启 Daphne**（`taskkill /F /IM daphne.exe` 后 `start "" venv\Scripts\daphne -b 0.0.0.0 -p 8000 backend.asgi:application`），改前端必须 `npm run build` + 硬刷新。
  - **致命潜在 bug（已修，2026-07-22）**：`apps/api_testing/views.py` **第 1 行原本被损坏为 `modelsfrom rest_framework import viewsets, status`**（应是 `from`），属语法错误，会导致整个 `api_testing` app 无法 import、服务重启即崩。已改为 `from rest_framework import ...`。**若服务重启后 500/无法启动，先检查 views.py 第 1 行是否又被损坏**。

