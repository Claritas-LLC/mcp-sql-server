import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        try:
            async with client.stream('GET', 'http://localhost:8085/mcp/sse', headers={'Accept': 'text/event-stream'}) as resp:
                print(f"Status: {resp.status_code}")
                async for line in resp.aiter_lines():
                    print(f"RAW: {line}")
                    if line.startswith("event: endpoint"):
                        pass
                    if line.startswith("data: "):
                        endpoint = line[6:]
                        print(f"Endpoint: {endpoint}")
                        return endpoint
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    endpoint = asyncio.run(test())
    if endpoint:
        print(f"GOT ENDPOINT: {endpoint}")
