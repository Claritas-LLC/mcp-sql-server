from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from src.models import AuthConfig, RuntimePolicy
from src.tools.sql_tools import register_sql_tools


class _StubMCP:
    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(self, name: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[name] = func
            return func

        return _decorator


class _FakeConnectionManager:
    def list_enabled_instances(self) -> list[str]:
        return ["primary"]

    def execute_read(
        self, instance: str, sql: str, max_rows: int
    ) -> list[dict[str, Any]]:
        return [{"instance": instance, "sql": sql, "max_rows": max_rows}]

    def execute_proc(
        self,
        instance_id: str,
        procedure_name: str,
        params: list[str | int | float | bool | None] | None = None,
    ) -> dict[str, Any]:
        return {
            "proc_name": procedure_name,
            "rows": [{"ok": True}],
            "row_count": 1,
            "columns": ["ok"],
            "latency_ms": 1,
            "params": params or [],
        }


def _build_state(auth: AuthConfig) -> SimpleNamespace:
    return SimpleNamespace(
        auth=auth,
        policy=RuntimePolicy(
            allowed_write_tools=["db_1_sql2019_exec_proc"],
            instance_enable_flags={"primary": True},
        ),
        connection_manager=_FakeConnectionManager(),
        session_manager=SimpleNamespace(touch=lambda actor, req: None),
        rate_limiter=SimpleNamespace(allow=lambda actor: None),
        write_guard=SimpleNamespace(
            enforce=lambda tool, sql: None,
            validate_procedure=lambda tool, proc_name: None,
        ),
        audit_logger=SimpleNamespace(log_event=lambda **kwargs: None),
        denied_requests=0,
    )


def _auth_config() -> AuthConfig:
    return AuthConfig(
        auth_mode="azure_token_verifier",
        azure_auth_enabled=True,
        azure_group_authorization_enabled=True,
        azure_group_claim_name="groups",
        azure_read_groups=["sql-readers"],
        azure_write_groups=["sql-writers"],
    )


def _register_tools(auth: AuthConfig) -> tuple[_StubMCP, SimpleNamespace]:
    mcp = _StubMCP()
    state = _build_state(auth)
    register_sql_tools(mcp, state)
    return mcp, state


def _make_token(subject: str, groups: list[str]) -> SimpleNamespace:
    return SimpleNamespace(claims={"preferred_username": subject, "groups": groups})


def test_select_denies_when_token_missing(monkeypatch) -> None:
    mcp, state = _register_tools(_auth_config())
    monkeypatch.setattr("src.tools.sql_tools.get_access_token", lambda: None)

    with pytest.raises(
        PermissionError, match="AUTH_FAILED: missing or invalid bearer token"
    ):
        asyncio.run(
            mcp.tools["db_primary_sql2019_select"](
                sql="SELECT 1 AS value",
                actor="system",
                ctx=None,
            )
        )

    assert state.denied_requests == 1


def test_select_allows_read_group_and_uses_subject_as_actor(monkeypatch) -> None:
    mcp, state = _register_tools(_auth_config())
    monkeypatch.setattr(
        "src.tools.sql_tools.get_access_token",
        lambda: _make_token("reader@example.com", ["sql-readers"]),
    )

    result = asyncio.run(
        mcp.tools["db_primary_sql2019_select"](
            sql="SELECT 1 AS value",
            actor="system",
            ctx=None,
        )
    )

    assert result["row_count"] == 1
    assert result["rows"][0]["instance"] == "primary"
    assert state.denied_requests == 0


def test_exec_proc_denies_for_read_only_group(monkeypatch) -> None:
    mcp, state = _register_tools(_auth_config())
    monkeypatch.setattr(
        "src.tools.sql_tools.get_access_token",
        lambda: _make_token("reader@example.com", ["sql-readers"]),
    )

    with pytest.raises(PermissionError, match="AUTH_FAILED: write privilege required"):
        asyncio.run(
            mcp.tools["db_primary_sql2019_exec_proc"](
                proc_name="dbo.usp_DoThing",
                params=[1],
                actor="system",
                ctx=None,
            )
        )

    assert state.denied_requests == 1


def test_exec_proc_allows_write_group(monkeypatch) -> None:
    mcp, state = _register_tools(_auth_config())
    monkeypatch.setattr(
        "src.tools.sql_tools.get_access_token",
        lambda: _make_token("writer@example.com", ["sql-writers"]),
    )

    result = asyncio.run(
        mcp.tools["db_primary_sql2019_exec_proc"](
            proc_name="dbo.usp_DoThing",
            params=[1],
            actor="system",
            ctx=None,
        )
    )

    assert result["instance"] == "primary"
    assert result["row_count"] == 1
    assert result["proc_name"] == "dbo.usp_DoThing"
    assert state.denied_requests == 0
