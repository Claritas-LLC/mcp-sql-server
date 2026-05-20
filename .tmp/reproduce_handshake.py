import httpx
import asyncio

async def reproduce():
    base_url = "http://localhost:8085/mcp/"
    
    async with httpx.AsyncClient() as client:
        # 1. GET to get a session
        print("--- Step 1: GET to get session ---")
        # In stateless mode, GET might just return a session header
        resp = await client.get(base_url, headers={"Accept": "text/event-stream"})
        print(f"GET Status: {resp.status_code}")
        session_id = resp.headers.get("mcp-session-id")
        print(f"Session ID: {session_id}")
        
        if not session_id:
            print("No session ID found in headers")
            return

        # 2. POST with that session
        print("\n--- Step 2: POST with session ---")
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "db_primary_sql2019_analyze_db_data_model",
                "arguments": {"database_name": "master", "actor": "stress-actor-01"}
            },
            "id": 1
        }
        
        resp = await client.post(
            base_url, 
            json=payload, 
            headers={
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id
            }
        )
        print(f"POST Status: {resp.status_code}")
        print(f"POST Body: {resp.text}")

if __name__ == "__main__":
    asyncio.run(reproduce())
