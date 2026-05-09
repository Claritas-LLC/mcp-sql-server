from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.diagnostics.routes import build_diagnostics_router


class _FakeConnectionManager:
    def healthcheck_all(self):
        return {"primary": {"state": "healthy"}}

    def get_pool_diagnostics(self):
        return {"primary": {"pool_max": 10}}


def _state(tmp_path: Path) -> SimpleNamespace:
    policy_path = tmp_path / "runtime-policy.yaml"
    policy_path.write_text("write_mode_default: deny\n", encoding="utf-8")
    return SimpleNamespace(
        version="1.0.0",
        policy=SimpleNamespace(write_mode_default="deny"),
        auth=SimpleNamespace(
            auth_mode="azure_token_verifier",
            azure_auth_enabled=True,
            azure_group_authorization_enabled=True,
            azure_required_scopes=["read", "write"],
            azure_read_groups=["group-read-1", "group-read-2"],
            azure_write_groups=["group-write-1"],
        ),
        rate_limit_backend="local",
        policy_path=str(policy_path),
        denied_requests=2,
        registered_tools=["db_primary_sql2019_select"],
        last_secret_refresh_utc="2026-05-09T00:00:00Z",
        connection_manager=_FakeConnectionManager(),
        audit_path=str(tmp_path / "audit.log"),
        tool_flag_env_applied=False,
    )


def test_security_route_includes_auth_summary(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(
        build_diagnostics_router(_state(tmp_path)), prefix="/diagnostics"
    )

    with TestClient(app) as client:
        response = client.get("/diagnostics/security")

    assert response.status_code == 200
    payload = response.json()
    assert payload["auth"]["auth_mode"] == "azure_token_verifier"
    assert payload["auth"]["azure_auth_enabled"] is True
    assert payload["auth"]["azure_group_authorization_enabled"] is True
    assert payload["auth"]["required_scopes"] == ["read", "write"]
    assert payload["auth"]["read_group_count"] == 2
    assert payload["auth"]["write_group_count"] == 1
