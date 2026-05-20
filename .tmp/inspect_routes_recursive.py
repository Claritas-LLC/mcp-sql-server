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

def dump_app(app, prefix=""):
    for route in app.routes:
        methods = getattr(route, 'methods', None)
        print(f"{prefix}Path: {route.path}, Name: {route.name}, Methods: {methods}")
        if hasattr(route, "app"):
            sub_app = route.app
            if hasattr(sub_app, "routes"):
                dump_app(sub_app, prefix + "  ")
            elif hasattr(sub_app, "app"): # Nested mounts
                 dump_app(sub_app.app, prefix + "  ")

print("--- App Route Tree ---")
dump_app(app)
