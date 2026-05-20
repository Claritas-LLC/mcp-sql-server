import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        try:
            async with client.stream('GET', 'http://localhost:8085/mcp/', headers={'Accept': 'text/event-stream'}) as resp:
                print(f"Status: {resp.status_code}")
                async for line in resp.aiter_lines():
                    if line:
                        print(f"Line: {line}")
                        if "endpoint=" in line:
                            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
