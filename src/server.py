import os
import time
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastmcp import FastMCP
import uvicorn

from src.config_loader import AppConfig, load_config
from src.db.connection_manager import ConnectionManager
from src.diagnostics.routes import build_diagnostics_router
from src.middleware.audit_logger import AuditLogger
from src.middleware.rate_limiter import RateLimiter, build_rate_limiter
from src.middleware.write_guard import WriteGuard
from src.models import RuntimePolicy
from src.security.session_manager import SessionManager
from src.tools.sql_tools import register_sql_tools


def secret_resolver(secret_ref: str) -> dict[str, str]:
    env_name = secret_ref.upper().replace("/", "_")
    username = os.getenv(f"{env_name}_USERNAME", "readonly_user")
    password = os.getenv(f"{env_name}_PASSWORD", "change-me")
    return {"username": username, "password": password}


@dataclass
class AppState:
    version: str
    config: AppConfig
    policy: RuntimePolicy
    policy_path: str
    audit_path: str
    connection_manager: ConnectionManager
    write_guard: WriteGuard
    rate_limiter: RateLimiter
    audit_logger: AuditLogger
    session_manager: SessionManager
    rate_limit_backend: str
    registered_tools: list[str]
    tool_flag_env_applied: bool
    denied_requests: int = 0
    last_secret_refresh_utc: str = ""



def build_fastapi_app() -> FastAPI:
    config_path = os.getenv("FASTMCP_CONFIG_PATH", "config/instances.yaml")
    policy_path = os.getenv("FASTMCP_POLICY_PATH", "config/runtime-policy.yaml")
    rate_limit_path = os.getenv("FASTMCP_RATE_LIMIT_PATH", "config/rate-limit.yaml")
    audit_path = os.getenv("FASTMCP_AUDIT_PATH", "/var/log/mcp/audit.log")
    rate_limit_backend = os.getenv("FASTMCP_RATE_LIMIT_BACKEND", "local")
    redis_url = os.getenv("FASTMCP_REDIS_URL")
    redis_namespace = os.getenv("FASTMCP_REDIS_NAMESPACE", "mcp:ratelimit")
    has_tool_flag_env = bool(os.getenv("FASTMCP_TOOL_ENABLE_FLAGS_JSON") or os.getenv("FASTMCP_INSTANCE_TOOL_ENABLE_FLAGS_JSON"))

    cfg = load_config(config_path, policy_path, rate_limit_path)
    conn_mgr = ConnectionManager(cfg.instances, secret_resolver=secret_resolver)
    limiter = build_rate_limiter(
        backend=rate_limit_backend,
        actor_rpm=cfg.rate_limit.actor.requests_per_minute,
        actor_burst=cfg.rate_limit.actor.burst,
        global_rpm=cfg.rate_limit.global_.requests_per_minute,
        global_burst=cfg.rate_limit.global_.burst,
        redis_url=redis_url,
        redis_namespace=redis_namespace,
    )
    state = AppState(
        version="1.0.0",
        config=cfg,
        policy=cfg.policy,
        policy_path=policy_path,
        audit_path=audit_path,
        connection_manager=conn_mgr,
        write_guard=WriteGuard(cfg.policy),
        rate_limiter=limiter,
        audit_logger=AuditLogger(file_path=audit_path),
        session_manager=SessionManager(
            session_ttl_minutes=cfg.rate_limit.session.session_ttl_minutes,
            inactivity_timeout_minutes=cfg.rate_limit.session.inactivity_timeout_minutes,
            concurrent_sessions_limit=cfg.rate_limit.session.concurrent_sessions_limit,
        ),
        rate_limit_backend=rate_limit_backend,
        registered_tools=[],
        tool_flag_env_applied=has_tool_flag_env,
        last_secret_refresh_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    mcp = FastMCP("sql2019-dual-instance")
    registered_tools = register_sql_tools(mcp, state)
    state.registered_tools = registered_tools

    # FastMCP versions differ in mount helper names. Use getattr to stay
    # compatible across versions without triggering type-checker errors on
    # attributes that may not exist in the installed version's stubs.
    mcp_app: Any
    _http_app_factory = getattr(mcp, "http_app", None) or getattr(mcp, "streamable_http_app", None)
    if _http_app_factory is not None:
        mcp_app = _http_app_factory(path="/")
    else:
        # Fallback for environments expecting direct run only.
        mcp_app = FastAPI()

    parent_lifespan = getattr(mcp_app, "lifespan", None)
    app = FastAPI(title="FastMCP SQL Server 2019", version=state.version, lifespan=parent_lifespan)
    app.state.runtime = state
    app.state.registered_tools = registered_tools
    app.include_router(build_diagnostics_router(state), prefix="/diagnostics")

    app.mount("/mcp", mcp_app)

    @app.get("/")
    def root() -> dict[str, Any]:
        return {"service": "fastmcp-sql2019", "status": "ok", "tools": registered_tools}

    return app


def main() -> None:
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8080"))
    uvicorn.run(build_fastapi_app(), host=host, port=port)


if __name__ == "__main__":
    main()
