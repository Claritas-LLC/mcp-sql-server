import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get('http://localhost:8085/mcp/')
            print(f"Status: {resp.status_code}")
            print(f"Headers: {resp.headers}")
            print(f"Body: {resp.text[:500]}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
