# -*- coding: utf-8 -*-
"""APP设备管理视图"""
import asyncio
import os
import base64
import gzip
import threading
import datetime
import platform
import tempfile
import xml.etree.ElementTree as ET
import logging

import subprocess
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
import django_filters

from .test_case_views import AppPagination
from ..models import AppDevice, AgentHost
from ..serializers import AppDeviceSerializer, AgentHostSerializer
from ..managers.device_manager import DeviceManager

logger = logging.getLogger(__name__)


def get_async_loop():
    """获取或创建事件循环，用于在同步代码中运行 async 函数"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


class AppDeviceFilter(django_filters.FilterSet):
    """设备过滤器：支持逗号分隔的多值状态筛选（如 status=online,available）"""
    status = django_filters.CharFilter(method='filter_status', label='设备状态')
    agent_host_id = django_filters.CharFilter(field_name='agent_host__host_id', lookup_expr='exact', label='Agent主机ID')
    has_agent = django_filters.BooleanFilter(method='filter_has_agent', label='是否有Agent')
    
    class Meta:
        model = AppDevice
        fields = ['status', 'connection_type']
    
    def filter_status(self, queryset, name, value):
        if value:
            status_list = [s.strip() for s in value.split(',') if s.strip()]
            if status_list:
                return queryset.filter(status__in=status_list)
        return queryset
    
    def filter_has_agent(self, queryset, name, value):
        if value:
            return queryset.exclude(agent_host__isnull=True)
        return queryset.filter(agent_host__isnull=True)

# 尝试导入 uiautomator2（类似 weditor 的元素获取方式）
try:
    import uiautomator2 as u2
    U2_AVAILABLE = True
except ImportError:
    U2_AVAILABLE = False
    u2 = None
    logger.warning("uiautomator2 未安装，将使用 adb uiautomator dump 回退方案")


def get_adb_path() -> str:
    """
    获取 ADB 路径：优先使用数据库配置，否则使用默认值 'adb'
    """
    try:
        from ..models import AppTestConfig
        config = AppTestConfig.objects.first()
        return config.adb_path if config else 'adb'
    except Exception as e:
        logger.warning(f"获取 ADB 配置失败，使用默认路径: {e}")
        return 'adb'


def _decompress_if_needed(data: dict) -> dict:
    """解压 Agent 返回的 gzip 压缩数据（兼容未压缩的旧数据）
    
    Agent 可能在 data 中标记 compressed='gzip' 表示内容经过 gzip 压缩。
    对于 xml_compressed='gzip' 的 XML 字段也会自动解压。
    """
    if not isinstance(data, dict):
        return data
    
    # 解压截图内容（content 字段中的 base64 数据）
    content = data.get('content', '')
    if content and data.get('compressed') == 'gzip':
        try:
            # 格式: data:image/png;base64,<gzip+base64>
            prefix = ''
            payload = content
            if ',' in content:
                parts = content.split(',', 1)
                prefix = parts[0] + ','
                payload = parts[1]
            decoded = gzip.decompress(base64.b64decode(payload))
            data['content'] = prefix + base64.b64encode(decoded).decode('utf-8')
            data['compressed'] = False  # 已解压
        except Exception as e:
            logger.warning(f"截图解压失败，保留原始数据: {e}")
    
    # 解压 XML
    xml_content = data.get('xml', '')
    if xml_content and data.get('xml_compressed') == 'gzip':
        try:
            decoded = gzip.decompress(base64.b64decode(xml_content))
            data['xml'] = decoded.decode('utf-8', errors='replace')
            data['xml_compressed'] = False
        except Exception as e:
            logger.warning(f"XML 解压失败，保留原始数据: {e}")
    
    # 解压 screenshot 字段 (dump_hierarchy 中的截图)
    screenshot_b64 = data.get('screenshot', '')
    if screenshot_b64 and data.get('screenshot_compressed') == 'gzip':
        try:
            decoded = gzip.decompress(base64.b64decode(screenshot_b64))
            data['screenshot'] = base64.b64encode(decoded).decode('utf-8')
            data['screenshot_compressed'] = False
        except Exception as e:
            logger.warning(f"层级截图解压失败，保留原始数据: {e}")
    
    return data


class AppDeviceViewSet(viewsets.ModelViewSet):
    """APP设备管理 ViewSet"""
    queryset = AppDevice.objects.all()
    serializer_class = AppDeviceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = AppDeviceFilter
    search_fields = ['device_id', 'name']
    
    # 设备状态同步缓存（避免频繁调用ADB）
    _last_device_sync = None
    _sync_lock = threading.Lock()
    _SYNC_INTERVAL = datetime.timedelta(seconds=10)
    
    @classmethod
    def _sync_device_status(cls):
        """通过ADB同步设备在线状态，带缓存避免频繁调用
        
        注意：Agent 代理设备的 device_id 格式为 "agent:<host_id>:<local_device_id>"，
        与本地 ADB 返回的 device_id 不匹配，因此需排除 Agent 设备，仅同步本地 ADB 设备。
        Agent 设备的状态由 WebSocket device_sync 消息独立管理。
        """
        now = timezone.now()
        
        # 如果上次同步在 SYNC_INTERVAL 内，跳过
        if cls._last_device_sync and (now - cls._last_device_sync) < cls._SYNC_INTERVAL:
            return
        
        # 使用线程锁防止并发重复执行
        if not cls._sync_lock.acquire(blocking=False):
            return
        
        try:
            # 再次检查（双重检查锁）
            if cls._last_device_sync and (now - cls._last_device_sync) < cls._SYNC_INTERVAL:
                return
            
            adb_path = get_adb_path()
            manager = DeviceManager(adb_path=adb_path)
            
            try:
                devices_info = manager.list_devices()
                online_device_ids = {d['device_id'] for d in devices_info}
                logger.info(f"ADB 在线设备: {online_device_ids}")
            except Exception as e:
                logger.warning(f"ADB 查询在线设备失败（暂不更新状态）: {e}")
                return
            
            # 统计变更
            changes_made = 0
            
            # 1. 数据库中标记为 online/available 但 ADB 中不存在的 → 标记为 offline
            #    （排除 Agent 代理设备和已锁定设备）
            db_online = AppDevice.objects.filter(
                status__in=['online', 'available'],
                agent_host__isnull=True  # Agent 设备状态由 WebSocket 管理，不通过本地 ADB 同步
            )
            for device in db_online:
                if device.device_id not in online_device_ids:
                    device.status = 'offline'
                    device.save(update_fields=['status', 'updated_at'])
                    changes_made += 1
                    logger.info(f"设备 {device.device_id} 已离线（ADB中未找到）")
            
            # 2. 数据库中标记为 offline 但 ADB 中存在的 → 标记为 online
            #    （排除 Agent 代理设备）
            db_offline = AppDevice.objects.filter(
                device_id__in=online_device_ids, status='offline',
                agent_host__isnull=True  # Agent 设备状态由 WebSocket 管理
            )
            for device in db_offline:
                device.status = 'online'
                device.save(update_fields=['status', 'updated_at'])
                changes_made += 1
                logger.info(f"设备 {device.device_id} 已上线（ADB中检测到）")
            
            if changes_made > 0:
                logger.info(f"设备状态同步完成，变更 {changes_made} 台设备")
            
            cls._last_device_sync = now
            
        finally:
            cls._sync_lock.release()
    
    def list(self, request, *args, **kwargs):
        """获取设备列表，自动同步ADB在线状态"""
        try:
            self._sync_device_status()
            self._sync_agent_devices()
        except Exception as e:
            logger.warning(f"同步设备状态失败（继续返回数据库状态）: {e}")
        return super().list(request, *args, **kwargs)
    
    @classmethod
    def _sync_agent_devices(cls):
        """同步 Agent 设备状态：检查 Agent 是否仍在线"""
        now = timezone.now()
        threshold = now - datetime.timedelta(seconds=60)
        
        # 检查超时的 Agent 主机
        stale_hosts = AgentHost.objects.filter(
            status='online',
            last_seen__lt=threshold
        )
        if stale_hosts.exists():
            for host in stale_hosts:
                device_cnt = host.device_count
                hostname = host.hostname
                # 标记该主机的设备为离线（解除 agent_host 关联）
                AppDevice.objects.filter(
                    agent_host=host
                ).exclude(status='locked').update(
                    status='offline',
                    agent_host=None
                )
                host.delete()
                logger.info(f"Agent {hostname} 超时，已删除，{device_cnt} 台设备离线")
    
    # ---- Agent 主机管理 ----
    
    @action(detail=False, methods=['get'], url_path='agent-hosts')
    def agent_hosts(self, request):
        """获取在线 Agent 主机列表（离线主机不保存、不显示）"""
        hosts = AgentHost.objects.filter(status='online')
        serializer = AgentHostSerializer(hosts, many=True)
        return Response({
            'success': True,
            'data': serializer.data,
            'count': hosts.count(),
        })
    
    @action(detail=False, methods=['post'], url_path='agent-sync')
    def agent_sync(self, request):
        """请求所有 Agent 同步设备列表"""
        from ..managers.agent_registry import agent_registry
        
        agents = agent_registry.list_active_agents()
        if not agents:
            return Response({
                'success': False,
                'message': '没有活跃的 Agent 连接',
            })
        
        agent_registry.broadcast_sync({
            "type": "sync_devices",
            "message": "服务器请求同步设备列表",
        })
        
        return Response({
            'success': True,
            'message': f'已向 {len(agents)} 个 Agent 发送同步请求',
            'agent_count': len(agents),
        })
    
    # ---- Agent 设备操作（截图/层级通过 Agent WebSocket 中继） ----
    
    def _is_agent_device(self, device):
        """判断是否为 Agent 代理设备（仅检查 agent_host 关联）"""
        return device.agent_host is not None
    
    def _agent_exec_command(self, device, command_type, **kwargs):
        """通过 Agent WebSocket 执行设备命令并等待结果（同步方法）"""
        from ..managers.agent_registry import agent_registry
        host_id = device.agent_host.host_id
        
        conn = agent_registry.get_by_host_id(host_id)
        if not conn or not conn.is_alive():
            raise ConnectionError(f"Agent {host_id} 未连接或已离线")
        
        message = {
            "type": "exec_command",
            "command_type": command_type,
            "device_id": device.agent_device_id or device.device_id,
            "adb_path": kwargs.get("adb_path", "adb"),
        }
        message.update(kwargs)
        
        return agent_registry.send_and_wait(host_id, message, timeout=kwargs.get("timeout", 30))
    
    @action(detail=False, methods=['get'])
    def discover(self, request):
        """发现ADB设备（同时触发Agent主机设备同步）"""
        try:
            adb_path = get_adb_path()
            logger.info(f"使用 ADB 路径: {adb_path}")
            
            manager = DeviceManager(adb_path=adb_path)
            devices_info = manager.list_devices()
            
            # 更新或创建设备记录
            db_devices = []
            for device_info in devices_info:
                # 判断连接类型和 IP 地址
                device_id = device_info['device_id']
                if ':' in device_id:
                    # 远程设备（IP:端口格式）
                    connection_type = 'remote_emulator'
                    ip_address = device_info.get('ip_address') or ''
                elif device_id.startswith('emulator-'):
                    # 本地模拟器 - 使用 localhost
                    connection_type = 'emulator'
                    ip_address = '127.0.0.1'
                else:
                    # USB 连接的真机
                    connection_type = 'usb'
                    ip_address = device_info.get('ip_address') or ''
                
                device, created = AppDevice.objects.update_or_create(
                    device_id=device_info['device_id'],
                    defaults={
                        'name': device_info.get('name') or '',
                        'status': device_info.get('status') or 'offline',
                        'android_version': device_info.get('android_version') or '',
                        'ip_address': ip_address,
                        'port': device_info.get('port') or 5555,
                        'connection_type': connection_type,
                    }
                )
                db_devices.append(device)
            
            # 标记ADB中不存在的设备为离线（不含已锁定设备和Agent设备）
            adb_device_ids = {d['device_id'] for d in devices_info}
            offline_count = AppDevice.objects.exclude(
                device_id__in=adb_device_ids
            ).exclude(
                status='locked'
            ).filter(
                status__in=['online', 'available'],
                agent_host__isnull=True  # Agent 设备状态由 WebSocket 管理
            ).update(status='offline')
            if offline_count > 0:
                logger.info(f"discover: 标记 {offline_count} 台设备为离线")
            
            # ===== 触发 Agent 主机设备同步 =====
            from ..managers.agent_registry import agent_registry
            agents = agent_registry.list_active_agents()
            agent_sync_msg = ''
            if agents:
                try:
                    agent_registry.broadcast_sync({
                        "type": "sync_devices",
                        "message": "服务器请求同步设备列表",
                    })
                    agent_sync_msg = f'，已向 {len(agents)} 个 Agent 主机发送同步请求'
                    logger.info(f"discover: 已向 {len(agents)} 个 Agent 发送同步请求")
                except Exception as e:
                    logger.warning(f"discover: Agent 同步请求发送失败: {e}")
            
            # ===== 统计 Agent 主机和设备数量 =====
            agent_device_count = AppDevice.objects.filter(
                agent_host__isnull=False
            ).exclude(status='offline').count()
            
            agent_host_count = AgentHost.objects.filter(status='online').count()
            
            # 更新同步时间
            AppDeviceViewSet._last_device_sync = timezone.now()
            
            # 构造消息
            parts = [f'发现 {len(db_devices)} 个本地设备']
            if agent_device_count > 0:
                parts.append(f'{agent_device_count} 个Agent设备')
            if agent_host_count > 0:
                parts.append(f'({agent_host_count} 个Agent主机在线)')
            msg = '，'.join(parts) + agent_sync_msg
            
            return Response({
                'success': True,
                'message': msg,
                'devices': AppDeviceSerializer(db_devices, many=True).data,
                'total_devices': len(db_devices) + agent_device_count,
                'local_device_count': len(db_devices),
                'agent_device_count': agent_device_count,
                'agent_host_count': agent_host_count,
            })
        except Exception as e:
            logger.error(f"发现设备失败: {str(e)}")
            return Response({
                'success': False,
                'message': f'发现设备失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def lock(self, request, pk=None):
        """锁定设备"""
        device = self.get_object()
        
        if device.status == 'locked':
            return Response({
                'success': False,
                'message': '设备已被锁定'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        device.lock(request.user)
        
        return Response({
            'success': True,
            'message': '设备锁定成功',
            'device': AppDeviceSerializer(device).data
        })
    
    @action(detail=True, methods=['post'])
    def unlock(self, request, pk=None):
        """释放设备"""
        device = self.get_object()
        
        if device.locked_by and device.locked_by != request.user:
            return Response({
                'success': False,
                'message': '无权释放他人锁定的设备'
            }, status=status.HTTP_403_FORBIDDEN)
        
        device.unlock()
        
        return Response({
            'success': True,
            'message': '设备释放成功',
            'device': AppDeviceSerializer(device).data
        })
    
    @action(detail=True, methods=['post'])
    def disconnect(self, request, pk=None):
        """断开远程设备连接"""
        device = self.get_object()
        
        # 只有远程设备可以断开
        if device.connection_type not in ['remote', 'remote_emulator']:
            return Response({
                'success': False,
                'message': '只能断开远程设备的连接'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            adb_path = get_adb_path()
            manager = DeviceManager(adb_path=adb_path)
            success = manager.disconnect_device(f'{device.ip_address}:{device.port}')
            
            if not success:
                return Response({
                    'success': False,
                    'message': '断开设备失败'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # 更新设备状态为离线
            device.status = 'offline'
            device.save()
            
            return Response({
                'success': True,
                'message': f'设备 {device.name or device.device_id} 已断开连接',
                'device': AppDeviceSerializer(device).data
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'message': f'断开设备失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def connect(self, request):
        """连接远程设备"""
        try:
            ip_address = request.data.get('ip_address')
            port = request.data.get('port', 5555)
            
            if not ip_address:
                return Response({
                    'success': False,
                    'message': '请提供设备IP地址'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            adb_path = get_adb_path()
            manager = DeviceManager(adb_path=adb_path)
            device_info = manager.connect_device(ip_address, port)
            
            # 创建或更新设备记录
            device, created = AppDevice.objects.update_or_create(
                device_id=device_info['device_id'],
                defaults={
                    'name': device_info.get('name') or '',
                    'status': 'online',
                    'android_version': device_info.get('android_version', ''),
                    'ip_address': ip_address,
                    'port': port,
                    'connection_type': 'remote_emulator',
                }
            )
            
            return Response({
                'success': True,
                'message': '设备连接成功',
                'device': AppDeviceSerializer(device).data
            })
        except Exception as e:
            logger.error(f"连接设备失败: {str(e)}")
            return Response({
                'success': False,
                'message': f'连接设备失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_path='screenshot')
    def screenshot(self, request, pk=None):
        """
        获取设备实时截图

        功能：
        1. 本地/远程设备：使用 adb screencap 获取设备截图
        2. Agent 代理设备：通过 Agent WebSocket 中继截图命令
        3. 转换为 Base64
        4. 返回 data URL 格式
        """
        device = self.get_object()
        
        if device.status == 'offline':
            return Response({
                'code': 400,
                'msg': '设备离线，无法截图',
                'success': False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Agent 代理设备：通过 WebSocket 中继
        if self._is_agent_device(device):
            return self._agent_screenshot(device)
        
        # 本地/远程设备：直接 ADB
        try:
            adb_path = get_adb_path()
            
            device_id = device.device_id
            if device.connection_type in ['remote_emulator', 'remote']:
                if ':' not in device_id:
                    device_id = f"{device.ip_address}:{device.port}"
                    logger.info(f"远程设备使用地址: {device_id}")
            
            kwargs = {}
            if platform.system() == 'Windows':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            
            result = subprocess.run(
                [adb_path, '-s', device_id, 'exec-out', 'screencap', '-p'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=10,
                **kwargs
            )
            
            if not result.stdout:
                logger.error(f"设备 {device_id} 截图返回空数据")
                return Response({
                    'code': 500,
                    'msg': '截图失败：设备未返回截图数据，请检查设备屏幕是否开启',
                    'success': False
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            image_base64 = base64.b64encode(result.stdout).decode('utf-8')
            logger.info(f"设备 {device_id} 截图成功，大小: {len(result.stdout)} bytes")
            
            return Response({
                'code': 0,
                'msg': '截图成功',
                'success': True,
                'data': {
                    'filename': f"device_{device.id}_{int(timezone.now().timestamp())}.png",
                    'content': f"data:image/png;base64,{image_base64}",
                    'device_id': device_id,
                    'timestamp': int(timezone.now().timestamp())
                }
            })
            
        except FileNotFoundError:
            logger.error(f"ADB 命令未找到，路径: {adb_path}")
            return Response({
                'code': 500,
                'msg': f'ADB 命令未找到，请检查 ADB 路径配置',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except subprocess.CalledProcessError as e:
            stderr_msg = e.stderr.decode('utf-8', errors='replace').strip() if e.stderr else ''
            error_detail = stderr_msg or str(e)
            logger.error(f"设备 {device.device_id} ADB 截图命令失败 (returncode={e.returncode}): {error_detail}")
            return Response({
                'code': 500,
                'msg': f'设备截图失败: {error_detail}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except subprocess.TimeoutExpired:
            logger.error(f"设备 {device.device_id} 截图超时")
            return Response({
                'code': 500,
                'msg': '截图超时，请检查设备连接状态',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"设备 {device.device_id} 截图失败: {str(e)}", exc_info=True)
            return Response({
                'code': 500,
                'msg': f'截图失败: {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _agent_screenshot(self, device):
        """通过 Agent WebSocket 获取 Agent 代理设备的截图"""
        try:
            result = self._agent_exec_command(device, 'screenshot', timeout=25)
            if result.get('success'):
                data = _decompress_if_needed(result.get('data', {}))
                return Response({
                    'code': 0,
                    'msg': '截图成功 (Agent)',
                    'success': True,
                    'data': {
                        'filename': f"agent_device_{device.id}_{int(timezone.now().timestamp())}.png",
                        'content': data.get('content', ''),
                        'device_id': device.device_id,
                        'timestamp': int(timezone.now().timestamp()),
                        'via_agent': device.agent_host.hostname if device.agent_host else 'unknown',
                    }
                })
            else:
                return Response({
                    'code': 500,
                    'msg': f'Agent 截图失败: {result.get("message", "未知错误")}',
                    'success': False
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except ConnectionError as e:
            return Response({
                'code': 503,
                'msg': f'Agent 连接失败: {str(e)}',
                'success': False
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except TimeoutError:
            return Response({
                'code': 500,
                'msg': 'Agent 截图超时 (25s)',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"Agent 截图失败: {str(e)}")
            return Response({
                'code': 500,
                'msg': f'Agent 截图异常: {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='dump-hierarchy')
    def dump_hierarchy(self, request, pk=None):
        """
        获取设备截图 + UI 层级树信息
        
        功能：
        1. 使用 adb screencap 获取设备截图（skip_screenshot=1 时跳过）
        2. 使用 adb shell uiautomator dump 获取 UI 层级 XML
        3. 解析 XML 提取可交互元素（resource-id, class, text, bounds 等）
        4. 返回截图 Base64 + 元素列表
        
        URL参数：
        - skip_screenshot: 1/true 跳过截图，仅返回层级元素（前端已持有截图时使用）
        
        返回的元素字段：
        - index: 元素在同级中的序号
        - resource_id: Android resource-id
        - class_name: 控件类名
        - text: 显示文本
        - content_desc: 内容描述（无障碍）
        - bounds: [x1, y1, x2, y2] 屏幕坐标
        - clickable: 是否可点击
        - xpath: 自动生成的 XPath 定位表达式
        - depth: 层级深度
        """
        device = self.get_object()
        
        if device.status == 'offline':
            return Response({
                'code': 400,
                'msg': '设备离线，无法获取层级信息',
                'success': False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Agent 代理设备：通过 WebSocket 中继
        if self._is_agent_device(device):
            skip_screenshot = request.query_params.get('skip_screenshot', '') in ('1', 'true', 'True')
            return self._agent_dump_hierarchy(device, request, skip_screenshot=skip_screenshot)
        
        skip_screenshot = request.query_params.get('skip_screenshot', '') in ('1', 'true', 'True')
        
        try:
            adb_path = get_adb_path()
            
            # 对远程设备，确保 device_id 是 IP:port 格式
            device_id = device.device_id
            if device.connection_type in ['remote_emulator', 'remote']:
                if ':' not in device_id:
                    device_id = f"{device.ip_address}:{device.port}"
                    logger.info(f"远程设备使用地址: {device_id}")
            
            # Windows 子进程创建标志
            kwargs = {}
            if platform.system() == 'Windows':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            
            screenshot_base64 = ''
            resolution = {'width': 0, 'height': 0}
            
            # ============ 步骤1: Dump UI 层级（先执行，避免后续操作改变屏幕状态）============
            # 优先使用 uiautomator2（类似 weditor，能获取更丰富的元素属性包括 text）
            # 失败时回退到 adb uiautomator dump
            xml_content = None
            
            if U2_AVAILABLE:
                try:
                    xml_content = self._dump_hierarchy_with_u2(
                        device_id=device_id,
                        connection_type=device.connection_type,
                        ip_address=device.ip_address,
                        port=device.port
                    )
                    if xml_content:
                        # 通过 u2 获取分辨率（更准确）
                        try:
                            u2_device = self._get_u2_device(
                                device_id=device_id,
                                connection_type=device.connection_type,
                                ip_address=device.ip_address,
                                port=device.port
                            )
                            u2_info = u2_device.info
                            resolution = {
                                'width': u2_info.get('displayWidth', 0),
                                'height': u2_info.get('displayHeight', 0)
                            }
                        except Exception:
                            pass  # 分辨率回退使用 wm size 结果
                        logger.info(f"设备 {device_id} 使用 uiautomator2 获取层级成功")
                except Exception as e:
                    logger.warning(f"uiautomator2 层级获取失败，回退到 adb uiautomator dump: {e}")
            
            if not xml_content:
                # 回退方案：adb uiautomator dump（多路径容错）
                xml_content = self._dump_hierarchy_with_adb(
                    adb_path=adb_path,
                    device_id=device_id,
                    kwargs=kwargs
                )
            
            # ============ 步骤2: 截图（在层级 dump 之后执行，确保两者状态一致）============
            if not skip_screenshot:
                try:
                    screencap_result = subprocess.run(
                        [adb_path, '-s', device_id, 'exec-out', 'screencap', '-p'],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=True,
                        timeout=10,
                        **kwargs
                    )
                    
                    if screencap_result.stdout:
                        screenshot_base64 = base64.b64encode(screencap_result.stdout).decode('utf-8')
                        logger.info(f"设备 {device_id} 截图成功，大小: {len(screencap_result.stdout)} bytes")
                except Exception as e:
                    logger.warning(f"设备 {device_id} 截图失败: {e}")
                    # 截图失败不中断流程，层级数据仍然可用
            
            # ============ 步骤3: 获取屏幕分辨率（如果 u2 没有提供）============
            if resolution['width'] == 0 or resolution['height'] == 0:
                try:
                    wm_result = subprocess.run(
                        [adb_path, '-s', device_id, 'shell', 'wm', 'size'],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=True,
                        timeout=5,
                        **kwargs
                    )
                    wm_output = wm_result.stdout.decode('utf-8', errors='replace').strip()
                    import re
                    match = re.search(r'(\d+)\s*x\s*(\d+)', wm_output)
                    if match:
                        resolution['width'] = int(match.group(1))
                        resolution['height'] = int(match.group(2))
                except Exception:
                    logger.warning(f"获取屏幕分辨率失败")
            
            # 4. 解析 XML 提取元素
            elements = []
            try:
                # uiautomator2 返回的 XML 可能以 byte 形式，统一处理
                if isinstance(xml_content, bytes):
                    xml_content = xml_content.decode('utf-8', errors='replace')
                
                # 移除可能的 BOM 或空白前缀
                xml_content = xml_content.strip()
                if not xml_content.startswith('<'):
                    # 有些输出可能在 XML 前有额外文本
                    xml_start = xml_content.find('<?xml')
                    if xml_start == -1:
                        xml_start = xml_content.find('<hierarchy')
                    if xml_start >= 0:
                        xml_content = xml_content[xml_start:]
                
                root = ET.fromstring(xml_content)
                
                # uiautomator2 返回的 XML 可能直接是 <hierarchy> 根节点
                if root.tag == 'hierarchy':
                    for child in root:
                        elements.extend(self._parse_hierarchy_nodes(child))
                else:
                    elements.extend(self._parse_hierarchy_nodes(root))
                    
            except ET.ParseError as pe:
                logger.error(f"XML 解析失败: {pe}, XML前200字符: {xml_content[:200] if xml_content else 'None'}")
                return Response({
                    'code': 500,
                    'msg': f'UI层级 XML 解析失败: {str(pe)}',
                    'success': False
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # 校验截图分辨率与层级坐标系统一致性
            screenshot_resolution_note = ''
            if screenshot_base64:
                import struct, io
                try:
                    # 解析 PNG 头获取截图尺寸
                    png_data = base64.b64decode(screenshot_base64)
                    if png_data[:8] == b'\x89PNG\r\n\x1a\n':
                        # IHDR chunk 在第 16-23 字节: width(4) + height(4)
                        ihdr_w = struct.unpack('>I', png_data[16:20])[0]
                        ihdr_h = struct.unpack('>I', png_data[20:24])[0]
                        if ihdr_w != resolution['width'] or ihdr_h != resolution['height']:
                            screenshot_resolution_note = (
                                f' 注意：截图尺寸({ihdr_w}x{ihdr_h})与设备分辨率'
                                f'({resolution["width"]}x{resolution["height"]})不一致，'
                                f'将以截图尺寸为准进行元素坐标映射'
                            )
                            # 以截图尺寸为准
                            resolution['width'] = ihdr_w
                            resolution['height'] = ihdr_h
                        logger.info(
                            f"设备 {device_id} 截图分辨率: {ihdr_w}x{ihdr_h}, "
                            f"层级分辨率: {resolution['width']}x{resolution['height']}"
                        )
                except Exception:
                    pass
            
            logger.info(f"设备 {device_id} 层级获取成功，提取 {len(elements)} 个元素{screenshot_resolution_note}")
            
            response_data = {
                'resolution': resolution,
                'elements': elements,
                'total_count': len(elements)
            }
            if screenshot_base64:
                response_data['screenshot'] = f"data:image/png;base64,{screenshot_base64}"
            
            return Response({
                'code': 0,
                'msg': '层级获取成功',
                'success': True,
                'data': response_data
            })
            
        except FileNotFoundError:
            logger.error(f"ADB 命令未找到，路径: {adb_path}")
            return Response({
                'code': 500,
                'msg': f'ADB 命令未找到，请检查 ADB 路径配置',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except subprocess.CalledProcessError as e:
            stderr_msg = e.stderr.decode('utf-8', errors='replace').strip() if e.stderr else ''
            stdout_msg = e.stdout.decode('utf-8', errors='replace').strip() if e.stdout else ''
            error_detail = stderr_msg or stdout_msg or str(e)
            logger.error(f"设备 {device.device_id} 层级dump失败 (returncode={e.returncode}): {error_detail}")
            
            if e.returncode == 137 or e.returncode == -9:
                msg = ('uiautomator 进程被设备杀死(返回码137)，'
                       '可能是设备内存不足。建议：关闭后台应用后重试')
            else:
                msg = f'获取UI层级失败: {error_detail}'
            return Response({
                'code': 500,
                'msg': msg,
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except subprocess.TimeoutExpired:
            logger.error(f"设备 {device.device_id} 层级获取超时")
            return Response({
                'code': 500,
                'msg': '获取UI层级超时，请检查设备连接状态',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"设备 {device.device_id} 层级获取失败: {str(e)}", exc_info=True)
            return Response({
                'code': 500,
                'msg': f'获取UI层级失败: {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @staticmethod
    def _parse_hierarchy_nodes(node, parent_path='', depth=0, sibling_index=None):
        """
        递归解析 UI 层级 XML 节点
        
        过滤掉无意义节点（bounds 为空或面积为 0）
        为每个节点生成 XPath 定位表达式
        """
        elements = []
        
        # 获取节点属性
        class_name = node.attrib.get('class', '')
        resource_id = node.attrib.get('resource-id', '')
        text = node.attrib.get('text', '')
        content_desc = node.attrib.get('content-desc', '')
        bounds_str = node.attrib.get('bounds', '')
        clickable = node.attrib.get('clickable', 'false').lower() == 'true'
        checkable = node.attrib.get('checkable', 'false').lower() == 'true'
        scrollable = node.attrib.get('scrollable', 'false').lower() == 'true'
        package_name = node.attrib.get('package', '')
        index_str = node.attrib.get('index', '0')
        
        # 解析 bounds
        bounds = None
        import re
        bounds_match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
        if bounds_match:
            x1, y1, x2, y2 = map(int, bounds_match.groups())
            # 过滤无意义节点（面积为 0 或坐标无效）
            if x2 > x1 and y2 > y1:
                bounds = [x1, y1, x2, y2]
        
        # 构建 XPath 路径
        # 计算同级相同 class 的元素序号
        class_count_path = f"{parent_path}/{class_name}"
        xpath = f"{parent_path}/{class_name}[@index='{index_str}']"
        if resource_id:
            xpath = f"{parent_path}/{class_name}[@resource-id='{resource_id}']"
        if text:
            xpath = f"{parent_path}/{class_name}[@text='{text}']"
        
        # 返回所有有效 bounds 的节点（不过滤，让前端实现"点击查找元素"）
        # 与 weditor 行为一致：保留完整层级树，点击时通过坐标匹配最深节点
        if bounds:
            elements.append({
                'index': int(index_str) if index_str.isdigit() else 0,
                'resource_id': resource_id,
                'class_name': class_name.split('.')[-1] if '.' in class_name else class_name,
                'class_name_full': class_name,
                'text': text,
                'content_desc': content_desc,
                'bounds': bounds,
                'clickable': clickable,
                'checkable': checkable,
                'scrollable': scrollable,
                'xpath': xpath,
                'depth': depth,
                'package': package_name,
            })
        
        # 递归处理子节点
        for idx, child in enumerate(node):
            child_path = f"{parent_path}/{class_name}[{idx + 1}]"
            child_elements = AppDeviceViewSet._parse_hierarchy_nodes(
                child, 
                parent_path=child_path,
                depth=depth + 1,
                sibling_index=idx
            )
            elements.extend(child_elements)
        
        return elements
    
    @staticmethod
    def _get_u2_device(device_id, connection_type='emulator', ip_address='', port=5555):
        """
        获取 uiautomator2 设备连接
        
        支持 USB 设备和远程设备（IP:port）
        自动安装/启动 ATX agent 到设备上
        """
        if connection_type in ('remote_emulator', 'remote'):
            # 远程设备：使用 IP:port 连接
            if ':' in device_id:
                addr = device_id
            else:
                addr = f"{ip_address}:{port}"
            return u2.connect(addr)
        else:
            # USB 设备：使用序列号连接
            return u2.connect(device_id)
    
    @staticmethod
    def _ensure_u2_atx_agent(d, device_id, timeout=30):
        """
        确保 ATX agent 已在设备上安装并运行
        
        如果 uiautomator2 连接后无法正常工作，尝试自动安装 ATX agent
        返回：是否成功
        """
        import time as _time
        
        try:
            # 快速检测：尝试获取设备信息看是否连通
            info = d.info
            if info:
                logger.info(f"u2 ATX agent 已在设备 {device_id} 上运行")
                return True
        except Exception:
            pass
        
        # ATX agent 未运行，尝试自动安装
        try:
            logger.info(f"正在为设备 {device_id} 安装 ATX agent (最多等待{timeout}s)...")
            # uiautomator2 的 connect() 会自动尝试安装 agent，
            # 但有时需要显式调用
            if hasattr(d, '_is_alive') and not d._is_alive():
                d.reset_uiautomator()  # 重新启动 uiautomator 服务
            _time.sleep(2)
            
            # 验证连接
            info = d.info
            if info:
                logger.info(f"u2 ATX agent 安装/启动成功: {device_id}")
                return True
        except Exception as e:
            logger.warning(f"u2 ATX agent 安装失败: {device_id}: {e}")
        
        return False
    
    @staticmethod
    def _dump_hierarchy_with_u2(device_id, connection_type='emulator', ip_address='', port=5555):
        """
        使用 uiautomator2 获取 UI 层级 XML（类似 weditor 的方式）
        
        优势：
        - 通过 ATX agent 执行 uiautomator dump，输入输出走 socket 而非文件
        - 元素属性更丰富（text/content-desc 等更准确）
        - ATX agent 作为持久服务，避免每次新建进程导致的 OOM
        
        返回：XML 字符串，失败返回 None
        """
        import time as _time
        
        try:
            d = AppDeviceViewSet._get_u2_device(device_id, connection_type, ip_address, port)
            logger.info(f"u2 设备连接成功: {device_id}, 尝试获取层级...")
        except Exception as e:
            logger.warning(f"u2 设备连接失败: {device_id}: {e}")
            return None
        
        # 确保 ATX agent 正常运行
        if not AppDeviceViewSet._ensure_u2_atx_agent(d, device_id):
            logger.warning(f"u2 ATX agent 不可用: {device_id}")
            return None
        
        # 获取层级 XML
        # uiautomator2 内部通过 ATX agent 执行 uiautomator dump，
        # XML 通过 socket 流式返回，不需要写设备文件，内存效率更高
        try:
            xml_content = d.dump_hierarchy()
        except Exception as e:
            logger.warning(f"u2 dump_hierarchy 失败: {device_id}: {e}")
            return None
        
        if not xml_content:
            logger.warning(f"uiautomator2 dump_hierarchy 返回空内容: {device_id}")
            return None
        
        logger.info(f"u2 层级获取成功: {device_id}, XML 大小: {len(xml_content)} 字节")
        return xml_content
    
    @staticmethod
    def _free_device_memory(adb_path, device_id, kwargs):
        """
        在 dump 前释放设备内存，提高 dump 成功率
        
        策略：
        1. 按 Home 键最小化当前应用（减少 UI 复杂度）
        2. 杀掉已知的内存消耗大户（非关键系统应用）
        3. 触发系统 GC
        """
        # 常见可安全 kill 的第三方/非关键包（白名单方式：只杀已知的非系统包）
        safe_to_kill = [
            'com.android.chrome',
            'com.google.android.gms.persistent',
            'com.google.android.googlequicksearchbox',
        ]
        
        memory_freed = False
        
        # 1. 先按 Home 键，减少当前前台应用的 UI 树复杂度
        try:
            subprocess.run(
                [adb_path, '-s', device_id, 'shell', 'input', 'keyevent', 'KEYCODE_HOME'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=3, **kwargs
            )
            memory_freed = True
            logger.debug(f"设备 {device_id}: 已按 Home 键减少 UI 复杂度")
        except Exception:
            pass
        
        # 2. 杀掉已知可安全关闭的应用
        for pkg in safe_to_kill:
            try:
                subprocess.run(
                    [adb_path, '-s', device_id, 'shell', 'am', 'force-stop', pkg],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=3, **kwargs
                )
                memory_freed = True
            except Exception:
                pass
        
        if memory_freed:
            # 等待内存回收
            import time as _time
            _time.sleep(1)
            logger.info(f"设备 {device_id}: 已尝试释放内存")
    
    @staticmethod
    def _dump_hierarchy_with_adb(adb_path, device_id, kwargs):
        """
        使用 adb uiautomator dump 获取 UI 层级 XML（回退方案）
        
        多路径容错 + OOM 重试机制：
        1. 首次尝试：直接 dump
        2. 如果 OOM(137)：释放内存后重试一次
        3. 如果仍失败：抛出友好错误
        
        返回：XML 字符串，失败抛出异常
        """
        dump_paths = [
            '/data/local/tmp/testhub_uidump.xml',
            '/sdcard/testhub_uidump.xml',
        ]
        
        # 先清理设备上可能残留的 dump 文件
        for path in dump_paths:
            try:
                subprocess.run(
                    [adb_path, '-s', device_id, 'shell', 'rm', '-f', path],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=5, **kwargs
                )
            except Exception:
                pass
        
        def attempt_dump(attempt_label=''):
            """单次 dump 尝试，返回 (success, dump_path, error_info)"""
            nonlocal last_error_info
            for path in dump_paths:
                try:
                    result = subprocess.run(
                        [adb_path, '-s', device_id, 'shell', 'uiautomator', 'dump', path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=True,
                        timeout=20,  # 给足时间
                        **kwargs
                    )
                    stdout_text = result.stdout.decode('utf-8', errors='replace').strip()
                    
                    if 'dumped to' in stdout_text.lower() or 'UI hierchary' in stdout_text:
                        # 验证文件确实存在再确认成功
                        verify = subprocess.run(
                            [adb_path, '-s', device_id, 'shell', f'ls -l {path} 2>/dev/null && echo EXISTS || echo MISSING'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=5, **kwargs
                        )
                        if b'EXISTS' in verify.stdout:
                            logger.info(f"UI层级 dump 成功{attempt_label}: {path}")
                            return (True, path, None)
                        else:
                            logger.warning(f"dump 声称成功但文件不存在{attempt_label}: {path}")
                            last_error_info = ('file_missing', f'文件未写入: {path}')
                            return (False, None, last_error_info)

                except subprocess.CalledProcessError as e:
                    rc = e.returncode
                    stderr_text = e.stderr.decode('utf-8', errors='replace').strip() if e.stderr else ''
                    stdout_text = e.stdout.decode('utf-8', errors='replace').strip() if e.stdout else ''
                    logger.warning(f"dump 路径 {path} 失败{attempt_label} (rc={rc}): {stderr_text or stdout_text}")
                    last_error_info = ('called_process_error', rc, stderr_text, stdout_text)
                    continue
                except subprocess.TimeoutExpired:
                    logger.warning(f"dump 路径 {path} 超时{attempt_label}")
                    last_error_info = ('timeout',)
                    continue
            
            return (False, None, last_error_info)
        
        last_error_info = None
        
        # 第一次尝试
        success, dump_path, error = attempt_dump('(第1次)')
        
        if not success and error and error[0] == 'called_process_error':
            rc = error[1]
            if rc == 137 or rc == -9:
                # OOM 被杀死，释放内存后重试
                logger.warning(f"设备 {device_id} 首次 dump 因 OOM 失败(rc={rc})，释放内存后重试...")
                AppDeviceViewSet._free_device_memory(adb_path, device_id, kwargs)
                
                # 等待设备稳定
                import time as _time
                _time.sleep(2)
                
                # 第二次尝试
                logger.info(f"设备 {device_id} 开始第2次 dump 尝试...")
                success, dump_path, error = attempt_dump('(第2次-释放内存后)')
        
        if not success:
            if error and error[0] == 'called_process_error':
                rc = error[1]
                stderr_text = error[2]
                stdout_text = error[3]
                
                if rc == 137 or rc == -9:
                    raise Exception(
                        f'UI层级获取失败(返回码{rc})：uiautomator 进程被设备内存不足杀死，'
                        f'已尝试释放内存但问题仍然存在。'
                        f'建议：手动关闭设备上所有后台应用后重试。'
                    )
                elif 'not found' in stderr_text.lower() or 'not found' in stdout_text.lower():
                    raise Exception(
                        f'UI层级获取失败：设备不支持 uiautomator dump 命令，'
                        f'可能需要 Android 4.1+ 系统版本。'
                    )
                else:
                    raise Exception(
                        f'UI层级获取失败(返回码{rc}): {stderr_text or stdout_text or str(error)}'
                    )
            elif error and error[0] == 'timeout':
                raise Exception('UI层级获取超时(20s)，请检查设备性能')
            elif error and error[0] == 'file_missing':
                raise Exception(f'UI层级获取失败: {error[1]}')
            else:
                raise Exception('UI层级获取失败：所有路径均失败')
        
        # Pull XML 到临时文件
        temp_dir = tempfile.mkdtemp(prefix='testhub_hierarchy_')
        local_xml_path = os.path.join(temp_dir, 'uidump.xml')
        
        try:
            subprocess.run(
                [adb_path, '-s', device_id, 'pull', dump_path, local_xml_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=10,
                **kwargs
            )
            
            # 读取 XML 内容到内存
            with open(local_xml_path, 'r', encoding='utf-8', errors='replace') as f:
                xml_content = f.read()
            
            logger.info(f"adb dump 成功: {device_id}, XML 大小: {len(xml_content)} 字节")
            return xml_content
            
        finally:
            # 清理临时文件
            try:
                os.remove(local_xml_path)
                os.rmdir(temp_dir)
            except Exception:
                pass
            # 清理设备上的临时文件
            try:
                subprocess.run(
                    [adb_path, '-s', device_id, 'shell', 'rm', '-f', dump_path],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=5, **kwargs
                )
            except Exception:
                pass
    
    def _agent_dump_hierarchy(self, device, request, skip_screenshot=False):
        """通过 Agent WebSocket 获取 Agent 代理设备的 UI 层级"""
        try:
            result = self._agent_exec_command(
                device, 'dump_hierarchy', 
                timeout=45,
                skip_screenshot=skip_screenshot
            )
            if not result.get('success'):
                return Response({
                    'code': 500,
                    'msg': f'Agent 层级获取失败: {result.get("message", "未知错误")}',
                    'success': False
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # 解压 gzip 数据（兼容旧版未压缩数据）
            data = _decompress_if_needed(result.get('data', {}))
            screenshot_base64 = data.get('screenshot', '')
            screenshot_format = data.get('screenshot_format', 'png')
            resolution = data.get('resolution', {'width': 0, 'height': 0})
            xml_content = data.get('xml', '')
            
            if not xml_content:
                return Response({
                    'code': 500,
                    'msg': 'Agent 未返回 UI 层级数据',
                    'success': False
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # 解析 XML 提取元素
            elements = []
            try:
                if isinstance(xml_content, bytes):
                    xml_content = xml_content.decode('utf-8', errors='replace')
                xml_content = xml_content.strip()
                if not xml_content.startswith('<'):
                    xml_start = xml_content.find('<?xml')
                    if xml_start == -1:
                        xml_start = xml_content.find('<hierarchy')
                    if xml_start >= 0:
                        xml_content = xml_content[xml_start:]
                
                root = ET.fromstring(xml_content)
                if root.tag == 'hierarchy':
                    for child in root:
                        elements.extend(self._parse_hierarchy_nodes(child))
                else:
                    elements.extend(self._parse_hierarchy_nodes(root))
                    
            except ET.ParseError as pe:
                logger.error(f"Agent XML 解析失败: {pe}")
                return Response({
                    'code': 500,
                    'msg': f'UI层级 XML 解析失败: {str(pe)}',
                    'success': False
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            logger.info(f"Agent 设备 {device.device_id} 层级获取成功，提取 {len(elements)} 个元素")
            
            response_data = {
                'resolution': resolution,
                'elements': elements,
                'total_count': len(elements),
                'via_agent': device.agent_host.hostname if device.agent_host else 'unknown',
            }
            if screenshot_base64:
                if not screenshot_base64.startswith('data:'):
                    mimetype = 'image/jpeg' if screenshot_format == 'jpeg' else 'image/png'
                    screenshot_base64 = f"data:{mimetype};base64,{screenshot_base64}"
                response_data['screenshot'] = screenshot_base64
            
            return Response({
                'code': 0,
                'msg': '层级获取成功 (Agent)',
                'success': True,
                'data': response_data
            })
            
        except ConnectionError as e:
            return Response({
                'code': 503,
                'msg': f'Agent 连接失败: {str(e)}',
                'success': False
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except TimeoutError:
            return Response({
                'code': 500,
                'msg': 'Agent 层级获取超时 (45s)',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"Agent 层级获取失败: {str(e)}", exc_info=True)
            return Response({
                'code': 500,
                'msg': f'Agent 层级获取异常: {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
