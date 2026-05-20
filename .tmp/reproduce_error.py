import httpx
import asyncio

async def reproduce():
    url = "http://localhost:8085/mcp/"
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "db_primary_sql2019_analyze_db_data_model",
            "arguments": {"database_name": "master", "actor": "stress-actor-01"}
        },
        "id": 1
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url, 
            json=payload, 
            headers={
                "Accept": "application/json",
                "mcp-session-id": "stress-test-session"
            }
        )
        print(f"Status: {resp.status_code}")
        print(f"Body: {resp.text}")

if __name__ == "__main__":
    asyncio.run(reproduce())
