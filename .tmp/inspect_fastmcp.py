import os
from unittest.mock import MagicMock
import sys
import inspect

# Mock ConnectionManager etc. before importing
sys.modules["src.db.connection_manager"] = MagicMock()
sys.modules["src.middleware.audit_logger"] = MagicMock()

from fastmcp import FastMCP

mcp = FastMCP("test")
if hasattr(mcp, "http_app"):
    app_factory = mcp.http_app
    print(f"Factory: {app_factory}")
    # Inspect the source or routes of what it creates
    from fastapi import FastAPI
    app = app_factory("/")
    print("--- MCP App Routes ---")
    for route in app.routes:
        print(f"Path: {route.path}")
elif hasattr(mcp, "streamable_http_app"):
    app_factory = mcp.streamable_http_app
    print(f"Streamable Factory: {app_factory}")
    app = app_factory("/")
    print("--- MCP App Routes ---")
    for route in app.routes:
        print(f"Path: {route.path}")
else:
    print("No http_app or streamable_http_app found")
