"""Test database_sync_to_async with AgentConsumer pattern"""
import asyncio
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from channels.db import database_sync_to_async
from apps.app_automation.models import AgentHost


class TestConsumer:
    def __init__(self):
        self.host_id = "test-host-001"
        self.agent_info = {
            "hostname": "TestPC",
            "ip_address": "192.168.1.100",
            "version": "1.0.0",
            "extra_info": {},
        }

    @staticmethod
    def _db_register_host(host_id, agent_info):
        """(sync) 创建或更新 AgentHost"""
        from apps.app_automation.models import AgentHost
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
    def _db_get_agent_host(host_id):
        from apps.app_automation.models import AgentHost
        return AgentHost.objects.filter(host_id=host_id).first()

    async def test_register(self):
        print("1. Testing database_sync_to_async with static method...")
        try:
            host, created = await database_sync_to_async(
                self._db_register_host
            )(self.host_id, self.agent_info)
            print(f"   OK: host={host}, created={created}, hostname={host.hostname}")
        except Exception as e:
            print(f"   FAILED: {type(e).__name__}: {e}")

    async def test_query(self):
        print("2. Testing query via database_sync_to_async...")
        try:
            host = await database_sync_to_async(self._db_get_agent_host)(self.host_id)
            print(f"   OK: host={host}, hostname={host.hostname if host else 'None'}")
        except Exception as e:
            print(f"   FAILED: {type(e).__name__}: {e}")

    async def test_direct_call(self):
        print("3. Testing sync static method direct call from async...")
        try:
            host, created = self._db_register_host(self.host_id + "-direct", self.agent_info)
            print(f"   OK: host={host}, created={created}, hostname={host.hostname}")
        except Exception as e:
            print(f"   FAILED: {type(e).__name__}: {e}")


async def main():
    t = TestConsumer()
    await t.test_register()
    await t.test_query()
    await t.test_direct_call()
    print("\nAll tests done!")

if __name__ == '__main__':
    asyncio.run(main())
