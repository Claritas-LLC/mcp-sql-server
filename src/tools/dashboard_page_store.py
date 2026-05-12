from __future__ import annotations

import copy
import os
import re
import threading
import time
from datetime import datetime, timezone


_STORE_LOCK = threading.RLock()
_DASHBOARD_PAGES: dict[str, dict[str, object]] = {}
_MAX_TTL_SECONDS = 7 * 24 * 60 * 60


def _now_epoch() -> float:
    return time.time()


def _validate_request_id(request_id: str) -> None:
    """Validate request_id format: alphanumerics, hyphen, underscore only."""
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id must be a non-empty string")
    if not re.match(r"^[a-zA-Z0-9_-]{1,255}$", request_id):
        raise ValueError("request_id contains invalid characters")


def _validate_html(html: str) -> str:
    if not isinstance(html, str):
        raise ValueError("html must be a string")
    if not html.strip():
        raise ValueError("html must be a non-empty string")
    return html


def _validate_ttl_seconds(ttl_seconds: int) -> int:
    try:
        ttl = int(ttl_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("ttl_seconds must be an integer") from exc
    if ttl < 1:
        raise ValueError("ttl_seconds must be >= 1")
    if ttl > _MAX_TTL_SECONDS:
        raise ValueError(f"ttl_seconds must be <= {_MAX_TTL_SECONDS}")
    return ttl


def _public_base_url() -> str:
    base = os.getenv("FASTMCP_PUBLIC_BASE_URL", "http://localhost:8080").strip()
    return base.rstrip("/")


def _cleanup_expired(now_epoch: float) -> None:
    expired_ids = [
        request_id
        for request_id, entry in _DASHBOARD_PAGES.items()
        if _entry_expires_epoch(entry) <= now_epoch
    ]
    for request_id in expired_ids:
        _DASHBOARD_PAGES.pop(request_id, None)


def _entry_expires_epoch(entry: dict[str, object]) -> float:
    expires_epoch = entry.get("expires_epoch", 0.0)
    if isinstance(expires_epoch, (int, float)) and not isinstance(expires_epoch, bool):
        return float(expires_epoch)
    return 0.0


def register_dashboard_page(request_id: str, html: str, ttl_seconds: int = 900) -> str:
    """Store generated dashboard HTML and return a retrievable URL.

    Pages are stored in-memory with TTL and are retrievable via
    `/diagnostics/dashboards/{request_id}`.
    """
    return register_dashboard_page_with_metadata(
        request_id,
        html,
        ttl_seconds=ttl_seconds,
        metadata=None,
    )


def register_dashboard_page_with_metadata(
    request_id: str,
    html: str,
    *,
    ttl_seconds: int = 900,
    metadata: dict[str, object] | None = None,
) -> str:
    """Store generated dashboard HTML plus metadata used for live refresh."""
    html = _validate_html(html)
    ttl = _validate_ttl_seconds(ttl_seconds)
    _validate_request_id(request_id)
    now_epoch = _now_epoch()
    expires_epoch = now_epoch + ttl
    with _STORE_LOCK:
        _cleanup_expired(now_epoch)
        entry: dict[str, object] = {
            "html": html,
            "expires_epoch": expires_epoch,
        }
        if metadata is not None:
            entry["metadata"] = copy.deepcopy(metadata)
        _DASHBOARD_PAGES[request_id] = entry
    return f"{_public_base_url()}/diagnostics/dashboards/{request_id}"


def _get_valid_entry(request_id: str) -> dict[str, object] | None:
    _validate_request_id(request_id)
    now_epoch = _now_epoch()
    with _STORE_LOCK:
        _cleanup_expired(now_epoch)
        entry = _DASHBOARD_PAGES.get(request_id)
        if entry is None:
            return None
        expires_epoch = _entry_expires_epoch(entry)
        if expires_epoch <= now_epoch:
            _DASHBOARD_PAGES.pop(request_id, None)
            return None
        return entry


def get_dashboard_page(request_id: str) -> str | None:
    """Return stored dashboard HTML if present and not expired; else None."""
    entry = _get_valid_entry(request_id)
    if entry is None:
        return None
    return str(entry.get("html", ""))


def get_dashboard_page_metadata(request_id: str) -> dict[str, object] | None:
    """Return stored dashboard metadata if present and not expired."""
    entry = _get_valid_entry(request_id)
    if entry is None:
        return None
    metadata = entry.get("metadata")
    if not isinstance(metadata, dict):
        return None
    return copy.deepcopy(metadata)


def get_dashboard_page_expiry_utc(request_id: str) -> str | None:
    """Return page expiry timestamp in UTC ISO-8601, if present and not expired."""
    entry = _get_valid_entry(request_id)
    if entry is None:
        return None
    expires_epoch = _entry_expires_epoch(entry)
    return datetime.fromtimestamp(expires_epoch, tz=timezone.utc).isoformat()


def clear_dashboard_pages() -> None:
    """Test helper: clear in-memory dashboard page store."""
    with _STORE_LOCK:
        _DASHBOARD_PAGES.clear()
