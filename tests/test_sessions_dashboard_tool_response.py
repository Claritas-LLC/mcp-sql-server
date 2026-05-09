from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Callable

from src.models import RuntimePolicy
from src.tools.dashboard_page_store import clear_dashboard_pages
from src.tools.sql_tools import register_sql_tools


class _StubMCP:
    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[name] = func
            return func

        return _decorator


class _FakeConnectionManager:
    def list_enabled_instances(self) -> list[str]:
        return ["primary"]

    def execute_catalog_query(
        self, instance_id: str, database_name: str, sql: str, max_rows: int = 5000
    ) -> dict[str, Any]:
        if (
            "sys.dm_exec_sessions s" in sql
            and "LEFT JOIN sys.dm_exec_requests r" in sql
        ):
            return {
                "rows": [
                    {
                        "session_id": 55,
                        "login_name": "app",
                        "host_name": "api-host",
                        "program_name": "api",
                        "status": "running",
                        "session_database_name": database_name,
                        "open_transaction_count": 1,
                        "command": "SELECT",
                        "wait_type": None,
                        "wait_time": 0,
                        "cpu_time": 2,
                        "blocking_session_id": None,
                    }
                ],
                "columns": [],
                "row_count": 1,
                "latency_ms": 1,
            }
        if (
            "sys.dm_os_waiting_tasks" in sql
            and "blocking_session_id IS NOT NULL" in sql
        ):
            return {
                "rows": [
                    {
                        "session_id": 77,
                        "blocking_session_id": 66,
                        "wait_type": "LCK_M_X",
                        "wait_duration_ms": 1200,
                        "resource_description": "KEY: 7:12345",
                    }
                ],
                "columns": [],
                "row_count": 1,
                "latency_ms": 1,
            }
        if "sys.dm_tran_locks" in sql:
            return {"rows": [], "columns": [], "row_count": 0, "latency_ms": 1}
        if "FROM sys.dm_exec_requests r" in sql and "blocking_session_id > 0" in sql:
            return {
                "rows": [
                    {
                        "session_id": 77,
                        "blocking_session_id": 66,
                        "wait_type": "LCK_M_X",
                        "wait_time": 1200,
                        "status": "suspended",
                        "login_name": "app",
                        "host_name": "api-host",
                        "command": "UPDATE",
                    }
                ],
                "columns": [],
                "row_count": 1,
                "latency_ms": 1,
            }
        if "sys.dm_os_waiting_tasks" in sql:
            return {"rows": [], "columns": [], "row_count": 0, "latency_ms": 1}
        return {"rows": [], "columns": [], "row_count": 0, "latency_ms": 1}


def _build_state() -> SimpleNamespace:
    return SimpleNamespace(
        policy=RuntimePolicy(),
        connection_manager=_FakeConnectionManager(),
        session_manager=SimpleNamespace(touch=lambda actor, req: None),
        rate_limiter=SimpleNamespace(allow=lambda actor: None),
        write_guard=SimpleNamespace(enforce=lambda tool, sql: None),
        audit_logger=SimpleNamespace(log_event=lambda **kwargs: None),
        denied_requests=0,
    )


def test_sessions_dashboard_response_includes_dashboard_url() -> None:
    clear_dashboard_pages()
    mcp = _StubMCP()
    state = _build_state()

    _ = register_sql_tools(mcp, state)
    tool_fn = mcp.tools["db_1_sql2019_sessions_dashboard"]

    result = asyncio.run(
        tool_fn(
            database_name="master",
            lookback_minutes=15,
            include_locks=True,
            actor="test",
            ctx=None,
        )
    )

    assert isinstance(result.get("dashboard_url"), str)
    assert "/diagnostics/dashboards/" in result["dashboard_url"]
    assert result.get("request_id")
    assert result.get("expires_at_utc")
    assert result.get("content_type") == "text/html"
    assert isinstance(result.get("html"), str)
    assert isinstance(result.get("data"), dict)
