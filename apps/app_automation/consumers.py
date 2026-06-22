import logging
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

logger = logging.getLogger(__name__)


class AppExecutionConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        try:
            self.execution_id = self.scope["url_route"]["kwargs"]["execution_id"]
            self.group_name = f"app_execution_{self.execution_id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            logger.info(f"WebSocket 连接成功: execution_id={self.execution_id}")
        except Exception as e:
            logger.error(f"WebSocket 连接失败: {e}")
            await self.close()

    async def disconnect(self, close_code):
        try:
            if hasattr(self, 'group_name'):
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
                logger.info(f"WebSocket 断开: execution_id={self.execution_id}, code={close_code}")
        except Exception as e:
            logger.error(f"WebSocket 断开处理失败: {e}")

    async def execution_update(self, event):
        try:
            await self.send_json(event)
        except Exception as e:
            logger.error(f"WebSocket 推送消息失败: {e}")


class AgentConsumer(AsyncJsonWebsocketConsumer):
    """
    Agent WebSocket Consumer - 处理远程 Agent 主机的连接

    协议：
    Agent → Server:
      - {"type": "register", "hostname": "...", "ip_address": "...", "version": "..."}
      - {"type": "device_sync", "devices": [...]}
      - {"type": "ping"}
      - {"type": "command_result", "request_id": "...", "success": true, "data": {...}}

    Server → Agent:
      - {"type": "registered", "host_id": "...", "message": "..."}
      - {"type": "sync_devices"}
      - {"type": "exec_command", "request_id": "...", "command": {...}}
      - {"type": "pong"}
      - {"type": "error", "message": "..."}
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host_id = None
        self.agent_info = {}

    # ---- Sync helpers (wrapped with database_sync_to_async) ----

    @staticmethod
    def _db_get_agent_host(host_id):
        """(sync) 查询 AgentHost 记录"""
        from .models import AgentHost
        try:
            return AgentHost.objects.filter(host_id=host_id).first()
        except Exception as e:
            logger.error(f"获取 AgentHost 失败: {e}")
            return None

    @staticmethod
    def _db_register_host(host_id, agent_info):
        """(sync) 创建或更新 AgentHost"""
        from .models import AgentHost
        host, created = AgentHost.objects.update_or_create(
            host_id=host_id,
            defaults={
                'hostname': agent_info.get('hostname', ''),
                'ip_address': agent_info.get('ip_address', ''),
                'port': agent_info.get('port', 0),
                'version': agent_info.get('version', ''),
                'status': 'online',
                'extra_info': agent_info.get('extra_info', {}),
            }
        )
        return host, created

    @staticmethod
    def _db_mark_agent_offline(host_id):
        """(sync) 断开时删除 Agent 主机，解除设备关联并标记离线"""
        from .models import AgentHost, AppDevice
        host = AgentHost.objects.filter(host_id=host_id).first()
        if host:
            hostname = host.hostname
            # 解除设备关联并标记离线
            AppDevice.objects.filter(
                agent_host=host
            ).exclude(status='locked').update(
                status='offline',
                agent_host=None
            )
            host.delete()
            return hostname
        return None

    @staticmethod
    def _db_sync_device(host_id, agent_device_id, dev_data, agent_host_id, host_ip):
        """(sync) 创建或更新单个设备记录"""
        from .models import AppDevice, AgentHost
        host = AgentHost.objects.filter(host_id=agent_host_id).first()
        if not host:
            return None, False

        adb_ip = dev_data.get("adb_ip", "") or host_ip

        device, created = AppDevice.objects.update_or_create(
            device_id=agent_device_id,
            defaults={
                'name': dev_data.get("name", ""),
                'status': dev_data.get("status", "online"),
                'android_version': dev_data.get("android_version", ""),
                'connection_type': 'agent_device',  # 强制标记为 Agent 代理设备
                'ip_address': adb_ip,
                'port': dev_data.get("tcp_port", 5555),
                'agent_host': host,
                'agent_device_id': dev_data.get("device_id", ""),
                'device_specs': dev_data.get("device_specs", {}),
            }
        )
        return device, created

    @staticmethod
    def _db_mark_stale_devices(agent_host_id, synced_device_ids):
        """(sync) 标记过期设备为离线，解除 agent_host 关联"""
        from .models import AppDevice, AgentHost
        host = AgentHost.objects.filter(host_id=agent_host_id).first()
        if not host:
            return 0
        return AppDevice.objects.filter(
            agent_host=host
        ).exclude(
            device_id__in=synced_device_ids
        ).exclude(
            status='locked'
        ).update(
            status='offline',
            agent_host=None
        )

    @staticmethod
    def _db_update_host_device_count(agent_host_id):
        """(sync) 更新主机设备数量 + last_seen"""
        from .models import AppDevice, AgentHost
        host = AgentHost.objects.filter(host_id=agent_host_id).first()
        if not host:
            return 0
        active_count = AppDevice.objects.filter(
            agent_host=host
        ).exclude(status='offline').count()
        host.device_count = active_count
        host.status = 'online'
        host.save()
        return active_count

    # ---- Async event handlers ----

    async def connect(self):
        try:
            # Agent 通过 URL 路径参数 host_id 标识（首次连接可为空，服务端分配）
            self.host_id = self.scope["url_route"]["kwargs"].get("host_id", "")

            # 捕获 Daphne 事件循环（供 sync 视图通过 run_coroutine_threadsafe 发送消息）
            from .managers.agent_registry import agent_registry
            agent_registry.capture_event_loop()

            await self.accept()
            logger.info(f"Agent WebSocket 连接已接受: host_id={self.host_id or '(待注册)'}")

            await self.send_json({
                "type": "welcome",
                "message": "请发送注册信息 (register)",
            })
        except Exception as e:
            logger.error(f"Agent WebSocket 连接失败: {e}")
            await self.close()

    async def disconnect(self, close_code):
        if self.host_id:
            try:
                from .managers.agent_registry import agent_registry
                agent_registry.unregister(host_id=self.host_id)

                hostname = await database_sync_to_async(
                    self._db_mark_agent_offline
                )(self.host_id)
                if hostname:
                    logger.info(f"Agent {self.host_id} 断开，已标记 {hostname} 所有设备为离线")
            except Exception as e:
                logger.error(f"Agent 注销失败: {e}")

        logger.info(f"Agent WebSocket 断开: host_id={self.host_id}, code={close_code}")

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        """覆盖父类 receive，添加全局异常捕获确保日志记录"""
        import sys
        try:
            return await super().receive(text_data=text_data, bytes_data=bytes_data, **kwargs)
        except BaseException as e:
            print(f"[WS-RECEIVE] 未捕获异常: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            logger.error(f"[WS-RECEIVE] 未捕获异常: {type(e).__name__}: {e}", exc_info=True)
            # 尝试发送错误消息
            try:
                await self.send_json({
                    "type": "error",
                    "message": f"内部错误: {type(e).__name__}: {e}",
                })
            except Exception:
                pass
            raise

    async def receive_json(self, content, **kwargs):
        """处理 Agent 发来的消息"""
        msg_type = content.get("type", "")

        try:
            if msg_type == "register":
                await self._handle_register(content)
            elif msg_type == "device_sync":
                await self._handle_device_sync(content)
            elif msg_type == "ping":
                await self._handle_ping(content)
            elif msg_type == "command_result":
                await self._handle_command_result(content)
            else:
                await self.send_json({
                    "type": "error",
                    "message": f"未知的消息类型: {msg_type}",
                })
        except Exception as e:
            logger.error(f"[WS-JSON] 处理 Agent 消息失败: {type(e).__name__}: {e}", exc_info=True)
            try:
                await self.send_json({
                    "type": "error",
                    "message": f"处理消息失败: {str(e)}",
                })
            except Exception:
                logger.error("[WS-JSON] 发送错误响应也失败", exc_info=True)

    async def _handle_register(self, content):
        """处理 Agent 注册"""
        import uuid
        import sys
        from .managers.agent_registry import agent_registry

        # 打印到 stderr 确保可见
        print(f"[REG-DEBUG] _handle_register 开始, content keys: {list(content.keys())}", file=sys.stderr, flush=True)

        try:
            self.agent_info = {
                "hostname": content.get("hostname", ""),
                "ip_address": content.get("ip_address", ""),
                "version": content.get("version", ""),
                "extra_info": content.get("extra_info", {}),
            }
            print(f"[REG-STEP1] agent_info done", file=sys.stderr, flush=True)
            logger.info(f"[REG-STEP1] agent_info 构建完成: {self.agent_info}")

            # 使用已有 host_id 或生成新的
            if not self.host_id:
                self.host_id = content.get("host_id", "")
            if not self.host_id:
                self.host_id = str(uuid.uuid4())[:12]
            print(f"[REG-STEP2] host_id={self.host_id}, channel={self.channel_name}", file=sys.stderr, flush=True)
            logger.info(f"[REG-STEP2] host_id={self.host_id}, channel_name={self.channel_name}")

            # 注册到 registry（内存）
            try:
                agent_registry.register(self.host_id, self.channel_name, self)
                print(f"[REG-STEP3] registry OK", file=sys.stderr, flush=True)
                logger.info(f"[REG-STEP3] registry 注册完成")
            except Exception as reg_err:
                print(f"[REG-STEP3] registry FAILED: {reg_err}", file=sys.stderr, flush=True)
                logger.error(f"[REG-STEP3] registry FAILED: {reg_err}", exc_info=True)
                raise

            # 数据库操作（异步安全）
            try:
                print(f"[REG-STEP4] 开始DB操作...", file=sys.stderr, flush=True)
                host, created = await database_sync_to_async(
                    self._db_register_host
                )(self.host_id, self.agent_info)
                print(f"[REG-STEP4] DB OK: hostname={host.hostname}, created={created}", file=sys.stderr, flush=True)
                logger.info(f"[REG-STEP4] DB操作完成: hostname={host.hostname if host else 'NONE'}, created={created}")
            except Exception as db_err:
                print(f"[REG-STEP4] DB FAILED: {type(db_err).__name__}: {db_err}", file=sys.stderr, flush=True)
                logger.error(f"[REG-STEP4] DB FAILED: {type(db_err).__name__}: {db_err}", exc_info=True)
                raise

            logger.info(f"Agent 注册成功: host_id={self.host_id}, hostname={host.hostname}, "
                        f"created={created}")

            await self.send_json({
                "type": "registered",
                "host_id": self.host_id,
                "message": f"注册成功，host_id={self.host_id}",
            })
            print(f"[REG-STEP5] registered sent", file=sys.stderr, flush=True)
            logger.info(f"[REG-STEP5] registered 响应已发送")

            await self.send_json({
                "type": "sync_devices",
                "message": "请发送设备列表 (device_sync)",
            })
            print(f"[REG-STEP6] sync_devices sent", file=sys.stderr, flush=True)
            logger.info(f"[REG-STEP6] sync_devices 请求已发送")

        except Exception as e:
            print(f"[REG-FAIL] {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            logger.error(f"[REG-FAIL] 注册处理失败: {type(e).__name__}: {e}", exc_info=True)
            raise

    async def _handle_device_sync(self, content):
        """处理 Agent 设备列表同步"""
        from .managers.agent_registry import agent_registry

        devices = content.get("devices", [])
        host_ip = self.agent_info.get("ip_address", "")

        if not self.host_id:
            await self.send_json({"type": "error", "message": "请先注册"})
            return

        # 验证 Agent 主机存在
        host = await database_sync_to_async(self._db_get_agent_host)(self.host_id)
        if not host:
            await self.send_json({"type": "error", "message": "Agent 主机未找到"})
            return

        logger.info(f"Agent {self.host_id} 上报 {len(devices)} 个设备")

        synced_device_ids = set()

        for dev in devices:
            local_device_id = dev.get("device_id", "")
            if not local_device_id:
                continue

            agent_device_id = f"agent:{self.host_id}:{local_device_id}"

            device, created = await database_sync_to_async(
                self._db_sync_device
            )(self.host_id, agent_device_id, dev, self.host_id, host_ip)

            if device:
                synced_device_ids.add(agent_device_id)
                if created:
                    logger.info(f"Agent 新设备: {agent_device_id} ({dev.get('name', '')})")

        # 标记过期设备为离线
        stale_count = await database_sync_to_async(
            self._db_mark_stale_devices
        )(self.host_id, synced_device_ids)

        if stale_count > 0:
            logger.info(f"Agent {self.host_id}: 标记 {stale_count} 台过期设备为离线")

        # 更新设备数量
        active_count = await database_sync_to_async(
            self._db_update_host_device_count
        )(self.host_id)

        # 更新 registry
        conn = agent_registry.get_by_host_id(self.host_id)
        if conn:
            conn.device_count = active_count
            conn.touch()

        await self.send_json({
            "type": "device_sync_ack",
            "message": f"同步完成，{len(devices)} 个设备",
            "synced_count": len(devices),
            "stale_count": stale_count,
        })

    async def _handle_ping(self, content):
        """处理心跳"""
        from .managers.agent_registry import agent_registry

        if self.host_id:
            conn = agent_registry.get_by_host_id(self.host_id)
            if conn:
                conn.touch()

            # 异步安全地更新 last_seen
            await database_sync_to_async(
                self._db_update_host_device_count
            )(self.host_id)

        await self.send_json({"type": "pong"})

    async def _handle_command_result(self, content):
        """处理 Agent 命令执行结果"""
        from .managers.agent_registry import agent_registry

        request_id = content.get("request_id", "")
        if request_id and self.host_id:
            agent_registry.resolve_response(self.host_id, request_id, content)
            logger.debug(f"Agent {self.host_id} 命令结果: request_id={request_id}, "
                        f"success={content.get('success')}")
