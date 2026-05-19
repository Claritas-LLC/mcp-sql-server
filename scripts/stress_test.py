import asyncio
import httpx
import time
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Configuration
BASE_URL = "http://localhost:8085"
TOOL_NAME = "db_primary_sql2019_analyze_db_data_model"
TOOL_ARGS = {"database_name": "master"}
INCREMENT_INTERVAL_SEC = 300  # 5 minutes
TOTAL_DURATION_SEC = 1200     # 20 minutes
POLL_INTERVAL_SEC = 60        # 1 minute for diagnostics
CALL_INTERVAL_SEC = 2         # Each session calls every 2s

# Metrics
stats = {
    "successful_calls": 0,
    "failed_calls": 0,
    "start_time": time.time(),
    "history": []
}

async def mcp_tool_call(client, actor_id, session_id):
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {
            "name": TOOL_NAME,
            "arguments": {**TOOL_ARGS, "actor": actor_id}
        }
    }
    try:
        resp = await client.post(
            f"{BASE_URL}/mcp/",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id
            },
            timeout=30.0
        )
        if resp.status_code == 200:
            stats["successful_calls"] += 1
            return True
        else:
            stats["failed_calls"] += 1
            print(f"[{actor_id}] Failed with {resp.status_code}: {resp.text[:100]}")
            return False
    except Exception as e:
        stats["failed_calls"] += 1
        print(f"[{actor_id}] Error: {str(e)}")
        return False

async def session_worker(actor_id):
    print(f"Starting session worker: {actor_id}")
    async with httpx.AsyncClient() as client:
        # 1. Handshake to get a session
        try:
            resp = await client.get(
                f"{BASE_URL}/mcp/",
                headers={"Accept": "text/event-stream"},
                timeout=10.0
            )
            session_id = resp.headers.get("mcp-session-id")
            if not session_id:
                print(f"[{actor_id}] Failed to get session ID from handshake")
                return
            print(f"[{actor_id}] Session established: {session_id}")
        except Exception as e:
            print(f"[{actor_id}] Handshake error: {e}")
            return

        # 2. Worker loop
        while True:
            # We need to pass the session_id to mcp_tool_call
            await mcp_tool_call(client, actor_id, session_id)
            await asyncio.sleep(CALL_INTERVAL_SEC)

async def monitor_diagnostics():
    async with httpx.AsyncClient() as client:
        while True:
            try:
                resp = await client.get(f"{BASE_URL}/diagnostics/pool")
                if resp.status_code == 200:
                    pool_data = resp.json()
                    elapsed = time.time() - stats["start_time"]
                    
                    # Calculate TPS since last monitor
                    # (Quick and dirty for this script)
                    snapshot = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "elapsed_sec": int(elapsed),
                        "successful": stats["successful_calls"],
                        "failed": stats["failed_calls"],
                        "pool": pool_data
                    }
                    stats["history"].append(snapshot)
                    print(f"[{int(elapsed)}s] Success: {stats['successful_calls']}, Fail: {stats['failed_calls']}, Pool: {json.dumps(pool_data)}")
            except Exception as e:
                print(f"Monitor error: {e}")
            await asyncio.sleep(POLL_INTERVAL_SEC)

async def main():
    print(f"Starting Stress Test at {datetime.now(timezone.utc).isoformat()}")
    print(f"Target: {BASE_URL}, Tool: {TOOL_NAME}")
    
    current_sessions = []
    monitor_task = asyncio.create_task(monitor_diagnostics())
    
    start_time = time.time()
    
    try:
        # Initial 10 sessions
        for i in range(10):
            actor_id = f"stress-actor-{len(current_sessions) + 1:02d}"
            current_sessions.append(asyncio.create_task(session_worker(actor_id)))
        
        while True:
            elapsed = time.time() - start_time
            if elapsed >= TOTAL_DURATION_SEC:
                break
            
            # Increment every 5 minutes (300s)
            target_count = 10 + (int(elapsed) // INCREMENT_INTERVAL_SEC) * 5
            while len(current_sessions) < target_count:
                actor_id = f"stress-actor-{len(current_sessions) + 1:02d}"
                current_sessions.append(asyncio.create_task(session_worker(actor_id)))
            
            await asyncio.sleep(10)
            
    finally:
        print("Stopping test...")
        for t in current_sessions:
            t.cancel()
        monitor_task.cancel()
        
        # Save results
        results_path = Path("testing/artifacts/stress_test_results.json")
        results_path.parent.mkdir(parents=True, exist_ok=True)
        with open(results_path, "w") as f:
            json.dump(stats, f, indent=2)
        print(f"Results saved to {results_path}")

if __name__ == "__main__":
    asyncio.run(main())
