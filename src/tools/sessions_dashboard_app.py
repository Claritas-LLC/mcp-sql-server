from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger

from src.tools.input_validation import validate_database_name, validate_positive_int
from src.tools.query_catalog import active_sessions_query, blocking_chain_query, lock_chain_query

logger = get_logger(__name__)


def register_sessions_dashboard_app_provider(mcp: FastMCP, state: Any) -> bool:
    """Register interactive sessions dashboard app provider.

    Returns True when provider registration succeeds. Returns False when
    interactive app dependencies are unavailable or initialization fails.
    """
    try:
        from fastmcp import FastMCPApp
        from prefab_ui.actions import ShowToast
        from prefab_ui.actions.mcp import CallTool
        from prefab_ui.app import PrefabApp
        from prefab_ui.components import Button, Column, Form, Heading, Input, Row, Select, SelectOption, Separator, Text, ForEach
    except Exception as exc:  # pragma: no cover - environment-specific optional deps
        logger.warning("Interactive app dependencies unavailable; sessions app provider disabled: %s", exc)
        return False

    app = FastMCPApp("SQL Sessions Dashboard")

    instance_ids = state.connection_manager.list_enabled_instances()
    number_by_instance = {idx: instance_id for idx, instance_id in enumerate(instance_ids, start=1)}
    available_instance_numbers = sorted(number_by_instance)

    @app.tool(description="Fetch sessions and lock-chain diagnostics for interactive dashboard")
    def fetch_sessions_dashboard_data(
        instance_number: int = 1,
        database_name: str = "master",
        lookback_minutes: int = 15,
        include_locks: bool = True,
        actor: str = "system",
    ) -> dict[str, Any]:
        request_id = f"app-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        db_name = validate_database_name(database_name)
        validate_positive_int(lookback_minutes, "lookback_minutes", 1, 1440)

        if instance_number not in number_by_instance:
            raise ValueError(f"INVALID_INPUT: instance_number must be one of {available_instance_numbers}")

        instance_id = number_by_instance[instance_number]

        state.session_manager.touch(actor, request_id)
        state.rate_limiter.allow(actor)
        state.write_guard.enforce("sessions_dashboard_app_fetch", "SELECT 1")

        sessions = state.connection_manager.execute_catalog_query(
            instance_id,
            db_name,
            active_sessions_query(200),
            200,
        )
        lock_rows = {"rows": []}
        blocking_chain_rows = {"rows": []}
        if include_locks:
            lock_rows = state.connection_manager.execute_catalog_query(
                instance_id,
                db_name,
                lock_chain_query(200),
                200,
            )
            blocking_chain_rows = state.connection_manager.execute_catalog_query(
                instance_id,
                db_name,
                blocking_chain_query(200),
                200,
            )

        head_blockers: list[int] = []
        for row in lock_rows["rows"]:
            blocker = row.get("blocking_session_id")
            if blocker is None:
                continue
            try:
                blocker_id = int(blocker)
            except (TypeError, ValueError):
                continue
            if blocker_id > 0 and blocker_id not in head_blockers:
                head_blockers.append(blocker_id)

        return {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "instance_number": instance_number,
            "database_name": db_name,
            "lookback_minutes": lookback_minutes,
            "active_sessions": sessions["rows"],
            "lock_chains": lock_rows["rows"],
            "blocking_chains": blocking_chain_rows["rows"],
            "head_blockers": head_blockers[:25],
            "recommendations": [
                {
                    "priority": "high" if head_blockers else "info",
                    "action": "Investigate head blockers and long wait chains."
                    if head_blockers
                    else "No immediate lock chain action required.",
                    "rationale": f"Detected {len(head_blockers)} unique blocking session(s).",
                }
            ],
        }

    @app.ui(
        title="SQL Sessions Dashboard",
        description="Open an interactive sessions dashboard for SQL Server diagnostics",
        name="sql2019_sessions_dashboard_app",
    )
    def sessions_dashboard_app():
        with Column(gap=6, css_class="p-6") as view:
            Heading("SQL Sessions Dashboard")
            Text("Interactive diagnostics for active sessions and lock chains.")

            with Form(
                on_submit=CallTool(
                    fetch_sessions_dashboard_data,
                    result_key="dashboard",
                    on_success=ShowToast("Dashboard refreshed", variant="success"),
                    on_error=ShowToast("Failed to refresh dashboard", variant="error"),
                )
            ):
                with Row(gap=3):
                    with Select(name="instance_number", label="Instance Number"):
                        for n in available_instance_numbers:
                            SelectOption(str(n), value=str(n))
                    Input(name="database_name", label="Database", value="master", required=True)
                    Input(name="lookback_minutes", label="Lookback Minutes", value="15", required=True)
                    with Select(name="include_locks", label="Include Locks"):
                        SelectOption("Yes", value="true")
                        SelectOption("No", value="false")
                Button("Refresh")

            Separator()
            Heading("Summary", level=3)
            Text("Instance: {dashboard.instance_number} | DB: {dashboard.database_name}")
            Text("Generated: {dashboard.generated_at_utc}")
            Text("Head blockers: {dashboard.head_blockers}")

            Separator()
            Heading("Active Sessions", level=3)
            with ForEach("dashboard.active_sessions") as sess:
                with Row(gap=2, align="center"):
                    Text("Session:")
                    Text(sess.session_id)
                    Text("Login:")
                    Text(sess.login_name)
                    Text("Wait:")
                    Text(sess.wait_type)

            Separator()
            Heading("Lock Chains", level=3)
            with ForEach("dashboard.lock_chains") as lock:
                with Row(gap=2, align="center"):
                    Text("Session:")
                    Text(lock.session_id)
                    Text("Blocking:")
                    Text(lock.blocking_session_id)
                    Text("Type:")
                    Text(lock.wait_type)

            Separator()
            Heading("Recommendations", level=3)
            with ForEach("dashboard.recommendations") as rec:
                with Row(gap=2, align="center"):
                    Text("Priority:")
                    Text(rec.priority)
                    Text("Action:")
                    Text(rec.action)

        initial_dashboard = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "instance_number": available_instance_numbers[0] if available_instance_numbers else "",
            "database_name": "master",
            "lookback_minutes": 15,
            "active_sessions": [],
            "lock_chains": [],
            "blocking_chains": [],
            "head_blockers": [],
            "recommendations": [
                {
                    "priority": "info",
                    "action": "Click Refresh to load dashboard data.",
                    "rationale": "No initial server-side fetch is performed.",
                }
            ],
        }

        return PrefabApp(view=view, state={"dashboard": initial_dashboard})

    mcp.add_provider(app)
    logger.info("Registered interactive sessions dashboard app provider")
    return True
