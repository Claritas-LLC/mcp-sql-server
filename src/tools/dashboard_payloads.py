from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_sessions_dashboard(*, instance_number: int, database_name: str, sessions: list[dict[str, Any]], lock_chains: list[dict[str, Any]]) -> dict[str, Any]:
    html = (
        "<section><h2>SQL Sessions Dashboard</h2>"
        f"<p>Instance {instance_number} / Database {database_name}</p>"
        f"<p>Active sessions: {len(sessions)} | Lock chains: {len(lock_chains)}</p>"
        "</section>"
    )
    return {
        "content_type": "text/html",
        "html": html,
        "data": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "instance_number": instance_number,
            "database_name": database_name,
            "widgets": {
                "active_sessions": sessions,
                "lock_chains": lock_chains,
            },
        },
    }
