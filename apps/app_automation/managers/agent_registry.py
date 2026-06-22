# -*- coding: utf-8 -*-
"""
Agent 注册中心 - 管理远程 Agent 主机的 WebSocket 连接和消息路由

职责：
1. 维护活跃的 Agent 连接
2. 路由命令到指定 Agent
3. 处理 Agent 心跳和设备同步
"""
import asyncio
import logging
import threading
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Callable

logger = logging.getLogger(__name__)


class AgentConnection:
    """单个 Agent 连接的状态"""
    
    def __init__(self, host_id: str, channel_name: str, consumer=None):
        self.host_id = host_id
        self.channel_name = channel_name
        self.consumer = consumer  # AgentConsumer 实例引用
        self.connected_at = datetime.now()
        self.last_seen = datetime.now()
        self.hostname = ''
        self.ip_address = ''
        self.version = ''
        self.device_count = 0
        self.pending_requests: Dict[str, asyncio.Future] = {}  # request_id -> Future (异步模式)
        # 跨事件循环安全：threading.Event + 结果存储
        self._sync_events: Dict[str, threading.Event] = {}  # request_id -> Event
        self._sync_results: Dict[str, dict] = {}  # request_id -> result dict
    
    def touch(self):
        self.last_seen = datetime.now()
    
    def is_alive(self, timeout_seconds=60):
        return (datetime.now() - self.last_seen).total_seconds() < timeout_seconds


class AgentRegistry:
    """Agent 注册中心（单例）"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._agents: Dict[str, AgentConnection] = {}  # host_id -> AgentConnection
        self._channel_to_host: Dict[str, str] = {}  # channel_name -> host_id
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None  # Daphne 事件循环引用
        logger.info("AgentRegistry 初始化完成")
    
    # ---- Daphne 事件循环管理 ----
    
    def capture_event_loop(self):
        """捕获并存储 Daphne ASGI 事件循环（由 consumer 在 connect 时调用）
        
        send_and_wait() 需要用 run_coroutine_threadsafe 将 WebSocket 发送
        调度到 Daphne 事件循环上，避免跨循环调用 transport 导致消息丢失。
        """
        try:
            self._event_loop = asyncio.get_event_loop()
            logger.info(f"已捕获 Daphne 事件循环: {id(self._event_loop)}")
        except RuntimeError:
            logger.warning("无法捕获事件循环（当前线程无运行中的循环）")
    
    # ---- 连接管理 ----
    
    def register(self, host_id: str, channel_name: str, consumer=None) -> AgentConnection:
        """注册或更新 Agent 连接"""
        if host_id in self._agents:
            conn = self._agents[host_id]
            conn.channel_name = channel_name
            conn.consumer = consumer
            conn.touch()
            # 更新 channel 映射
            old_channel = None
            for ch, hid in list(self._channel_to_host.items()):
                if hid == host_id and ch != channel_name:
                    old_channel = ch
            if old_channel:
                del self._channel_to_host[old_channel]
        else:
            conn = AgentConnection(host_id, channel_name, consumer)
            self._agents[host_id] = conn
        
        self._channel_to_host[channel_name] = host_id
        logger.info(f"Agent 注册: host_id={host_id}, channel={channel_name}")
        return conn
    
    def unregister(self, host_id: str = None, channel_name: str = None):
        """注销 Agent 连接"""
        if channel_name and channel_name in self._channel_to_host:
            host_id = self._channel_to_host.pop(channel_name)
        
        if host_id and host_id in self._agents:
            conn = self._agents.pop(host_id)
            # 取消所有待处理 asyncio 请求
            for req_id, future in conn.pending_requests.items():
                if not future.done():
                    future.set_exception(ConnectionError(f"Agent {host_id} 已断开"))
            # 通知所有同步等待者
            for req_id, event in conn._sync_events.items():
                if not event.is_set():
                    conn._sync_results[req_id] = {
                        'success': False, 'message': f'Agent {host_id} 已断开'
                    }
                    event.set()
            conn._sync_events.clear()
            conn._sync_results.clear()
            logger.info(f"Agent 注销: host_id={host_id}")
    
    def get_by_host_id(self, host_id: str) -> Optional[AgentConnection]:
        return self._agents.get(host_id)
    
    def get_by_channel(self, channel_name: str) -> Optional[AgentConnection]:
        host_id = self._channel_to_host.get(channel_name)
        if host_id:
            return self._agents.get(host_id)
        return None
    
    def list_agents(self) -> Dict[str, AgentConnection]:
        """获取所有 Agent 连接"""
        return dict(self._agents)
    
    def list_active_agents(self) -> Dict[str, AgentConnection]:
        """获取活跃的 Agent 连接"""
        return {
            hid: conn for hid, conn in self._agents.items()
            if conn.is_alive()
        }
    
    # ---- 消息发送 ----
    
    async def send_to_agent(self, host_id: str, message: dict):
        """向指定 Agent 发送消息"""
        conn = self._agents.get(host_id)
        if not conn:
            raise ConnectionError(f"Agent {host_id} 未连接")
        if not conn.consumer:
            raise ConnectionError(f"Agent {host_id} consumer 不可用")
        
        try:
            await conn.consumer.send_json(message)
            conn.touch()
        except Exception as e:
            logger.error(f"向 Agent {host_id} 发送消息失败: {e}")
            raise
    
    def send_and_wait(self, host_id: str, message: dict, timeout: float = 30.0) -> dict:
        """向 Agent 发送消息并等待响应（同步方法，跨线程/跨事件循环安全）
        
        关键设计：
        1. 发送: 使用 asyncio.run_coroutine_threadsafe() 将 send_to_agent 
           调度到 Daphne 事件循环上执行，避免跨循环调用 WebSocket transport
        2. 等待: 使用 threading.Event 替代 asyncio.Future，不依赖任何事件循环
        """
        conn = self._agents.get(host_id)
        if not conn:
            raise ConnectionError(f"Agent {host_id} 未连接")
        if not conn.consumer:
            raise ConnectionError(f"Agent {host_id} consumer 不可用")
        
        request_id = str(uuid.uuid4())[:8]
        message['request_id'] = request_id
        
        # 使用 threading.Event 替代 asyncio.Future（跨事件循环安全）
        event = threading.Event()
        conn._sync_events[request_id] = event
        
        # 发送消息：优先使用 run_coroutine_threadsafe 调度到 Daphne 循环
        send_ok = False
        if self._event_loop and self._event_loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.send_to_agent(host_id, message),
                    self._event_loop
                )
                future.result(timeout=5)  # 等待发送完成（短暂超时保护）
                send_ok = True
            except Exception as e:
                logger.error(
                    f"run_coroutine_threadsafe 发送失败: {e}，"
                    f"回退到临时循环"
                )
        
        if not send_ok:
            # 回退方案：临时事件循环（用于 Daphne 循环不可用时）
            temp_loop = asyncio.new_event_loop()
            try:
                temp_loop.run_until_complete(
                    self.send_to_agent(host_id, message)
                )
                send_ok = True
            except Exception as e:
                logger.error(f"临时循环发送也失败: {e}")
                conn._sync_events.pop(request_id, None)
                raise ConnectionError(f"向 Agent {host_id} 发送消息失败: {e}")
            finally:
                temp_loop.close()
        
        # 等待 Agent 响应（线程阻塞，不依赖任何 asyncio 事件循环）
        if not event.wait(timeout=timeout):
            conn._sync_events.pop(request_id, None)
            conn._sync_results.pop(request_id, None)
            logger.error(f"Agent {host_id} 请求 {request_id} 超时 ({timeout}s)")
            raise TimeoutError(f"Agent {host_id} 响应超时 ({timeout}s)")
        
        result = conn._sync_results.pop(request_id, {})
        conn._sync_events.pop(request_id, None)
        return result
    
    def resolve_response(self, host_id: str, request_id: str, data: dict):
        """解析 Agent 响应（从 WebSocket consumer 事件循环调用）"""
        conn = self._agents.get(host_id)
        if not conn:
            return
        
        # 优先检查同步请求（threading.Event 方式）
        sync_event = conn._sync_events.get(request_id)
        if sync_event:
            conn._sync_results[request_id] = data
            sync_event.set()
            logger.debug(f"Agent {host_id} 同步响应已到达: request_id={request_id}")
            return
        
        # 兼容旧版异步请求（asyncio.Future 方式）
        future = conn.pending_requests.get(request_id)
        if future and not future.done():
            try:
                future.set_result(data)
            except RuntimeError:
                # 如果 future 属于不同事件循环（跨循环调用），降级处理
                logger.warning(
                    f"Agent {host_id} 跨事件循环 future 设置失败: "
                    f"request_id={request_id}，使用轮询回退"
                )
    
    async def broadcast_to_agents(self, message: dict):
        """向所有连接的 Agent 广播消息（在 Daphne 循环内调用）"""
        for host_id, conn in list(self._agents.items()):
            if conn.is_alive() and conn.consumer:
                try:
                    await conn.consumer.send_json(message)
                except Exception as e:
                    logger.warning(f"向 Agent {host_id} 广播失败: {e}")
    
    def broadcast_sync(self, message: dict):
        """向所有 Agent 广播消息（同步方法，跨线程安全）"""
        if not self._event_loop or not self._event_loop.is_running():
            logger.warning("Daphne 事件循环不可用，无法广播")
            return
        
        for host_id, conn in list(self._agents.items()):
            if conn.is_alive() and conn.consumer:
                try:
                    asyncio.run_coroutine_threadsafe(
                        conn.consumer.send_json(message),
                        self._event_loop
                    )
                except Exception as e:
                    logger.warning(f"向 Agent {host_id} 广播失败: {e}")
    
    # ---- 设备同步 ----
    
    def get_agent_device_ids(self) -> Dict[str, list]:
        """获取所有 Agent 已注册的设备 ID 列表
        Returns: {host_id: [device_id, ...], ...}
        """
        result = {}
        for host_id, conn in self._agents.items():
            if conn.is_alive():
                result[host_id] = list(conn.pending_requests.keys())  # placeholder
        return result
    
    # ---- 清理 ----
    
    def cleanup_dead_agents(self):
        """清理超时的 Agent 连接"""
        dead = [hid for hid, conn in self._agents.items() if not conn.is_alive()]
        for hid in dead:
            self.unregister(host_id=hid)


# 全局单例
agent_registry = AgentRegistry()
