import asyncio
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

async def run():
    async with sse_client("http://localhost:8085/mcp/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # List tools
            tools = await session.list_tools()
            print(f"Available tools: {[t.name for t in tools.tools]}")
            
            # Call a tool
            result = await session.call_tool(
                "db_primary_sql2019_analyze_db_data_model",
                arguments={"database_name": "master", "actor": "poc-actor"}
            )
            print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(run())
