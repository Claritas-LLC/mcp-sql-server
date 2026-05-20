import os
import uvicorn
from fastapi import FastAPI
from src.server import build_fastapi_app

app = build_fastapi_app()

for route in app.routes:
    print(f"Path: {route.path}, Name: {route.name}, Methods: {getattr(route, 'methods', None)}")
    if hasattr(route, "endpoint"):
        print(f"  Endpoint: {route.endpoint}")
    if hasattr(route, "app"):
        print(f"  Sub-app: {route.app}")
        if hasattr(route.app, "routes"):
            for sub_route in route.app.routes:
                print(f"    Sub-path: {sub_route.path}, Name: {sub_route.name}, Methods: {getattr(sub_route, 'methods', None)}")
