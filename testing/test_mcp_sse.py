#!/usr/bin/env python3
"""
Test script to verify MCP server SSE connectivity and tool availability.
"""

import asyncio
import json
import httpx
from typing import Any

async def test_mcp_sse_server():
    """Test MCP server SSE connectivity and list available tools."""
    
    print("Testing MCP server SSE connectivity...")
    
    base_url = "http://localhost:8085"
    headers = {
        "Accept": "text/event-stream, application/json",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Try to list tools via HTTP POST
            response = await client.post(
                f"{base_url}/mcp",
                headers=headers,
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}
            )
            
            print(f"POST /mcp (tools/list) response: {response.status_code}")
            
            if response.status_code == 200:
                # For SSE, we need to read the stream
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        try:
                            data = json.loads(line[5:])
                            if data.get("id") == 1:
                                print(f"✓ Tools list received: {json.dumps(data, indent=2)}")
                                
                                # Now try to call a tool
                                await call_tool_in_stream(client, base_url, headers)
                                
                        except json.JSONDecodeError:
                            print(f"Could not decode JSON: {line}")
            else:
                print(f"Response text: {response.text}")
                
    except Exception as e:
        print(f"✗ SSE server test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

async def call_tool_in_stream(client, base_url, headers):
    """Call a tool within the same SSE stream."""
    print("\nCalling tool db_sql2019_analyze_table_health...")
    
    tool_call_data = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "db_sql2019_analyze_table_health",
            "arguments": {
                "database_name": "USGISPRO_800",
                "schema": "dbo",
                "table_name": "Account"
            }
        },
        "id": 2
    }
    
    response = await client.post(
        f"{base_url}/mcp",
        headers=headers,
        json=tool_call_data
    )
    
    print(f"POST /mcp (tool call) response: {response.status_code}")
    
    if response.status_code == 200:
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                try:
                    data = json.loads(line[5:])
                    if data.get("id") == 2:
                        print(f"✓ Tool call result received: {json.dumps(data, indent=2)}")
                except json.JSONDecodeError:
                    print(f"Could not decode JSON: {line}")
    else:
        print(f"Response text: {response.text}")

if __name__ == "__main__":
    print("🧪 Testing MCP Server SSE Endpoint")
    print("=" * 50)
    
    success = asyncio.run(test_mcp_sse_server())
    
    if success:
        print("\n🎉 SSE endpoint tests completed!")
    else:
        print("\n❌ SSE endpoint tests failed!")
        exit(1)
