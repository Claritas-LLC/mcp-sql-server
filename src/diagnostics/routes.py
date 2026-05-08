from __future__ import annotations

import hashlib
import pathlib
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

from src.diagnostics.usage_summary import summarize_audit_events
from src.tools.dashboard_page_store import get_dashboard_page

REQUEST_COUNT = Counter("mcp_requests_total", "Total MCP tool calls", ["tool", "instance", "decision"])
REQUEST_LATENCY = Histogram("mcp_query_latency_ms", "MCP query latency in ms", ["tool", "instance"])


def build_diagnostics_router(state: Any) -> APIRouter:
    router = APIRouter()
    start_time = time.time()

    @router.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": state.version,
            "uptime_seconds": int(time.time() - start_time),
            "instances": state.connection_manager.healthcheck_all(),
        }

    @router.get("/readiness")
    def readiness() -> dict[str, Any]:
        health = state.connection_manager.healthcheck_all()
        required_ok = all(v.get("state") == "healthy" for v in health.values())
        return {
            "ready": required_ok,
            "components": {
                "config_loaded": True,
                "policy_active": True,
                "rate_limiter_active": True,
                "session_manager_active": True,
            },
            "instances": health,
        }

    @router.get("/security")
    def security() -> dict[str, Any]:
        policy_path = pathlib.Path(state.policy_path)
        raw = policy_path.read_bytes() if policy_path.exists() else b""
        registered_tools = list(getattr(state, "registered_tools", []))
        advanced_tools = [name for name in registered_tools if "_analyze_" in name or name.endswith("_dashboard")]
        return {
            "write_mode_default": state.policy.write_mode_default,
            "rate_limit_backend": state.rate_limit_backend,
            "tool_flag_env_applied": getattr(state, "tool_flag_env_applied", False),
            "policy_checksum_sha256": hashlib.sha256(raw).hexdigest(),
            "denied_requests": state.denied_requests,
            "registered_tools_count": len(registered_tools),
            "registered_tools": registered_tools,
            "advanced_tools_count": len(advanced_tools),
            "advanced_tools": advanced_tools,
            "last_secret_refresh_utc": state.last_secret_refresh_utc,
        }

    @router.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @router.get("/audit-summary")
    def audit_summary() -> dict[str, Any]:
        audit_path = pathlib.Path(state.audit_path)
        summary = summarize_audit_events(audit_path)
        return {"events": summary["events"], "latest": summary["latest"]}

    @router.get("/tool-usage-summary")
    def tool_usage_summary() -> dict[str, Any]:
        audit_path = pathlib.Path(state.audit_path)
        return summarize_audit_events(audit_path)

    @router.get("/dashboards/{request_id}")
    def dashboard_page(request_id: str) -> Response:
        html = get_dashboard_page(request_id)
        if html is None:
            raise HTTPException(status_code=404, detail="dashboard_page_not_found_or_expired")
        return Response(content=html, media_type="text/html")

    return router
