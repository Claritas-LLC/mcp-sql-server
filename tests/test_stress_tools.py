import concurrent.futures
import os
import sys

import pytest

import server


def _call_tool(tool, *args, **kwargs):
    fn = getattr(tool, "fn", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return tool(*args, **kwargs)


def _run_query():
    return _call_tool(
        server.db_sql2019_execute_query,
        "TEST_DB",
        "SELECT TOP 1 * FROM sales.Customers"
    )


@pytest.fixture(autouse=True, scope="module")
def _require_db_connection():
    if sys.platform == "win32" and os.getenv("MCP_RUN_STRESS_WINDOWS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        pytest.skip("Stress tests are disabled on Windows by default due intermittent pyodbc access violations. Set MCP_RUN_STRESS_WINDOWS=true to force run.")

    try:
        conn = server.get_connection("master")
        conn.close()
    except Exception as exc:
        pytest.skip(f"Stress DB is unavailable: {exc}")


def test_concurrent_queries():
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_run_query) for _ in range(25)]
        results = [future.result() for future in futures]

    assert all(isinstance(result, dict) for result in results)
    assert all(isinstance(result.get("items", []), list) for result in results)
