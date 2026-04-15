import asyncio
import pytest
from typing import Any

from mcp_sqlserver import server


pytestmark = pytest.mark.integration


def _call_tool(tool, *args, **kwargs) -> Any:
    fn = getattr(tool, "fn", None)
    if callable(fn):
        result = fn(*args, **kwargs)
    else:
        result = tool(*args, **kwargs)

    if asyncio.iscoroutine(result):
        return asyncio.run(result)
    return result


@pytest.fixture(autouse=True, scope="module")
def _require_db_connection(db_available):
    if not db_available:
        pytest.skip("database unavailable")
    return db_available


def test_list_databases_includes_test_db():
    databases = _call_tool(server.db_sql2019_list_databases, instance=1)

    def _extract_name(item: Any) -> str:
        if isinstance(item, dict):
            value = item.get("name") or item.get("NAME") or item.get("database") or item.get("DatabaseName")
            return value if isinstance(value, str) else ""
        return item if isinstance(item, str) else ""

    assert any(
        _extract_name(item).upper() == "TEST_DB"
        for item in databases.get("items", [])
    )


def test_list_tables_returns_sales_customers():
    tables = _call_tool(server.db_sql2019_list_tables, "TEST_DB", schema_name="sales", instance=1)
    assert any(row.get("TABLE_NAME") == "Customers" for row in tables.get("items", []))


def test_get_schema_returns_columns():
    schema = _call_tool(server.db_sql2019_get_schema, "TEST_DB", "Customers", "sales", instance=1)
    assert "columns" in schema
    assert any(col.get("COLUMN_NAME") == "CustomerID" for col in schema["columns"])


def test_execute_query_returns_rows():
    result = _call_tool(server.db_sql2019_execute_query, "TEST_DB", "SELECT TOP 2 * FROM sales.Customers", instance=1)
    assert isinstance(result, dict)
    assert isinstance(result.get("items", []), list)


def test_list_objects_tables():
    result = _call_tool(server.db_sql2019_list_objects, "TEST_DB", schema="sales", object_type="TABLE", instance=1)
    assert any(row.get("TABLE_NAME") == "Customers" for row in result.get("items", []))


def test_run_query_alias():
    result = _call_tool(server.db_sql2019_run_query, "TEST_DB", "SELECT TOP 1 * FROM sales.Customers", instance=1)
    assert isinstance(result, dict)
    assert isinstance(result.get("items", []), list)
    


def test_show_top_queries():
    result = _call_tool(server.db_sql2019_show_top_queries, "TEST_DB", instance=1)
    assert "database" in result
    assert "query_store_enabled" in result


def test_check_fragmentation():
    result = _call_tool(
        server.db_sql2019_check_fragmentation,
        "TEST_DB",
        min_fragmentation=0.0,
        min_page_count=1,
        include_recommendations=False,
        instance=1
    )
    assert "database" in result
    assert "fragmentation_summary" in result


def test_db_sec_perf_metrics():
    result = _call_tool(server.db_sql2019_db_sec_perf_metrics, profile="oltp", instance=1)
    assert result.get("profile") == "oltp"
    assert "security_assessment" in result
    assert "performance_metrics" in result


# --- New tests for db_02_sql2019_* tools (if configured) ---
import os
SECONDARY_ENABLED = bool(os.environ.get("DB_02_SERVER"))

import pytest

@pytest.mark.skipif(not SECONDARY_ENABLED, reason="Secondary instance not configured")
def test_db_02_list_databases():
    databases = _call_tool(server.db_sql2019_list_databases, instance=2)
    assert isinstance(databases, dict)
    assert "items" in databases

@pytest.mark.skipif(not SECONDARY_ENABLED, reason="Secondary instance not configured")
def test_db_02_ping():
    result = _call_tool(server.db_sql2019_ping, instance=2)
    assert result.get("status") == "ok"

## Removed tests for send_email and save_file_temp tools (tools no longer exist)
