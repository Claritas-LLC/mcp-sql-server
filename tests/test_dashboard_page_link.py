from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.diagnostics.routes import build_diagnostics_router
import src.tools.dashboard_page_store as page_store
from src.tools.dashboard_page_store import clear_dashboard_pages, get_dashboard_page, register_dashboard_page


def _fake_state() -> SimpleNamespace:
    return SimpleNamespace(audit_path="audit.log")


def test_register_dashboard_page_returns_dashboard_url(monkeypatch) -> None:
    clear_dashboard_pages()
    monkeypatch.setenv("FASTMCP_PUBLIC_BASE_URL", "https://mcp.example.com")

    url = register_dashboard_page("req-123", "<html><body>ok</body></html>", ttl_seconds=900)

    assert url == "https://mcp.example.com/diagnostics/dashboards/req-123"


def test_register_dashboard_page_round_trip_content() -> None:
    clear_dashboard_pages()

    _ = register_dashboard_page("req-abc", "<html><body>dashboard</body></html>", ttl_seconds=900)
    stored = get_dashboard_page("req-abc")

    assert stored == "<html><body>dashboard</body></html>"


def test_diagnostics_dashboard_route_returns_200_and_404() -> None:
    clear_dashboard_pages()

    app = FastAPI()
    app.include_router(build_diagnostics_router(_fake_state()), prefix="/diagnostics")

    register_dashboard_page("req-route", "<html><body>route ok</body></html>", ttl_seconds=900)

    with TestClient(app) as client:
        ok_resp = client.get("/diagnostics/dashboards/req-route")
        assert ok_resp.status_code == 200
        assert ok_resp.headers["content-type"].startswith("text/html")
        assert "route ok" in ok_resp.text

        missing_resp = client.get("/diagnostics/dashboards/does-not-exist")
        assert missing_resp.status_code == 404
        assert missing_resp.json()["detail"] == "dashboard_page_not_found_or_expired"


def test_dashboard_page_expires_after_ttl(monkeypatch) -> None:
    clear_dashboard_pages()

    _ = register_dashboard_page("req-expire", "<html><body>ttl</body></html>", ttl_seconds=1)
    assert get_dashboard_page("req-expire") is not None

    monkeypatch.setattr(page_store, "_now_epoch", lambda: 10_000_000_000.0)
    assert get_dashboard_page("req-expire") is None
