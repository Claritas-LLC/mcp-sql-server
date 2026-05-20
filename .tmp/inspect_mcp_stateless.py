import os
from unittest.mock import MagicMock
import sys
import asyncio

# Mock ConnectionManager etc. before importing
sys.modules["src.db.connection_manager"] = MagicMock()
sys.modules["src.middleware.audit_logger"] = MagicMock()

from fastmcp import FastMCP

async def inspect_mcp():
    mcp = FastMCP("test")
    _http_app_factory = getattr(mcp, "http_app", None) or getattr(
        mcp, "streamable_http_app", None
    )
    
    if _http_app_factory:
        print(f"Factory: {_http_app_factory}")
        app = _http_app_factory("/", stateless_http=True)
        
        # We need to trigger the lifespan to initialize the session manager
        async with app.lifespan(app):
            print("--- MCP App Routes ---")
            for route in app.routes:
                print(f"Path: {route.path}")
                if hasattr(route, "endpoint"):
                    ep = route.endpoint
                    print(f"Endpoint: {ep}")
                    if hasattr(ep, "session_manager"):
                        sm = ep.session_manager
                        print(f"Session Manager: {sm}")
                        if hasattr(sm, "_stateless"):
                            print(f"Stateless: {sm._stateless}")
                        elif hasattr(sm, "stateless"):
                            print(f"Stateless: {sm.stateless}")
                        else:
                            print("Stateless property not found")

if __name__ == "__main__":
    asyncio.run(inspect_mcp())
