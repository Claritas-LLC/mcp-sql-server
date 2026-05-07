from __future__ import annotations

from typing import Any


_SENSITIVE_TOKENS = ("password", "secret", "token", "connection_string", "pwd")


def redact_sensitive_fields(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    redacted: list[dict[str, Any]] = []
    for row in rows:
        cleaned: dict[str, Any] = {}
        for key, value in row.items():
            lower = key.lower()
            if any(token in lower for token in _SENSITIVE_TOKENS):
                cleaned[key] = "***REDACTED***"
            else:
                cleaned[key] = value
        redacted.append(cleaned)
    return redacted
