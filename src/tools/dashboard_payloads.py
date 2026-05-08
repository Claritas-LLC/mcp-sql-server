from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Typed state schema for interactive app clients
# ---------------------------------------------------------------------------

DASHBOARD_STATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "generated_at_utc": {"type": "string", "format": "date-time"},
        "instance_number": {"type": "integer"},
        "database_name": {"type": "string"},
        "lookback_minutes": {"type": "integer"},
        "ui_meta": {
            "type": "object",
            "properties": {
                "loading": {"type": "boolean"},
                "error": {"type": ["string", "null"]},
            },
            "required": ["loading", "error"],
        },
        "sessions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "login_name": {"type": "string"},
                    "host_name": {"type": "string"},
                    "program_name": {"type": "string"},
                    "status": {"type": "string"},
                    "command": {"type": ["string", "null"]},
                    "wait_type": {"type": ["string", "null"]},
                    "wait_time": {"type": ["integer", "null"]},
                    "cpu_time": {"type": ["integer", "null"]},
                    "blocking_session_id": {"type": ["integer", "null"]},
                },
            },
        },
        "locks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "resource_type": {"type": "string"},
                    "resource_database_id": {"type": ["integer", "null"]},
                    "resource_associated_entity_id": {"type": ["integer", "null"]},
                    "request_mode": {"type": "string"},
                    "request_status": {"type": "string"},
                    "request_owner_type": {"type": "string"},
                },
            },
        },
        "blockers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "blocking_session_id": {"type": ["integer", "null"]},
                    "wait_type": {"type": ["string", "null"]},
                    "wait_duration_ms": {"type": ["integer", "null"]},
                    "resource_description": {"type": ["string", "null"]},
                },
            },
        },
        "blocking_chains": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "session_id": {"type": ["integer", "null"]},
                    "blocking_session_id": {"type": ["integer", "null"]},
                    "wait_type": {"type": ["string", "null"]},
                    "wait_time": {"type": ["integer", "null"]},
                    "status": {"type": ["string", "null"]},
                    "login_name": {"type": ["string", "null"]},
                    "host_name": {"type": ["string", "null"]},
                    "command": {"type": ["string", "null"]},
                },
            },
        },
        "head_blockers": {"type": "array", "items": {"type": "integer"}},
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "priority": {"type": "string"},
                    "action": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["priority", "action", "rationale"],
            },
        },
    },
    "required": [
        "generated_at_utc",
        "instance_number",
        "database_name",
        "ui_meta",
        "sessions",
        "locks",
        "blockers",
        "blocking_chains",
        "head_blockers",
        "recommendations",
    ],
}


def _esc(value: Any) -> str:
    if value is None:
        return "&mdash;"
    return html.escape(str(value))


def _session_row_class(session: dict[str, Any], head_blockers: set[int]) -> str:
    session_id = session.get("session_id")
    try:
        sid = int(session_id)
    except (TypeError, ValueError):
        sid = -1

    if sid in head_blockers:
        return "row-head-blocker"

    blocker = session.get("blocking_session_id")
    try:
        blocker_sid = int(blocker)
    except (TypeError, ValueError):
        blocker_sid = 0
    if blocker_sid > 0:
        return "row-blocked"

    status = str(session.get("status", "")).lower()
    if status in {"running", "suspended"}:
        return "row-active"
    return "row-idle"


def _html_inline_styles() -> str:
    return """
<style>
  :root {
    --c-active: #22c55e;
    --c-idle: #94a3b8;
    --c-blocked: #ef4444;
    --c-blocker: #f97316;
    --bg: #f8fafc;
    --card: #ffffff;
    --text: #0f172a;
    --muted: #475569;
    --border: #e2e8f0;
  }
  body { margin: 0; background: var(--bg); color: var(--text); font-family: Segoe UI, Arial, sans-serif; }
  .page { max-width: 1400px; margin: 0 auto; padding: 16px; }
  .meta { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0 14px; }
  .badge { border-radius: 999px; padding: 3px 10px; font-size: 12px; font-weight: 700; border: 1px solid var(--border); background: #fff; }
  .badge-active { background: #dcfce7; color: #166534; }
  .badge-idle { background: #e2e8f0; color: #334155; }
  .badge-blocked { background: #fee2e2; color: #991b1b; }
  .badge-blocker { background: #ffedd5; color: #9a3412; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px; margin: 10px 0; }
  table { width: 100%; border-collapse: collapse; font-family: ui-monospace, Consolas, monospace; font-size: 12px; }
  th, td { border-bottom: 1px solid var(--border); text-align: left; padding: 8px; vertical-align: top; }
  th { background: #f1f5f9; font-weight: 700; }
  .row-active { background: #f0fdf4; }
  .row-idle { background: #f8fafc; }
  .row-blocked { background: #fef2f2; }
  .row-head-blocker { background: #fff7ed; font-weight: 700; }
  .rec-card { border-left: 4px solid #3b82f6; padding: 8px 10px; margin: 8px 0; background: #eff6ff; border-radius: 6px; }
  .rec-high { border-left-color: #ef4444; background: #fef2f2; }
  .rec-medium { border-left-color: #f97316; background: #fff7ed; }
  .rec-info { border-left-color: #3b82f6; background: #eff6ff; }
  details { margin: 8px 0; }
  summary { cursor: pointer; font-weight: 700; }
  .muted { color: var(--muted); }
</style>
"""


def _html_header(
    instance_number: int,
    database_name: str,
    generated_at_utc: str,
    session_count: int,
    lock_count: int,
    wait_count: int,
    chain_count: int,
) -> str:
    return (
        "<header class=\"card\"><h1>SQL Server Sessions Dashboard</h1>"
        f"<div class=\"muted\">Instance {instance_number} / Database {_esc(database_name)}</div>"
        f"<div class=\"muted\">Generated {_esc(generated_at_utc)}</div>"
        "<div class=\"meta\">"
        f"<span class=\"badge\">Sessions: {session_count}</span>"
        f"<span class=\"badge\">Lock Holders: {lock_count}</span>"
        f"<span class=\"badge\">Waiting Tasks: {wait_count}</span>"
        f"<span class=\"badge\">Chain Rows: {chain_count}</span>"
        "</div></header>"
    )


def _html_sessions_table(sessions: list[dict[str, Any]], head_blockers: list[int]) -> str:
    hb = set(head_blockers)
    active_count = 0
    idle_count = 0
    blocked_count = 0
    head_blocker_count = 0
    rows_html: list[str] = []

    for session in sessions:
        css_class = _session_row_class(session, hb)
        if css_class == "row-active":
            active_count += 1
            status_badge = '<span class="badge badge-active">ACTIVE</span>'
        elif css_class == "row-idle":
            idle_count += 1
            status_badge = '<span class="badge badge-idle">IDLE</span>'
        elif css_class == "row-blocked":
            blocked_count += 1
            status_badge = '<span class="badge badge-blocked">BLOCKED</span>'
        else:
            head_blocker_count += 1
            status_badge = '<span class="badge badge-blocker">HEAD-BLOCKER</span>'

        rows_html.append(
            "<tr class=\"%s\">"
            "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "</tr>"
            % (
                css_class,
                status_badge,
                _esc(session.get("session_id")),
                _esc(session.get("login_name")),
                _esc(session.get("host_name")),
                _esc(session.get("program_name")),
                _esc(session.get("session_database_name")),
                _esc(session.get("command")),
                _esc(session.get("wait_type")),
                _esc(session.get("wait_time")),
                _esc(session.get("cpu_time")),
                _esc(session.get("open_transaction_count")),
                _esc(session.get("blocking_session_id")),
            )
        )

    caption = (
        f"<caption class=\"muted\">Sessions: {len(sessions)} | Active: {active_count} | "
        f"Idle: {idle_count} | Blocked: {blocked_count} | Head-Blockers: {head_blocker_count}</caption>"
    )
    return (
        "<section class=\"card\" id=\"sessions\"><h2>Sessions</h2>"
        "<table>"
        f"{caption}"
        "<thead><tr><th>Status</th><th>SID</th><th>Login</th><th>Host</th><th>Program</th><th>Database</th><th>Command</th><th>Wait Type</th><th>Wait (ms)</th><th>CPU (ms)</th><th>Txns</th><th>Blocking SID</th></tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody></table></section>"
    )


def _html_chain_section(blocking_chains: list[dict[str, Any]], waiting_tasks: list[dict[str, Any]]) -> str:
    if not blocking_chains:
        return "<section class=\"card\" id=\"chains\"><h2>Session Chains</h2><p>No blocking chains detected.</p></section>"

    wait_by_session: dict[int, str] = {}
    for row in waiting_tasks:
        try:
            sid = int(row.get("session_id"))
        except (TypeError, ValueError):
            continue
        if sid not in wait_by_session:
            wait_by_session[sid] = str(row.get("resource_description") or "")

    grouped: dict[str, list[dict[str, Any]]] = {}
    blocking_by_session: dict[int, int] = {}
    for row in blocking_chains:
        grouped.setdefault(str(row.get("blocking_session_id")), []).append(row)
        try:
            sid = int(row.get("session_id"))
            bsid = int(row.get("blocking_session_id"))
        except (TypeError, ValueError):
            continue
        if sid > 0 and bsid > 0:
            blocking_by_session[sid] = bsid

    def _depth_for_session(session_id: int) -> int:
        depth = 0
        seen: set[int] = set()
        current = session_id
        while current in blocking_by_session and current not in seen:
            seen.add(current)
            current = blocking_by_session[current]
            depth += 1
            if depth > 16:
                break
        return depth

    chunks: list[str] = ["<section class=\"card\" id=\"chains\"><h2>Session Chains</h2>"]
    for blocker_sid, rows in grouped.items():
        max_wait = 0
        for row in rows:
            try:
                max_wait = max(max_wait, int(row.get("wait_time") or 0))
            except (TypeError, ValueError):
                pass

        chunks.append(
            f"<details open><summary>Head blocker SID { _esc(blocker_sid) } | Blocked sessions: {len(rows)} | Max wait: {_esc(max_wait)} ms</summary>"
        )
        chunks.append(
            "<table><thead><tr><th>Blocked SID</th><th>Login</th><th>Host</th><th>Command</th><th>Wait Type</th><th>Wait (ms)</th><th>Resource</th></tr></thead><tbody>"
        )
        for row in rows:
            try:
                sid = int(row.get("session_id"))
            except (TypeError, ValueError):
                sid = -1
            depth = _depth_for_session(sid) if sid > 0 else 0
            chunks.append(
                "<tr>"
                f"<td style=\"padding-left: {depth * 16}px\">{_esc(row.get('session_id'))}</td>"
                f"<td>{_esc(row.get('login_name'))}</td>"
                f"<td>{_esc(row.get('host_name'))}</td>"
                f"<td>{_esc(row.get('command'))}</td>"
                f"<td>{_esc(row.get('wait_type'))}</td>"
                f"<td>{_esc(row.get('wait_time'))}</td>"
                f"<td>{_esc(wait_by_session.get(sid))}</td>"
                "</tr>"
            )
        chunks.append("</tbody></table></details>")
    chunks.append("</section>")
    return "".join(chunks)


def _html_recommendations(recommendations: list[dict[str, Any]]) -> str:
    cards: list[str] = []
    for rec in recommendations:
        priority = str(rec.get("priority", "info")).lower()
        cards.append(
            f"<div class=\"rec-card rec-{_esc(priority)}\"><strong>[{_esc(priority.upper())}]</strong> {_esc(rec.get('action'))}<div class=\"muted\">{_esc(rec.get('rationale'))}</div></div>"
        )
    return "<section class=\"card\" id=\"recommendations\"><h2>Recommendations</h2>" + "".join(cards) + "</section>"


def _html_footer(generated_at_utc: str) -> str:
    return (
        "<footer class=\"card muted\">"
        f"<small>MCP SQL Server - Generated {_esc(generated_at_utc)} - Point-in-time DMV snapshot.</small>"
        "</footer>"
    )


# ---------------------------------------------------------------------------
# Default (minimal) dashboard payload – used by non-app clients
# ---------------------------------------------------------------------------

def build_sessions_dashboard(
    *,
    instance_number: int,
    database_name: str,
    sessions: list[dict[str, Any]],
    lock_chains: list[dict[str, Any]],
) -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Full dashboard payload – all four DMV sections, interactive-app aligned
# ---------------------------------------------------------------------------

def build_sessions_dashboard_full(
    *,
    instance_number: int,
    database_name: str,
    sessions: list[dict[str, Any]],
    lock_chains: list[dict[str, Any]],
    tran_locks: list[dict[str, Any]],
    waiting_tasks: list[dict[str, Any]],
    head_blockers: list[int],
    blocking_chains: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the full dashboard payload aligned with DASHBOARD_STATE_SCHEMA.

    Sections:
    - sessions: active user sessions from sys.dm_exec_sessions + sys.dm_exec_requests
    - locks: active lock holders from sys.dm_tran_locks
    - blockers: waiting tasks from sys.dm_os_waiting_tasks (all waits, not just blocked)
    - head_blockers: session IDs that are the root cause of blocking chains
    - recommendations: prioritized mitigation guidance
    """
    recommendations: list[dict[str, Any]] = []
    if head_blockers:
        recommendations.append(
            {
                "priority": "high",
                "action": f"Kill or investigate head blocker session(s): {head_blockers[:5]}",
                "rationale": f"Detected {len(head_blockers)} unique head blocking session(s) causing wait chains.",
            }
        )
    long_waits = [
        w for w in waiting_tasks
        if (w.get("wait_duration_ms") or 0) > 5000
    ]
    if long_waits:
        recommendations.append(
            {
                "priority": "medium",
                "action": f"Review {len(long_waits)} task(s) with wait duration > 5 s.",
                "rationale": "Long-running waits indicate lock contention, I/O pressure, or resource exhaustion.",
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "priority": "info",
                "action": "No immediate blocking or long-wait issues detected.",
                "rationale": "All sessions within normal wait thresholds.",
            }
        )

    chain_rows = blocking_chains or []
    generated_at_utc = datetime.now(timezone.utc).isoformat()
    header = _html_header(
        instance_number=instance_number,
        database_name=database_name,
        generated_at_utc=generated_at_utc,
        session_count=len(sessions),
        lock_count=len(tran_locks),
        wait_count=len(waiting_tasks),
        chain_count=len(chain_rows),
    )

    html_doc = (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>Sessions Dashboard - Instance {instance_number}</title>"
        f"{_html_inline_styles()}"
        "</head><body><main class=\"page\">"
        f"{header}"
        f"{_html_sessions_table(sessions, head_blockers)}"
        f"{_html_chain_section(chain_rows, waiting_tasks)}"
        f"{_html_recommendations(recommendations)}"
        f"{_html_footer(generated_at_utc)}"
        "</main></body></html>"
    )

    return {
        "content_type": "text/html",
        "html": html_doc,
        "data": {
            "generated_at_utc": generated_at_utc,
            "instance_number": instance_number,
            "database_name": database_name,
            "ui_meta": {"loading": False, "error": None},
            "sessions": sessions,
            "locks": tran_locks,
            "blockers": waiting_tasks,
            "blocking_chains": chain_rows,
            "head_blockers": head_blockers,
            "recommendations": recommendations,
            "widgets": {
                "active_sessions": sessions,
                "lock_chains": lock_chains,
                "tran_locks": tran_locks,
                "waiting_tasks": waiting_tasks,
                "blocking_chains": chain_rows,
            },
        },
    }
