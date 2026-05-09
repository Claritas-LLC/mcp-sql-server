from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.diagnostics.routes import build_diagnostics_router


class _FakeConnectionManager:
    def get_pool_diagnostics(self):
        return {
            "primary": {
                "enabled": True,
                "pool_max": 10,
                "pool_size": 3,
                "in_use": 1,
                "available": 2,
                "created_total": 5,
                "reused_total": 11,
                "discarded_total": 1,
            }
        }

    def healthcheck_all(self):
        return {"primary": {"state": "healthy"}}


def _state() -> SimpleNamespace:
    return SimpleNamespace(
        version="1.0.0",
        policy=SimpleNamespace(write_mode_default="deny"),
        rate_limit_backend="local",
        policy_path="does-not-matter.yaml",
        denied_requests=0,
        registered_tools=[],
        last_secret_refresh_utc="2026-05-09T00:00:00Z",
        connection_manager=_FakeConnectionManager(),
        audit_path="audit.log",
    )


def test_pool_metrics_route_returns_expected_shape() -> None:
    app = FastAPI()
    app.include_router(build_diagnostics_router(_state()), prefix="/diagnostics")

    with TestClient(app) as client:
        response = client.get("/diagnostics/pool")

    assert response.status_code == 200
    payload = response.json()
    assert "instances" in payload
    assert payload["instances"]["primary"]["pool_max"] == 10
    assert payload["instances"]["primary"]["reused_total"] == 11
