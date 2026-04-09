# server_startup.py

"""
Safe startup entrypoint for MCP SQL Server backend.
- Ensures connection pools are initialized only at runtime, not on import.
- Use this file to launch the server in production or development.

Usage:
    python server_startup.py
"""


# Import the FastMCP app instance and pool initializer
from mcp_sqlserver.server import initialize_connection_pools, run_server_entrypoint

if __name__ == "__main__":
    # Initialize all DB connection pools (thread-safe, idempotent)
    initialize_connection_pools()
    # Start the FastMCP server through the canonical runtime entrypoint.
    run_server_entrypoint()
