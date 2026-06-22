"""Minimal WebSocket client to test AgentConsumer"""
import asyncio

try:
    import websockets
except ImportError:
    print("pip install websockets")
    exit(1)


async def test():
    url = "ws://localhost:8000/ws/app-automation/agent/PC-20231108VKVI-test/"
    print(f"Connecting to {url}")
    
    try:
        async with websockets.connect(url) as ws:
            print(f"Connected!")
            
            # Receive welcome
            msg = await ws.recv()
            print(f"Received: {msg}")
            
            # Send register
            register_msg = '{"type":"register","host_id":"PC-20231108VKVI-test","hostname":"TestPC","ip_address":"192.168.1.100","version":"1.0.0","extra_info":{}}'
            print(f"Sending: {register_msg}")
            await ws.send(register_msg)
            
            # Wait for response
            msg = await ws.recv()
            print(f"Received: {msg}")
            
            msg = await ws.recv()
            print(f"Received: {msg}")
            
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: code={e.code}, reason={e.reason}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

if __name__ == '__main__':
    asyncio.run(test())
