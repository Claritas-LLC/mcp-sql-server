#!/usr/bin/env python3
"""Test script for the db_sql2019_db_analyze_query_store tool"""

import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_query_store_tool():
    """Test the query store analysis tool"""
    server_params = StdioServerParameters(
        command="python",
        args=["server.py"],
        env=None
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the session
            await session.initialize()
            
            # Test the tool
            result = await session.call_tool(
                "db_sql2019_db_analyze_query_store",
                arguments={"database": "ACS"}
            )
            
            print("Tool Result:")
            print(json.dumps(result, indent=2))
            
            # Extract the URL and test it
            if hasattr(result, 'content'):
                content = json.loads(result.content[0].text)
                url = content.get('report_url')
            else:
                url = result.get('report_url')
            
            if url:
                print(f"\nReport URL: {url}")
                print("You can now visit this URL in your browser to see the analysis report.")
            else:
                print("No URL found in result")

if __name__ == "__main__":
    asyncio.run(test_query_store_tool())