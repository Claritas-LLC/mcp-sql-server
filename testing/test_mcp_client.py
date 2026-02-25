#!/usr/bin/env python3
"""
Test script to verify MCP server connectivity and tool availability.
"""

import asyncio
import json
from typing import Any

# Try to import the MCP client
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    print("✓ Successfully imported MCP client modules")
except ImportError as e:
    print(f"✗ Failed to import MCP client modules: {e}")
    print("Please install mcp package: pip install mcp")
    exit(1)

async def test_mcp_server():
    """Test MCP server connectivity and list available tools."""
    
    print("Testing MCP server connectivity...")
    
    # Server connection parameters
    server_params = StdioServerParameters(
        command="python",
        args=["server.py"],
        env=None
    )
    
    try:
        # Create client session
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize the session
                await session.initialize()
                print("✓ Successfully connected to MCP server")
                
                # List available tools
                tools = await session.list_tools()
                print(f"✓ Found {len(tools)} available tools:")
                for tool in tools:
                    print(f"  - {tool.name}: {tool.description}")
                
                # Test a specific tool
                if any(tool.name == "db_sql2019_analyze_table_health" for tool in tools):
                    print("\n✓ Found db_sql2019_analyze_table_health tool, testing...")
                    
                    result = await session.call_tool(
                        "db_sql2019_analyze_table_health",
                        arguments={
                            "database_name": "USGISPRO_800",
                            "schema": "dbo", 
                            "table_name": "Account"
                        }
                    )
                    
                    print(f"✓ Tool call successful!")
                    print(f"Result type: {type(result)}")
                    if hasattr(result, 'content'):
                        print(f"Content: {result.content}")
                    else:
                        print(f"Result: {result}")
                
                return True
                
    except Exception as e:
        print(f"✗ MCP server test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_mcp_server())
    if success:
        print("\n🎉 All MCP server tests passed!")
    else:
        print("\n❌ MCP server tests failed!")
        exit(1)
