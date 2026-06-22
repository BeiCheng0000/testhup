#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TestHub ADB Agent - 远程设备代理

功能：
1. 连接 TestHub 服务器 WebSocket
2. 发现本地 ADB 设备 (USB + 模拟器)
3. 为 USB 设备启用 TCP 调试模式 (adb tcpip 5555)
4. 定期同步设备列表到服务器
5. 处理服务器命令 (截图, UI层级, 等)

使用方式:
  python adb_agent.py --server ws://192.168.1.100:8000 [--host-id mypc]

参数:
  --server     TestHub 服务器 WebSocket 地址 (必需)
  --host-id    主机 ID（可选，不指定则自动生成）
  --adb        ADB 可执行文件路径 (默认: adb)
  --tcp-port   设备 TCP 调试端口 (默认: 5555)
  --interval   设备同步间隔秒数 (默认: 30)
  --heartbeat  心跳间隔秒数 (默认: 15)
  --log-level  日志级别 (默认: INFO)
"""

import asyncio
import base64
import gzip
import json
import logging
import os
import platform
import re
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

# 可选：Pillow 用于 PNG→JPEG 转换（大幅减少截图传输体积）
try:
    from io import BytesIO
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import websockets
except ImportError:
    print("=" * 60)
    print("错误: 缺少 websockets 库")
    print("请安装: pip install websockets")
    print("=" * 60)
    sys.exit(1)

# ---- 日志配置 ----
logger = logging.getLogger("adb_agent")


def setup_logging(level="INFO"):
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))


# ---- 数据压缩工具 ----


def compress_data(data: bytes) -> str:
    """对二进制数据执行 gzip 压缩并返回 base64 字符串"""
    compressed = gzip.compress(data, compresslevel=6)
    return base64.b64encode(compressed).decode('utf-8')


def compress_text(text: str) -> str:
    """对文本执行 gzip 压缩并返回 base64 字符串"""
    return compress_data(text.encode('utf-8'))


# ---- ADB 工具函数 ----

class ADBHelper:
    """ADB 命令执行辅助类"""
    
    def __init__(self, adb_path="adb"):
        self.adb_path = adb_path
        self._subprocess_kwargs = {}
        if platform.system() == 'Windows':
            self._subprocess_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    
    def _run(self, args, timeout=10, binary=False) -> subprocess.CompletedProcess:
        """执行 ADB 命令
        
        Args:
            args: ADB 命令参数列表
            timeout: 超时秒数
            binary: True=返回 bytes（用于截图等二进制输出），False=返回 str
        """
        cmd = [self.adb_path] + args
        if binary:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=False,
                timeout=timeout,
                **self._subprocess_kwargs
            )
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            **self._subprocess_kwargs
        )
    
    def verify(self) -> bool:
        """验证 ADB 是否可用"""
        try:
            result = self._run(['version'], timeout=5)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"ADB 验证失败: {e}")
            return False
    
    def list_devices(self) -> List[Dict]:
        """发现本地 ADB 设备"""
        try:
            result = self._run(['devices', '-l'], timeout=10)
            if result.returncode != 0:
                logger.error(f"adb devices 失败: {result.stderr}")
                return []
            
            devices = []
            lines = result.stdout.strip().split('\n')[1:]
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('*'):
                    continue
                
                parts = line.split()
                if len(parts) < 2:
                    continue
                
                device_id = parts[0]
                adb_status = parts[1]
                status = 'online' if adb_status == 'device' else 'offline'
                
                dev_info = {
                    'device_id': device_id,
                    'status': status,
                    'name': '',
                    'android_version': '',
                    'connection_type': 'agent_device',
                    'ip_address': '',
                    'tcp_port': 5555,
                    'device_specs': {},
                }
                
                # 判断连接类型
                if ':' in device_id:
                    parts_id = device_id.split(':')
                    dev_info['ip_address'] = parts_id[0]
                    dev_info['tcp_port'] = int(parts_id[1]) if len(parts_id) > 1 else 5555
                    dev_info['connection_type'] = 'agent_device'
                elif device_id.startswith('emulator-'):
                    dev_info['ip_address'] = '127.0.0.1'
                    dev_info['tcp_port'] = int(device_id.split('-')[1]) if '-' in device_id else 5554
                else:
                    dev_info['connection_type'] = 'real_device'
                
                # 获取设备详细信息
                if status == 'online':
                    try:
                        dev_info.update(self.get_device_info(device_id))
                    except Exception:
                        pass
                
                devices.append(dev_info)
            
            logger.info(f"发现 {len(devices)} 个设备")
            return devices
            
        except subprocess.TimeoutExpired:
            logger.error("adb devices 超时")
            return []
        except Exception as e:
            logger.error(f"获取设备列表失败: {e}")
            return []
    
    def get_device_info(self, device_id: str) -> Dict:
        """获取设备型号和 Android 版本"""
        info = {}
        try:
            result = self._run(['-s', device_id, 'shell', 'getprop', 'ro.product.model'], timeout=5)
            if result.returncode == 0:
                info['name'] = result.stdout.strip()
        except Exception:
            pass
        
        try:
            result = self._run(['-s', device_id, 'shell', 'getprop', 'ro.build.version.release'], timeout=5)
            if result.returncode == 0:
                info['android_version'] = result.stdout.strip()
        except Exception:
            pass
        
        return info
    
    def enable_tcp_debug(self, device_id: str, tcp_port: int = 5555) -> bool:
        """为 USB 设备启用 TCP 调试模式"""
        if ':' in device_id or device_id.startswith('emulator-'):
            return False  # 已经是网络设备
        
        try:
            logger.info(f"为设备 {device_id} 启用 TCP 调试: port={tcp_port}")
            result = self._run(['-s', device_id, 'tcpip', str(tcp_port)], timeout=15)
            output = (result.stdout + result.stderr).strip()
            
            if result.returncode == 0 and 'restarting' in output.lower():
                logger.info(f"设备 {device_id} TCP 调试已启用")
                time.sleep(2)  # 等待 ADB 重启
                return True
            else:
                logger.warning(f"tcpip 输出: {output}")
                return result.returncode == 0
        except Exception as e:
            logger.error(f"启用 TCP 调试失败: {e}")
            return False
    
    def get_device_ip(self, device_id: str) -> str:
        """获取设备 WiFi IP 地址"""
        try:
            result = self._run(
                ['-s', device_id, 'shell', 'ip', '-f', 'inet', 'addr', 'show', 'wlan0'],
                timeout=5
            )
            match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', result.stdout)
            if match:
                return match.group(1)
        except Exception:
            pass
        
        try:
            result = self._run(
                ['-s', device_id, 'shell', 'getprop', 'dhcp.wlan0.ipaddress'],
                timeout=5
            )
            ip = result.stdout.strip()
            if ip and ip != '0.0.0.0' and not ip.startswith('192.0.0.'):
                return ip
        except Exception:
            pass
        
        return ''
    
    def screenshot(self, device_id: str) -> Optional[bytes]:
        """获取设备截图 (PNG 二进制)"""
        try:
            result = self._run(['-s', device_id, 'exec-out', 'screencap', '-p'], timeout=10, binary=True)
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception as e:
            logger.error(f"截图失败: {e}")
        return None
    
    def dump_hierarchy(self, device_id: str) -> Optional[str]:
        """获取 UI 层级 XML"""
        dump_path = '/data/local/tmp/testhub_agent_uidump.xml'
        try:
            # 清理旧文件
            self._run(['-s', device_id, 'shell', 'rm', '-f', dump_path], timeout=5)
            
            # 执行 dump
            result = self._run(
                ['-s', device_id, 'shell', 'uiautomator', 'dump', dump_path],
                timeout=20
            )
            
            stdout_text = result.stdout.strip()
            if 'dumped to' not in stdout_text.lower() and 'UI hierchary' not in stdout_text:
                logger.warning(f"dump 可能失败: {stdout_text}")
            
            # Pull XML
            import tempfile
            tmp_dir = tempfile.mkdtemp(prefix='agent_hierarchy_')
            local_path = os.path.join(tmp_dir, 'uidump.xml')
            
            try:
                pull_result = self._run(
                    ['-s', device_id, 'pull', dump_path, local_path],
                    timeout=10
                )
                if pull_result.returncode == 0:
                    with open(local_path, 'r', encoding='utf-8', errors='replace') as f:
                        return f.read()
            finally:
                try:
                    os.remove(local_path)
                    os.rmdir(tmp_dir)
                except Exception:
                    pass
                self._run(['-s', device_id, 'shell', 'rm', '-f', dump_path], timeout=5)
                    
        except Exception as e:
            logger.error(f"dump hierarchy 失败: {e}")
        return None
    
    def get_resolution(self, device_id: str) -> Dict:
        """获取设备屏幕分辨率"""
        try:
            result = self._run(['-s', device_id, 'shell', 'wm', 'size'], timeout=5)
            match = re.search(r'(\d+)\s*x\s*(\d+)', result.stdout)
            if match:
                return {'width': int(match.group(1)), 'height': int(match.group(2))}
        except Exception:
            pass
        return {'width': 0, 'height': 0}


# ---- Agent 主逻辑 ----

class ADBAgent:
    """TestHub ADB Agent 客户端"""
    
    def __init__(self, server_url: str, host_id: str = "", adb_path: str = "adb",
                 tcp_port: int = 5555, sync_interval: int = 30, heartbeat_interval: int = 15):
        self.server_url = server_url
        self.host_id = host_id or self._generate_host_id()
        self.adb = ADBHelper(adb_path)
        self.tcp_port = tcp_port
        self.sync_interval = sync_interval
        self.heartbeat_interval = heartbeat_interval
        
        self._ws = None
        self._running = False
        self._registered = False
        self._tasks: List[asyncio.Task] = []
        self._last_devices: List[Dict] = []
        self._tcp_enabled_device_ids: set = set()  # 已启用 TCP 的设备，避免重复 tcpip
        self._hostname = socket.gethostname()
        self._local_ip = self._get_local_ip()
    
    @staticmethod
    def _generate_host_id() -> str:
        """生成主机 ID"""
        return f"{socket.gethostname()}-{str(uuid.uuid4())[:8]}"
    
    @staticmethod
    def _get_local_ip() -> str:
        """获取本机局域网 IP"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return '127.0.0.1'
    
    async def run(self):
        """主入口"""
        self._running = True
        
        while self._running:
            try:
                await self._connect_and_serve()
            except websockets.ConnectionClosed as e:
                logger.warning(f"连接断开: {e}, 5秒后重连...")
            except (ConnectionRefusedError, OSError) as e:
                logger.error(f"连接失败: {e}, 10秒后重连...")
            except Exception as e:
                logger.error(f"未预期错误: {e}", exc_info=True)
                await asyncio.sleep(5)
            
            if self._running:
                await asyncio.sleep(5)
    
    async def _connect_and_serve(self):
        """连接服务器并进行消息循环"""
        ws_url = f"{self.server_url}/ws/app-automation/agent/{self.host_id}/"
        logger.info(f"连接服务器: {ws_url}")
        
        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as ws:
            self._ws = ws
            self._registered = False
            
            # 启动后台任务
            self._tasks = [
                asyncio.create_task(self._heartbeat_loop()),
                asyncio.create_task(self._device_sync_loop()),
            ]
            
            try:
                async for message in ws:
                    await self._handle_message(json.loads(message))
            finally:
                for task in self._tasks:
                    task.cancel()
                self._tasks = []
                self._ws = None
    
    async def _handle_message(self, msg: dict):
        """处理服务器消息"""
        msg_type = msg.get('type', '')
        
        if msg_type == 'welcome':
            await self._send_register()
        elif msg_type == 'registered':
            self._registered = True
            logger.info(f"注册成功: {msg.get('message', '')}")
            # 立即同步一次设备
            await self._sync_devices()
        elif msg_type == 'sync_devices':
            logger.info("收到服务器同步请求")
            await self._sync_devices()
        elif msg_type == 'exec_command':
            await self._handle_command(msg)
        elif msg_type == 'pong':
            pass  # 心跳响应
        elif msg_type == 'error':
            logger.error(f"服务器错误: {msg.get('message', '')}")
        else:
            logger.debug(f"未知消息类型: {msg_type}")
    
    async def _send_register(self):
        """发送注册消息"""
        msg = {
            'type': 'register',
            'host_id': self.host_id,
            'hostname': self._hostname,
            'ip_address': self._local_ip,
            'version': '1.0.0',
            'extra_info': {
                'os': platform.system(),
                'os_version': platform.version(),
                'python_version': sys.version.split()[0],
                'machine': platform.machine(),
            }
        }
        await self._send(msg)
        logger.info(f"已发送注册: host_id={self.host_id}, hostname={self._hostname}, ip={self._local_ip}")
    
    async def _send(self, msg: dict):
        """发送消息到服务器"""
        if self._ws:
            await self._ws.send(json.dumps(msg, ensure_ascii=False))
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        while self._running:
            try:
                await self._send({'type': 'ping', 'timestamp': datetime.now().isoformat()})
            except Exception:
                pass
            await asyncio.sleep(self.heartbeat_interval)
    
    async def _device_sync_loop(self):
        """定时设备同步循环"""
        await asyncio.sleep(2)  # 初始等待
        
        while self._running:
            try:
                await self._sync_devices()
            except Exception as e:
                logger.error(f"设备同步失败: {e}")
            await asyncio.sleep(self.sync_interval)
    
    async def _sync_devices(self):
        """发现并同步本地设备"""
        if not self._registered:
            return
        
        devices = self.adb.list_devices()
        self._last_devices = devices
        
        # 为 USB 真机设备启用 TCP 调试（每个设备仅执行一次）
        for dev in devices:
            device_id = dev['device_id']
            if dev['connection_type'] == 'real_device' and dev['status'] == 'online':
                # 只对尚未启用 TCP 的 USB 设备执行
                if device_id not in self._tcp_enabled_device_ids:
                    # 先获取设备 IP（tcpip 之前 USB 连接稳定）
                    device_ip = self.adb.get_device_ip(device_id)
                    if device_ip:
                        success = self.adb.enable_tcp_debug(device_id, self.tcp_port)
                        if success:
                            self._tcp_enabled_device_ids.add(device_id)
                            dev['adb_ip'] = device_ip
                            dev['tcp_port'] = self.tcp_port
                            dev['ip_address'] = device_ip
                            logger.info(f"设备 {device_id} TCP 调试地址: {device_ip}:{self.tcp_port}")
                        else:
                            logger.warning(f"设备 {device_id} TCP 调试启用失败")
                    else:
                        logger.warning(f"设备 {device_id} 无法获取 WiFi IP，保持 USB 模式")
                # 不再回退到主机 IP
            elif dev['connection_type'] == 'agent_device' and ':' in device_id:
                dev['adb_ip'] = device_id.split(':')[0]
            elif device_id.startswith('emulator-'):
                dev['adb_ip'] = '127.0.0.1'
        
        # 发送到服务器
        msg = {
            'type': 'device_sync',
            'devices': devices,
            'timestamp': datetime.now().isoformat(),
        }
        await self._send(msg)
        
        online_count = sum(1 for d in devices if d['status'] == 'online')
        logger.info(f"设备同步完成: {online_count}/{len(devices)} 在线")
    
    async def _handle_command(self, msg: dict):
        """处理服务器命令"""
        request_id = msg.get('request_id', '')
        command_type = msg.get('command_type', '')
        device_id = msg.get('device_id', '')
        
        logger.info(f"执行命令: {command_type} on {device_id} (request_id={request_id})")
        
        try:
            if command_type == 'screenshot':
                result = await self._cmd_screenshot(device_id)
            elif command_type == 'dump_hierarchy':
                result = await self._cmd_dump_hierarchy(device_id, msg)
            else:
                result = {'success': False, 'message': f'不支持的命令: {command_type}'}
        except Exception as e:
            result = {'success': False, 'message': str(e)}
        
        result['request_id'] = request_id
        result['type'] = 'command_result'
        await self._send(result)
    
    async def _cmd_screenshot(self, device_id: str) -> dict:
        """执行截图命令（带压缩优化）"""
        png_data = self.adb.screenshot(device_id)
        if png_data is None:
            return {'success': False, 'message': '截图返回空数据'}
        
        # 策略1: Pillow 可用 → PNG→JPEG 转换（体积减少 80-90%）
        if HAS_PIL:
            try:
                img = Image.open(BytesIO(png_data))
                buf = BytesIO()
                img.convert('RGB').save(buf, format='JPEG', quality=70, optimize=True)
                jpeg_data = buf.getvalue()
                b64 = base64.b64encode(jpeg_data).decode('utf-8')
                logger.info(
                    f"截图 JPEG 压缩: {len(png_data)} → {len(jpeg_data)} bytes "
                    f"({len(jpeg_data)/max(len(png_data),1)*100:.0f}%), "
                    f"device={device_id}"
                )
                return {
                    'success': True,
                    'data': {
                        'content': f'data:image/jpeg;base64,{b64}',
                        'format': 'jpeg',
                        'compressed': False,  # JPEG 本身已压缩
                    }
                }
            except Exception as e:
                logger.warning(f"JPEG 转换失败，回退 PNG: {e}")
        
        # 策略2: gzip 压缩 PNG（体积减少 10-20%）
        compressed_b64 = compress_data(png_data)
        logger.info(
            f"截图 gzip 压缩: {len(png_data)} → {len(compressed_b64)} chars base64, "
            f"device={device_id}"
        )
        return {
            'success': True,
            'data': {
                'content': f'data:image/png;base64,{compressed_b64}',
                'format': 'png',
                'compressed': 'gzip',  # 服务端需解压
            }
        }
    
    async def _cmd_dump_hierarchy(self, device_id: str, msg: dict = None) -> dict:
        """执行 UI 层级获取命令（并行执行 + 压缩优化）
        
        额外参数（通过 msg 传入）：
        - skip_screenshot: 跳过截图（前端已有截图时使用）
        """
        skip_screenshot = (msg or {}).get('skip_screenshot', False)
        loop = asyncio.get_event_loop()
        
        # ===== 并行执行：dump_hierarchy + (可选)screenshot + resolution 同时进行 =====
        # Python 3.13: asyncio.create_task() 不接受 Future，run_in_executor 返回的 Future
        # 本身就是 awaitable，直接存入 dict 后用 asyncio.gather 并行等待即可
        
        futures = {}
        
        # dump_hierarchy 必须执行
        futures['dump'] = loop.run_in_executor(None, self.adb.dump_hierarchy, device_id)
        
        # resolution 并行获取
        futures['resolution'] = loop.run_in_executor(None, self.adb.get_resolution, device_id)
        
        # screenshot 可选并行
        if not skip_screenshot:
            futures['screenshot'] = loop.run_in_executor(None, self.adb.screenshot, device_id)
        
        # 并行等待所有 Future 完成
        xml_content = await futures['dump']
        resolution = await futures['resolution']
        png_data = await futures['screenshot'] if 'screenshot' in futures else None
        
        if not xml_content:
            return {'success': False, 'message': 'UI层级获取失败'}
        
        # 压缩 XML（文本压缩率 80-95%，极大减少 WebSocket 传输时间）
        compressed_xml = compress_text(xml_content)
        logger.info(
            f"XML gzip 压缩: {len(xml_content)} → {len(compressed_xml)} chars base64, "
            f"device={device_id}"
        )
        
        # 处理截图
        screenshot_b64 = ''
        screenshot_format = 'png'
        screenshot_compressed = False
        
        if png_data is not None:
            if HAS_PIL:
                try:
                    img = Image.open(BytesIO(png_data))
                    buf = BytesIO()
                    img.convert('RGB').save(buf, format='JPEG', quality=70, optimize=True)
                    jpeg_data = buf.getvalue()
                    screenshot_b64 = base64.b64encode(jpeg_data).decode('utf-8')
                    screenshot_format = 'jpeg'
                    logger.info(
                        f"截图 JPEG 压缩: {len(png_data)} → {len(jpeg_data)} bytes, "
                        f"device={device_id}"
                    )
                except Exception as e:
                    logger.warning(f"JPEG 转换失败，回退 gzip PNG: {e}")
                    screenshot_b64 = compress_data(png_data)
                    screenshot_format = 'png'
                    screenshot_compressed = 'gzip'
            else:
                screenshot_b64 = base64.b64encode(png_data).decode('utf-8')
        
        return {
            'success': True,
            'data': {
                'xml': compressed_xml,
                'xml_compressed': 'gzip',
                'resolution': resolution,
                'screenshot': screenshot_b64,
                'screenshot_format': screenshot_format,
                'screenshot_compressed': screenshot_compressed,
            }
        }
    
    def stop(self):
        """停止 Agent"""
        self._running = False


# ---- 主入口 ----

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='TestHub ADB Agent - 远程设备代理',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python adb_agent.py --server ws://192.168.1.100:8000
  python adb_agent.py --server ws://testhub.example.com --host-id my-lab-pc
  python adb_agent.py --server ws://localhost:8000 --adb "D:/platform-tools/adb.exe"
        """
    )
    parser.add_argument('--server', required=True, 
                        help='TestHub 服务器 WebSocket 地址 (如 ws://192.168.1.100:8000)')
    parser.add_argument('--host-id', default='', 
                        help='主机 ID（默认自动生成）')
    parser.add_argument('--adb', default='adb', 
                        help='ADB 路径 (默认: adb)')
    parser.add_argument('--tcp-port', type=int, default=5555, 
                        help='设备 TCP 调试端口 (默认: 5555)')
    parser.add_argument('--interval', type=int, default=30, 
                        help='设备同步间隔秒数 (默认: 30)')
    parser.add_argument('--heartbeat', type=int, default=15, 
                        help='心跳间隔秒数 (默认: 15)')
    parser.add_argument('--log-level', default='INFO', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='日志级别 (默认: INFO)')
    
    args = parser.parse_args()
    
    setup_logging(args.log_level)
    
    logger.info("=" * 50)
    logger.info("TestHub ADB Agent v1.0.0")
    logger.info(f"服务器: {args.server}")
    logger.info(f"主机名: {socket.gethostname()}")
    logger.info(f"主机 IP: {ADBAgent._get_local_ip()}")
    logger.info(f"ADB 路径: {args.adb}")
    logger.info(f"TCP 调试端口: {args.tcp_port}")
    logger.info("=" * 50)
    
    # 验证 ADB
    adb_helper = ADBHelper(args.adb)
    if not adb_helper.verify():
        logger.error("ADB 不可用，请检查 ADB 路径")
        sys.exit(1)
    logger.info("ADB 验证成功")
    
    agent = ADBAgent(
        server_url=args.server.rstrip('/'),
        host_id=args.host_id,
        adb_path=args.adb,
        tcp_port=args.tcp_port,
        sync_interval=args.interval,
        heartbeat_interval=args.heartbeat,
    )
    
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在退出...")
        agent.stop()
    except Exception as e:
        logger.error(f"Agent 异常退出: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
