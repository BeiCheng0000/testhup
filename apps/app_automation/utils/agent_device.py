# -*- coding: utf-8 -*-
"""
Agent 设备解析工具 - 两种执行策略

方案A: 直接 TCP 连接
  从 agent:<host_id>:<local_device_id> 解析出真实 IP:Port，通过 TCP 直连设备执行测试
  
方案B: Agent 远程执行
  通过 WebSocket 将测试执行命令发送给 Agent，Agent 在远程主机上运行测试并回传结果
"""
import socket
import logging
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)

# Agent 设备 ID 格式: agent:<host_id>:<local_device_id>
AGENT_DEVICE_PREFIX = "agent:"


def is_agent_device(device_id: str) -> bool:
    """判断设备 ID 是否为 Agent 代理设备格式"""
    return device_id.startswith(AGENT_DEVICE_PREFIX)


def parse_agent_device_id(device_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    解析 Agent 设备 ID 格式
    
    Args:
        device_id: 格式 agent:<host_id>:<local_device_id>
        
    Returns:
        (host_id, local_device_id) 或 (None, None) 如果格式无效
    """
    if not is_agent_device(device_id):
        return None, None
    
    parts = device_id[len(AGENT_DEVICE_PREFIX):].split(':', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, None


def resolve_tcp_device_address(device_id: str, device=None) -> Optional[Dict[str, str]]:
    """
    将 Agent 设备 ID 解析为 Airtest 可识别的 TCP 连接地址
    
    方案A: 直接 TCP 连接
    
    Args:
        device_id: 原始设备ID
        device: AppDevice 模型实例（可选，可从数据库获取 ip/port）
        
    Returns:
        {
            'address': '192.168.1.100:5555',  # Airtest init_device 可用格式
            'strategy': 'direct_tcp',
            'host_id': 'agent-host-id',
            'local_device_id': 'emulator-5554',
        }
        或 None（无法解析）
    """
    host_id, local_device_id = parse_agent_device_id(device_id)
    if not host_id:
        return None
    
    result = {
        'strategy': 'direct_tcp',
        'host_id': host_id,
        'local_device_id': local_device_id,
        'address': None,
    }
    
    # 优先从数据库设备记录获取 IP 和端口
    if device and device.ip_address:
        port = device.port or 5555
        result['address'] = f"{device.ip_address}:{port}"
        return result
    
    # 尝试从 device_id 格式解析（如果是 emulator-5554 格式）
    if local_device_id.startswith('emulator-'):
        port = local_device_id.split('-')[1] if '-' in local_device_id else '5554'
        result['address'] = f"127.0.0.1:{port}"
        return result
    
    # 如果 local_device_id 本身已经是 IP:Port 格式
    if ':' in local_device_id:
        result['address'] = local_device_id
        return result
    
    return None


def check_tcp_reachable(host: str, port: int, timeout: float = 3.0) -> bool:
    """
    检查 TCP 地址是否可达
    
    Args:
        host: 主机 IP
        port: 端口号
        timeout: 超时秒数
        
    Returns:
        是否可达
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.debug(f"TCP 连通性检查失败 {host}:{port}: {e}")
        return False


def get_execution_strategy(device_id: str, device=None) -> Dict:
    """
    根据设备类型确定执行策略
    
    优先级：
    1. 非 Agent 设备 → 'local'（本地直连）
    2. Agent 设备 + TCP 可达 → 'direct_tcp'（方案A）
    3. Agent 设备 + Agent 在线 → 'agent_remote'（方案B）
    4. 以上都不可用 → 'unavailable'
    
    Args:
        device_id: 设备ID
        device: AppDevice 模型实例
        
    Returns:
        {
            'strategy': 'local' | 'direct_tcp' | 'agent_remote' | 'unavailable',
            'resolved_device_id': str,  # 执行时实际使用的 device_id
            'host_id': str | None,
            'local_device_id': str | None,
            'address': str | None,
            'error': str | None,
        }
    """
    result = {
        'strategy': 'unavailable',
        'resolved_device_id': device_id,
        'host_id': None,
        'local_device_id': None,
        'address': None,
        'error': None,
    }
    
    # 非 Agent 设备，直接使用
    if not is_agent_device(device_id):
        result['strategy'] = 'local'
        return result
    
    # Agent 设备解析
    host_id, local_device_id = parse_agent_device_id(device_id)
    if not host_id:
        result['error'] = f"无法解析 Agent 设备 ID: {device_id}"
        return result
    
    result['host_id'] = host_id
    result['local_device_id'] = local_device_id
    
    # 读取强制策略配置
    forced_strategy = _get_forced_strategy()
    
    tcp_info = resolve_tcp_device_address(device_id, device)
    tcp_address = tcp_info.get('address') if tcp_info else None
    
    # 检查 TCP 可达性
    tcp_reachable = False
    if tcp_address:
        host, _, port = tcp_address.partition(':')
        try:
            port_num = int(port)
        except (ValueError, TypeError):
            port_num = 5555
        tcp_reachable = check_tcp_reachable(host, port_num)
    
    # 检查 Agent 在线状态
    from ..managers.agent_registry import agent_registry
    conn = agent_registry.get_by_host_id(host_id)
    agent_online = conn is not None and conn.is_alive()
    
    # 强制策略模式
    if forced_strategy == 'direct_tcp':
        if tcp_reachable:
            result['strategy'] = 'direct_tcp'
            result['resolved_device_id'] = tcp_address
            result['address'] = tcp_address
            logger.info(f"Agent 设备 {device_id} → 强制 TCP 直连: {tcp_address}")
            return result
        else:
            result['error'] = f"强制 TCP 直连模式，但设备 {tcp_address} 不可达"
            logger.warning(result['error'])
            return result
    
    if forced_strategy == 'agent_remote':
        if agent_online:
            result['strategy'] = 'agent_remote'
            result['resolved_device_id'] = local_device_id
            result['address'] = tcp_address
            logger.info(f"Agent 设备 {device_id} → 强制 Agent 远程执行 (host_id={host_id})")
            return result
        else:
            result['error'] = f"强制 Agent 远程执行模式，但 Agent {host_id} 不在线"
            logger.warning(result['error'])
            return result
    
    # 自动模式（默认）：TCP 优先，Agent 远程备选
    if tcp_reachable:
        result['strategy'] = 'direct_tcp'
        result['resolved_device_id'] = tcp_address
        result['address'] = tcp_address
        logger.info(f"Agent 设备 {device_id} → TCP 直连: {tcp_address}")
        return result
    elif agent_online:
        result['strategy'] = 'agent_remote'
        result['resolved_device_id'] = local_device_id
        result['address'] = tcp_address
        logger.info(f"Agent 设备 {device_id} TCP 不可达，→ Agent 远程执行 (host_id={host_id})")
        return result
    else:
        result['error'] = (
            f"Agent 设备 {device_id} 不可用: "
            f"TCP 地址不可达，且 Agent {host_id} 不在线"
        )
        logger.warning(result['error'])
        return result


def _get_forced_strategy() -> str:
    """
    获取强制执行策略配置
    
    在 Django settings 中配置 AGENT_EXECUTION_STRATEGY:
    - 'auto': 自动选择（默认，TCP优先，Agent远程备选）
    - 'direct_tcp': 强制使用 TCP 直连（方案A）
    - 'agent_remote': 强制使用 Agent 远程执行（方案B）
    """
    try:
        from django.conf import settings
        strategy = getattr(settings, 'AGENT_EXECUTION_STRATEGY', 'auto')
        if strategy in ('direct_tcp', 'agent_remote', 'auto'):
            return strategy
        logger.warning(f"无效的 AGENT_EXECUTION_STRATEGY: {strategy}, 使用默认 auto")
        return 'auto'
    except Exception:
        return 'auto'
