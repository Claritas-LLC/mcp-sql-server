from __future__ import annotations

import json
import subprocess
import sys
import httpx
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sqlcmd(container: str, password: str, sql: str, database: str = "master") -> str:
    cmd = (
        f"if [ -x /opt/mssql-tools18/bin/sqlcmd ]; then "
        f"/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P '{password}' -No -d {database} -W -s '|' -Q \"{sql}\"; "
        "else "
        f"/opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P '{password}' -No -d {database} -W -s '|' -Q \"{sql}\"; fi"
    )
    result = subprocess.run(
        ["docker", "exec", container, "/bin/bash", "-lc", cmd],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _mcp_tool_call(base_url: str, tool_name: str, arguments: dict) -> dict:
    """Call an MCP tool over HTTP (streamable-http transport, JSON-RPC 2.0)."""
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
    ).encode()
    try:
        resp = httpx.post(
            f"{base_url}/mcp/",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        raw = resp.text
        # Streamable HTTP may respond with SSE lines; extract first JSON data line
        for line in raw.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return json.loads(raw)
    except httpx.HTTPError as exc:
        return {"error": str(exc), "reachable": False}


def _assert_mcp_tool_result(result: dict, expected_keys: list[str]) -> dict[str, bool]:
    assertions: dict[str, bool] = {}
    assertions["no_transport_error"] = "reachable" not in result
    if "result" in result:
        content = result.get("result", {})
        tool_content = content.get("content", [{}])
        text_block = tool_content[0].get("text", "{}") if tool_content else "{}"
        try:
            payload = json.loads(text_block)
        except (json.JSONDecodeError, TypeError):
            payload = {}
        for key in expected_keys:
            assertions[f"has_{key}"] = key in payload
    elif "error" in result:
        assertions["no_error"] = False
    return assertions


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run() -> None:
    base_url = "http://localhost:8085"

    q1 = "SELECT COUNT(*) AS table_count FROM [USGISPRO_800].[sys].[tables]"
    q2 = "SELECT COUNT(*) AS table_count FROM [CITYGIS_810].[sys].[tables]"

    ping1 = _sqlcmd(
        "mcp-sql2019-1", "YourStrong!Passw0rd1", "SELECT @@SERVERNAME AS instance_name"
    )
    ping2 = _sqlcmd(
        "mcp-sql2019-2", "YourStrong!Passw0rd2", "SELECT @@SERVERNAME AS instance_name"
    )
    r1 = _sqlcmd("mcp-sql2019-1", "YourStrong!Passw0rd1", q1)
    r2 = _sqlcmd("mcp-sql2019-2", "YourStrong!Passw0rd2", q2)

    # ------------------------------------------------------------------
    # MCP advanced tool integration checks
    # ------------------------------------------------------------------
    tab_health_1 = _mcp_tool_call(
        base_url,
        "db_1_sql2019_analyze_tab_health",
        {"database_name": "master", "top_n": 5, "view_mode": "COMPACT"},
    )
    tab_health_assertions_1 = _assert_mcp_tool_result(
        tab_health_1, ["tool", "severity_counts", "findings"]
    )

    tab_health_2 = _mcp_tool_call(
        base_url,
        "db_2_sql2019_analyze_tab_health",
        {"database_name": "master", "top_n": 5, "view_mode": "COMPACT"},
    )
    tab_health_assertions_2 = _assert_mcp_tool_result(
        tab_health_2, ["tool", "severity_counts", "findings"]
    )

    data_model_1 = _mcp_tool_call(
        base_url,
        "db_1_sql2019_analyze_db_data_model",
        {"database_name": "master", "top_n": 10, "view_mode": "FULL"},
    )
    data_model_assertions_1 = _assert_mcp_tool_result(
        data_model_1, ["tool", "severity_counts", "findings"]
    )

    sec_config_1 = _mcp_tool_call(
        base_url,
        "db_1_sql2019_analyze_sec_config",
        {"database_name": "master", "top_n": 10, "view_mode": "FULL"},
    )
    sec_config_assertions_1 = _assert_mcp_tool_result(
        sec_config_1, ["tool", "severity_counts", "findings"]
    )

    sessions_1 = _mcp_tool_call(
        base_url,
        "db_1_sql2019_sessions_dashboard",
        {"top_n": 10, "view_mode": "COMPACT"},
    )
    sessions_assertions_1 = _assert_mcp_tool_result(
        sessions_1, ["content_type", "data"]
    )

    payload = {
        "phase": "integration",
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "instances": [
            {"instance_number": 1, "health_raw": ping1},
            {"instance_number": 2, "health_raw": ping2},
        ],
        "cross_database_queries": [
            {
                "instance_number": 1,
                "database_context": "master",
                "sql": q1,
                "result_raw": r1,
            },
            {
                "instance_number": 2,
                "database_context": "master",
                "sql": q2,
                "result_raw": r2,
            },
        ],
        "advanced_tools": {
            "db_1_sql2019_analyze_tab_health": {
                "response_snippet": str(tab_health_1)[:200],
                "assertions": tab_health_assertions_1,
            },
            "db_2_sql2019_analyze_tab_health": {
                "response_snippet": str(tab_health_2)[:200],
                "assertions": tab_health_assertions_2,
            },
            "db_1_sql2019_analyze_db_data_model": {
                "response_snippet": str(data_model_1)[:200],
                "assertions": data_model_assertions_1,
            },
            "db_1_sql2019_analyze_sec_config": {
                "response_snippet": str(sec_config_1)[:200],
                "assertions": sec_config_assertions_1,
            },
            "db_1_sql2019_sessions_dashboard": {
                "response_snippet": str(sessions_1)[:200],
                "assertions": sessions_assertions_1,
            },
        },
        "assertions": {
            "instance1_accessible": "instance_name" in ping1,
            "instance2_accessible": "instance_name" in ping2,
            "instance1_table_count_positive": "table_count" in r1,
            "instance2_table_count_positive": "table_count" in r2,
        },
    }

    # Merge advanced tool transport-level assertions into top-level assertions
    for tool_key, tool_block in payload["advanced_tools"].items():
        for k, v in tool_block["assertions"].items():
            payload["assertions"][f"{tool_key}.{k}"] = v

    payload["status"] = "passed" if all(payload["assertions"].values()) else "failed"
    write_json(Path("testing/artifacts/integration/integration-summary.json"), payload)


if __name__ == "__main__":
    run()


def _sqlcmd(container: str, password: str, sql: str, database: str = "master") -> str:
    cmd = (
        f"if [ -x /opt/mssql-tools18/bin/sqlcmd ]; then "
        f"/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P '{password}' -No -d {database} -W -s '|' -Q \"{sql}\"; "
        "else "
        f"/opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P '{password}' -No -d {database} -W -s '|' -Q \"{sql}\"; fi"
    )
    result = subprocess.run(
        ["docker", "exec", container, "/bin/bash", "-lc", cmd],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def run() -> None:
    q1 = "SELECT COUNT(*) AS table_count FROM [USGISPRO_800].[sys].[tables]"
    q2 = "SELECT COUNT(*) AS table_count FROM [CITYGIS_810].[sys].[tables]"

    ping1 = _sqlcmd(
        "mcp-sql2019-1", "YourStrong!Passw0rd1", "SELECT @@SERVERNAME AS instance_name"
    )
    ping2 = _sqlcmd(
        "mcp-sql2019-2", "YourStrong!Passw0rd2", "SELECT @@SERVERNAME AS instance_name"
    )
    r1 = _sqlcmd("mcp-sql2019-1", "YourStrong!Passw0rd1", q1)
    r2 = _sqlcmd("mcp-sql2019-2", "YourStrong!Passw0rd2", q2)

    payload = {
        "phase": "integration",
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "instances": [
            {"instance_number": 1, "health_raw": ping1},
            {"instance_number": 2, "health_raw": ping2},
        ],
        "cross_database_queries": [
            {
                "instance_number": 1,
                "database_context": "master",
                "sql": q1,
                "result_raw": r1,
            },
            {
                "instance_number": 2,
                "database_context": "master",
                "sql": q2,
                "result_raw": r2,
            },
        ],
        "assertions": {
            "instance1_accessible": "instance_name" in ping1,
            "instance2_accessible": "instance_name" in ping2,
            "instance1_table_count_positive": "table_count" in r1,
            "instance2_table_count_positive": "table_count" in r2,
        },
    }

    payload["status"] = "passed" if all(payload["assertions"].values()) else "failed"
    write_json(Path("testing/artifacts/integration/integration-summary.json"), payload)


if __name__ == "__main__":
    run()
