import os
from unittest.mock import MagicMock
import sys

# Mock ConnectionManager etc. before importing
sys.modules["src.db.connection_manager"] = MagicMock()
sys.modules["src.middleware.audit_logger"] = MagicMock()

from fastapi import FastAPI
from src.server import build_fastapi_app

# Fake environment variables
os.environ["FASTMCP_CONFIG_PATH"] = "config/instances.yaml"
os.environ["FASTMCP_POLICY_PATH"] = "config/runtime-policy.yaml"
os.environ["FASTMCP_RATE_LIMIT_PATH"] = "config/rate-limit.yaml"

app = build_fastapi_app()

print("--- Root App Routes ---")
for route in app.routes:
    methods = getattr(route, 'methods', None)
    print(f"Path: {route.path}, Name: {route.name}, Methods: {methods}")
    if hasattr(route, "app"):
        print(f"  Mount: {route.path}")
        sub_app = route.app
        if hasattr(sub_app, "routes"):
            for sub_route in sub_app.routes:
                sub_methods = getattr(sub_route, 'methods', None)
                print(f"    Sub-path: {sub_route.path}, Name: {sub_route.name}, Methods: {sub_methods}")
