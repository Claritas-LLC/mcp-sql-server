"""Unit and integration tests for the Sessions Dashboard payloads and app layer.

TASK-017: App state transitions and CallTool result shape validation.
TASK-018: Integration-level tests for dashboard payload structure and head_blockers derivation.
"""
from __future__ import annotations

import pytest

from src.tools.dashboard_payloads import (
    DASHBOARD_STATE_SCHEMA,
    build_sessions_dashboard,
    build_sessions_dashboard_full,
)
from src.tools.query_catalog import (
    active_sessions_query,
    blocking_chain_query,
    lock_chain_query,
    tran_locks_query,
    waiting_tasks_query,
)


# ---------------------------------------------------------------------------
# query_catalog – structural checks for new queries
# ---------------------------------------------------------------------------


def test_tran_locks_query_uses_dm_tran_locks() -> None:
    sql = tran_locks_query(50)
    assert "sys.dm_tran_locks" in sql
    assert "TOP 50" in sql
    assert "request_mode" in sql


def test_tran_locks_query_filters_grant_and_wait() -> None:
    sql = tran_locks_query(10)
    assert "GRANT" in sql
    assert "WAIT" in sql


def test_waiting_tasks_query_uses_dm_os_waiting_tasks() -> None:
    sql = waiting_tasks_query(30)
    assert "sys.dm_os_waiting_tasks" in sql
    assert "TOP 30" in sql
    assert "wait_duration_ms" in sql
    assert "resource_description" in sql


def test_waiting_tasks_query_no_blocking_filter() -> None:
    # waiting_tasks_query returns ALL waits, not just blocked tasks
    sql = waiting_tasks_query(10)
    assert "blocking_session_id IS NOT NULL" not in sql


def test_lock_chain_query_retains_blocking_filter() -> None:
    # lock_chain_query (for blocked-chain detection) should still filter
    sql = lock_chain_query(10)
    assert "blocking_session_id IS NOT NULL" in sql


def test_active_sessions_query_has_extended_columns() -> None:
    sql = active_sessions_query(10)
    assert "session_database_name" in sql
    assert "open_transaction_count" in sql


def test_blocking_chain_query_structure() -> None:
    sql = blocking_chain_query(20)
    assert "TOP 20" in sql
    assert "blocking_session_id" in sql
    assert "dm_exec_requests" in sql


# ---------------------------------------------------------------------------
# TASK-017 – dashboard_payloads unit tests
# ---------------------------------------------------------------------------


def test_build_sessions_dashboard_required_keys() -> None:
    result = build_sessions_dashboard(
        instance_number=1,
        database_name="master",
        sessions=[],
        lock_chains=[],
    )
    assert result["content_type"] == "text/html"
    assert "html" in result
    data = result["data"]
    assert "generated_at_utc" in data
    assert "widgets" in data
    assert "active_sessions" in data["widgets"]
    assert "lock_chains" in data["widgets"]


def test_build_sessions_dashboard_session_count_in_html() -> None:
    sessions = [{"session_id": 55}, {"session_id": 66}]
    result = build_sessions_dashboard(
        instance_number=2,
        database_name="mydb",
        sessions=sessions,
        lock_chains=[],
    )
    assert "2" in result["html"]
    assert "mydb" in result["html"]


def test_build_sessions_dashboard_full_required_sections() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="testdb",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[],
    )
    data = result["data"]
    for key in ("generated_at_utc", "instance_number", "database_name",
            "ui_meta", "sessions", "locks", "blockers", "blocking_chains", "head_blockers", "recommendations"):
        assert key in data, f"Missing section: {key}"


def test_build_sessions_dashboard_full_ui_meta_defaults() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="testdb",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[],
    )
    ui_meta = result["data"]["ui_meta"]
    assert ui_meta["loading"] is False
    assert ui_meta["error"] is None


def test_build_sessions_dashboard_full_head_blockers_passthrough() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="testdb",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[101, 202],
    )
    assert result["data"]["head_blockers"] == [101, 202]


def test_build_sessions_dashboard_full_recommendations_have_required_keys() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="testdb",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[],
    )
    for rec in result["data"]["recommendations"]:
        for k in ("priority", "action", "rationale"):
            assert k in rec, f"Recommendation missing key: {k}"


def test_build_sessions_dashboard_full_head_blocker_recommendation_generated() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="testdb",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[55, 66],
    )
    recs = result["data"]["recommendations"]
    high_recs = [r for r in recs if r["priority"] == "high"]
    assert high_recs, "Expected at least one high-priority recommendation for head blockers"
    assert "55" in high_recs[0]["action"] or "66" in high_recs[0]["action"]


def test_build_sessions_dashboard_full_long_wait_recommendation() -> None:
    waiting_tasks = [
        {"session_id": 10, "wait_duration_ms": 8000},
        {"session_id": 11, "wait_duration_ms": 100},
    ]
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="testdb",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=waiting_tasks,
        head_blockers=[],
    )
    recs = result["data"]["recommendations"]
    medium_recs = [r for r in recs if r["priority"] == "medium"]
    assert medium_recs, "Expected a medium-priority recommendation for long wait"


def test_build_sessions_dashboard_full_no_issues_info_recommendation() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="testdb",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[],
    )
    recs = result["data"]["recommendations"]
    info_recs = [r for r in recs if r["priority"] == "info"]
    assert info_recs, "Expected an info recommendation when no issues detected"


def test_build_sessions_dashboard_full_tran_locks_in_locks_section() -> None:
    tran_locks = [
        {"session_id": 33, "resource_type": "ROW", "request_mode": "X", "request_status": "GRANT", "request_owner_type": "TRANSACTION", "resource_database_id": 5, "resource_associated_entity_id": 12345},
    ]
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="testdb",
        sessions=[],
        lock_chains=[],
        tran_locks=tran_locks,
        waiting_tasks=[],
        head_blockers=[],
    )
    assert result["data"]["locks"] == tran_locks


def test_build_sessions_dashboard_full_waiting_tasks_in_blockers_section() -> None:
    waiting_tasks = [{"session_id": 7, "wait_duration_ms": 1000, "wait_type": "LCK_M_X"}]
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="testdb",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=waiting_tasks,
        head_blockers=[],
    )
    assert result["data"]["blockers"] == waiting_tasks


def test_build_sessions_dashboard_full_widgets_present() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="testdb",
        sessions=[{"session_id": 1}],
        lock_chains=[{"session_id": 1}],
        tran_locks=[{"session_id": 1}],
        waiting_tasks=[{"session_id": 1}],
        head_blockers=[],
    )
    widgets = result["data"]["widgets"]
    assert "active_sessions" in widgets
    assert "lock_chains" in widgets
    assert "tran_locks" in widgets
    assert "waiting_tasks" in widgets
    assert "blocking_chains" in widgets


# ---------------------------------------------------------------------------
# TASK-017 – DASHBOARD_STATE_SCHEMA structural validation
# ---------------------------------------------------------------------------


def test_dashboard_state_schema_required_fields_declared() -> None:
    required = DASHBOARD_STATE_SCHEMA.get("required", [])
    for field in ("generated_at_utc", "instance_number", "database_name",
                  "ui_meta", "sessions", "locks", "blockers", "blocking_chains", "head_blockers", "recommendations"):
        assert field in required, f"Schema missing required: {field}"


def test_dashboard_state_schema_sessions_is_array() -> None:
    sessions_prop = DASHBOARD_STATE_SCHEMA["properties"]["sessions"]
    assert sessions_prop["type"] == "array"


def test_dashboard_state_schema_locks_is_array() -> None:
    locks_prop = DASHBOARD_STATE_SCHEMA["properties"]["locks"]
    assert locks_prop["type"] == "array"


def test_dashboard_state_schema_head_blockers_items_integer() -> None:
    hb_prop = DASHBOARD_STATE_SCHEMA["properties"]["head_blockers"]
    assert hb_prop["items"]["type"] == "integer"


# ---------------------------------------------------------------------------
# TASK-018 – integration-level output contract tests
# ---------------------------------------------------------------------------


def test_full_payload_generated_at_utc_is_iso_format() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="testdb",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[],
    )
    ts = result["data"]["generated_at_utc"]
    # Should be parseable as ISO 8601 datetime
    from datetime import datetime
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None


def test_full_payload_head_blockers_is_list_of_ints() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="testdb",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[7, 42],
    )
    for hb in result["data"]["head_blockers"]:
        assert isinstance(hb, int)


def test_full_payload_html_contains_instance_and_db() -> None:
    result = build_sessions_dashboard_full(
        instance_number=2,
        database_name="WideWorldImporters",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[],
    )
    assert "2" in result["html"]
    assert "WideWorldImporters" in result["html"]


def test_full_payload_html_contains_sessions_table_values() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="master",
        sessions=[
            {
                "session_id": 55,
                "login_name": "sa",
                "host_name": "SVRA",
                "program_name": "SSMS",
                "status": "running",
                "session_database_name": "master",
                "open_transaction_count": 0,
                "command": "SELECT",
                "wait_type": None,
                "wait_time": None,
                "cpu_time": None,
                "blocking_session_id": None,
            }
        ],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[],
    )
    assert "55" in result["html"]
    assert ">sa<" in result["html"]


def test_full_payload_html_is_complete_document() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="master",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[],
    )
    assert result["html"].startswith("<!DOCTYPE html>")
    assert result["html"].endswith("</html>")


def test_full_payload_html_marks_blocked_row() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="master",
        sessions=[
            {
                "session_id": 10,
                "login_name": "app",
                "host_name": "host",
                "program_name": "client",
                "status": "suspended",
                "session_database_name": "master",
                "open_transaction_count": 1,
                "command": "UPDATE",
                "wait_type": "LCK_M_X",
                "wait_time": 1100,
                "cpu_time": 5,
                "blocking_session_id": 7,
            }
        ],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[],
    )
    assert "row-blocked" in result["html"]


def test_full_payload_html_marks_head_blocker_row() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="master",
        sessions=[
            {
                "session_id": 99,
                "login_name": "dba",
                "host_name": "adminhost",
                "program_name": "ssms",
                "status": "running",
                "session_database_name": "master",
                "open_transaction_count": 0,
                "command": "SELECT",
                "wait_type": None,
                "wait_time": 0,
                "cpu_time": 1,
                "blocking_session_id": None,
            }
        ],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[99],
    )
    assert "row-head-blocker" in result["html"]


def test_full_payload_html_escapes_script_in_session_fields() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="master",
        sessions=[
            {
                "session_id": 13,
                "login_name": "<script>alert(1)</script>",
                "host_name": "host",
                "program_name": "client",
                "status": "idle",
                "session_database_name": "master",
                "open_transaction_count": 0,
                "command": "SELECT",
                "wait_type": None,
                "wait_time": None,
                "cpu_time": None,
                "blocking_session_id": None,
            }
        ],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[],
    )
    assert "<script>alert(1)</script>" not in result["html"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result["html"]


def test_full_payload_html_contains_chain_section() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="master",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[{"session_id": 11, "resource_description": "KEY: 7:7205759404"}],
        head_blockers=[],
        blocking_chains=[
            {
                "session_id": 11,
                "blocking_session_id": 3,
                "wait_type": "LCK_M_S",
                "wait_time": 3200,
                "status": "suspended",
                "login_name": "api",
                "host_name": "appsvr",
                "command": "SELECT",
            }
        ],
    )
    assert 'id="chains"' in result["html"]
    assert "3200" in result["html"]


def test_full_payload_html_chain_section_empty_message() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="master",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[],
        blocking_chains=[],
    )
    assert "No blocking chains detected" in result["html"]


def test_full_payload_html_recommendations_contains_rec_high() -> None:
    result = build_sessions_dashboard_full(
        instance_number=1,
        database_name="master",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[5],
    )
    assert "rec-high" in result["html"]


def test_full_payload_instance_number_and_db_name_preserved() -> None:
    result = build_sessions_dashboard_full(
        instance_number=2,
        database_name="mydb",
        sessions=[],
        lock_chains=[],
        tran_locks=[],
        waiting_tasks=[],
        head_blockers=[],
    )
    assert result["data"]["instance_number"] == 2
    assert result["data"]["database_name"] == "mydb"
