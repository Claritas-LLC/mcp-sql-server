from __future__ import annotations

import os
import re
import threading
import time
from datetime import datetime, timezone


_STORE_LOCK = threading.RLock()
_DASHBOARD_PAGES: dict[str, dict[str, object]] = {}


def _now_epoch() -> float:
    return time.time()


def _validate_request_id(request_id: str) -> None:
    """Validate request_id format: alphanumerics, hyphen, underscore only."""
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id must be a non-empty string")
    if not re.match(r"^[a-zA-Z0-9_-]{1,255}$", request_id):
        raise ValueError(f"request_id contains invalid characters: {request_id}")


def _public_base_url() -> str:
    base = os.getenv("FASTMCP_PUBLIC_BASE_URL", "http://localhost:8080").strip()
    return base.rstrip("/")


def _cleanup_expired(now_epoch: float) -> None:
    expired_ids = [
        request_id
        for request_id, entry in _DASHBOARD_PAGES.items()
        if float(entry.get("expires_epoch", 0.0)) <= now_epoch
    ]
    for request_id in expired_ids:
        _DASHBOARD_PAGES.pop(request_id, None)


def register_dashboard_page(request_id: str, html: str, ttl_seconds: int = 900) -> str:
    """Store generated dashboard HTML and return a retrievable URL.

    Pages are stored in-memory with TTL and are retrievable via
    `/diagnostics/dashboards/{request_id}`.
    """
    _validate_request_id(request_id)
    now_epoch = _now_epoch()
    expires_epoch = now_epoch + max(ttl_seconds, 1)
    with _STORE_LOCK:
        _cleanup_expired(now_epoch)
        _DASHBOARD_PAGES[request_id] = {
            "html": html,
            "expires_epoch": expires_epoch,
        }
    return f"{_public_base_url()}/diagnostics/dashboards/{request_id}"


def get_dashboard_page(request_id: str) -> str | None:
    """Return stored dashboard HTML if present and not expired; else None."""
    _validate_request_id(request_id)
    now_epoch = _now_epoch()
    with _STORE_LOCK:
        _cleanup_expired(now_epoch)
        entry = _DASHBOARD_PAGES.get(request_id)
        if entry is None:
            return None
        expires_epoch = float(entry.get("expires_epoch", 0.0))
        if expires_epoch <= now_epoch:
            _DASHBOARD_PAGES.pop(request_id, None)
            return None
        return str(entry.get("html", ""))


def get_dashboard_page_expiry_utc(request_id: str) -> str | None:
    """Return page expiry timestamp in UTC ISO-8601, if present and not expired."""
    _validate_request_id(request_id)
    now_epoch = _now_epoch()
    with _STORE_LOCK:
        _cleanup_expired(now_epoch)
        entry = _DASHBOARD_PAGES.get(request_id)
        if entry is None:
            return None
        expires_epoch = float(entry.get("expires_epoch", 0.0))
        return datetime.fromtimestamp(expires_epoch, tz=timezone.utc).isoformat()


def clear_dashboard_pages() -> None:
    """Test helper: clear in-memory dashboard page store."""
    with _STORE_LOCK:
        _DASHBOARD_PAGES.clear()
