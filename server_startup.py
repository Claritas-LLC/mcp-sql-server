# server_startup.py

"""
Safe startup entrypoint for MCP SQL Server backend.
- Ensures connection pools are initialized only at runtime, not on import.
- Use this file to launch the server in production or development.

Usage:
    python server_startup.py
"""


# Import the FastMCP app instance and pool initializer
from mcp_sqlserver.server import mcp, initialize_connection_pools, SETTINGS

if __name__ == "__main__":
    # Initialize all DB connection pools (thread-safe, idempotent)
    initialize_connection_pools()
    # Start the MCP server (FastMCP main entrypoint) with explicit transport/host/port
    mcp.run(transport=SETTINGS.transport, host=SETTINGS.host, port=SETTINGS.port)
