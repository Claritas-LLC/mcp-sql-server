#!/usr/bin/env python3
"""
Test script to verify MCP server HTTP connectivity and tool availability.
"""

import asyncio
import json
import httpx
from typing import Any

async def test_mcp_http_server():
    """Test MCP server HTTP connectivity and list available tools."""
    
    print("Testing MCP server HTTP connectivity...")
    
    base_url = "http://localhost:8085"
    
    try:
        # Test basic connectivity
        async with httpx.AsyncClient() as client:
            # Try to access the MCP endpoint
            response = await client.get(f"{base_url}/mcp")
            print(f"GET /mcp response: {response.status_code} - {response.text}")
            
            # Try to access the SSE endpoint
            response = await client.get(f"{base_url}/sse")
            print(f"GET /sse response: {response.status_code} - {response.text[:200]}...")
            
            # Try to access the root endpoint
            response = await client.get(f"{base_url}/")
            print(f"GET / response: {response.status_code} - {response.text}")
            
            # Try to list tools via HTTP POST (common MCP pattern)
            try:
                response = await client.post(
                    f"{base_url}/mcp",
                    json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}
                )
                print(f"POST /mcp (tools/list) response: {response.status_code}")
                if response.status_code == 200:
                    print(f"Tools response: {response.json()}")
                else:
                    print(f"Response text: {response.text}")
            except Exception as e:
                print(f"POST /mcp failed: {e}")
            
            # Try SSE endpoint for tools
            try:
                response = await client.post(
                    f"{base_url}/sse",
                    json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}
                )
                print(f"POST /sse (tools/list) response: {response.status_code}")
                if response.status_code == 200:
                    print(f"Tools response: {response.json()}")
                else:
                    print(f"Response text: {response.text}")
            except Exception as e:
                print(f"POST /sse failed: {e}")
                
    except Exception as e:
        print(f"✗ HTTP server test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

async def test_direct_tool_call():
    """Test direct tool call via HTTP."""
    
    print("\nTesting direct tool call via HTTP...")
    
    base_url = "http://localhost:8085"
    
    try:
        async with httpx.AsyncClient() as client:
            # Try to call the specific tool
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
            
            try:
                response = await client.post(
                    f"{base_url}/mcp",
                    json=tool_call_data
                )
                print(f"POST /mcp (tool call) response: {response.status_code}")
                if response.status_code == 200:
                    result = response.json()
                    print(f"Tool call result: {json.dumps(result, indent=2)}")
                else:
                    print(f"Response text: {response.text}")
            except Exception as e:
                print(f"Tool call via /mcp failed: {e}")
            
            # Try via SSE endpoint
            try:
                response = await client.post(
                    f"{base_url}/sse",
                    json=tool_call_data
                )
                print(f"POST /sse (tool call) response: {response.status_code}")
                if response.status_code == 200:
                    result = response.json()
                    print(f"Tool call result: {json.dumps(result, indent=2)}")
                else:
                    print(f"Response text: {response.text}")
            except Exception as e:
                print(f"Tool call via /sse failed: {e}")
                
    except Exception as e:
        print(f"✗ Direct tool call test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    print("🧪 Testing MCP Server HTTP Endpoints")
    print("=" * 50)
    
    success1 = asyncio.run(test_mcp_http_server())
    success2 = asyncio.run(test_direct_tool_call())
    
    if success1 and success2:
        print("\n🎉 HTTP endpoint tests completed!")
    else:
        print("\n❌ Some HTTP endpoint tests failed!")
        exit(1)
