# -*- coding: utf-8 -*-
"""APP设备管理视图"""
import subprocess
import base64
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
import logging
import platform
import tempfile
import os
import xml.etree.ElementTree as ET

from .test_case_views import AppPagination
from ..models import AppDevice
from ..serializers import AppDeviceSerializer
from ..managers.device_manager import DeviceManager

logger = logging.getLogger(__name__)

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


class AppDeviceViewSet(viewsets.ModelViewSet):
    """APP设备管理 ViewSet"""
    queryset = AppDevice.objects.all()
    serializer_class = AppDeviceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'connection_type']
    search_fields = ['device_id', 'name']
    
    @action(detail=False, methods=['get'])
    def discover(self, request):
        """发现ADB设备"""
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
            
            # 返回序列化后的数据库对象
            return Response({
                'success': True,
                'message': f'发现 {len(db_devices)} 个设备',
                'devices': AppDeviceSerializer(db_devices, many=True).data
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
        1. 使用 adb screencap 获取设备截图
        2. 转换为 Base64
        3. 返回 data URL 格式
        """
        device = self.get_object()
        
        if device.status == 'offline':
            return Response({
                'code': 400,
                'msg': '设备离线，无法截图',
                'success': False
            }, status=status.HTTP_400_BAD_REQUEST)
        
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
            
            # 使用 adb screencap 命令截图
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
            
            # 转换为 Base64
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
