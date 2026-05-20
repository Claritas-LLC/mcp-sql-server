from fastapi import FastAPI; from fastmcp import FastMCP; mcp = FastMCP('test'); app = mcp.http_app(path='/'); print([r.path for r in app.routes])
