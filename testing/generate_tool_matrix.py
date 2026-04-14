import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_sqlserver import server


READ_ONLY_SUFFIXES = {
    "ping",
    "list_databases",
    "list_tables",
    "get_schema",
    "execute_query",
    "run_query",
    "list_objects",
    "index_fragmentation",
    "index_health",
    "table_health",
    "db_stats",
    "server_info_mcp",
    "show_top_queries",
    "check_fragmentation",
    "db_sec_perf_metrics",
    "explain_query",
    "analyze_logical_data_model",
    "open_logical_model",
    "generate_ddl",
}


ARG_TEMPLATES = {
    "list_tables": {"database_name": "TEST_DB", "schema_name": "sales"},
    "get_schema": {"database_name": "TEST_DB", "table_name": "Customers", "schema_name": "sales"},
    "execute_query": {"database_name": "TEST_DB", "sql": "SELECT TOP 5 CustomerID, FirstName, LastName FROM sales.Customers ORDER BY CustomerID"},
    "run_query": {"arg1": "TEST_DB", "arg2": "SELECT TOP 5 ProductID, ProductName FROM sales.Products ORDER BY ProductID"},
    "list_objects": {"database_name": "TEST_DB", "object_type": "TABLE", "schema": "sales", "limit": 20},
    "index_fragmentation": {"database_name": "TEST_DB", "schema": "sales", "min_fragmentation": 0.0, "min_page_count": 1, "limit": 20},
    "index_health": {"database_name": "TEST_DB", "schema": "sales", "min_fragmentation": 0.0, "min_page_count": 1, "limit": 20},
    "table_health": {"database_name": "TEST_DB", "schema": "sales", "table_name": "Customers", "view": "standard"},
    "db_stats": {"database": "TEST_DB"},
    "show_top_queries": {"database_name": "TEST_DB", "view": "summary"},
    "check_fragmentation": {"database_name": "TEST_DB", "schema_name": "sales", "table_name": "Customers"},
    "db_sec_perf_metrics": {"database_name": "TEST_DB"},
    "explain_query": {"database_name": "TEST_DB", "sql": "SELECT TOP 5 * FROM sales.Customers"},
    "analyze_logical_data_model": {"database_name": "TEST_DB", "schema": "sales", "view": "summary"},
    "open_logical_model": {"database_name": "TEST_DB", "schema": "sales"},
    "generate_ddl": {"database_name": "TEST_DB", "schema_name": "sales", "table_name": "Customers"},
    "create_db_user": {"database_name": "TEST_DB", "username": "mcp_tmp_user", "password": "McpTempPwd123!"},
    "drop_db_user": {"database_name": "TEST_DB", "username": "mcp_tmp_user"},
    "kill_session": {"session_id": 0},
    "create_object": {"database_name": "TEST_DB", "sql": "CREATE TABLE sales.MCP_TMP_TABLE (Id INT PRIMARY KEY, Name NVARCHAR(50) NULL)"},
    "alter_object": {"database_name": "TEST_DB", "sql": "ALTER TABLE sales.MCP_TMP_TABLE ADD CreatedAt DATETIME2 NULL"},
    "drop_object": {"database_name": "TEST_DB", "sql": "DROP TABLE sales.MCP_TMP_TABLE"},
}


async def main() -> None:
    tools = await server.mcp.list_tools()
    names = sorted(t.name for t in tools)

    items = []
    for tool in sorted(tools, key=lambda t: t.name):
        name = tool.name
        suffix = name.split("_", 2)[2]
        classification = "read" if suffix in READ_ONLY_SUFFIXES else "write"
        params_schema = tool.parameters if isinstance(tool.parameters, dict) else {}
        param_props = params_schema.get("properties", {})

        items.append(
            {
                "tool_name": name,
                "suffix": suffix,
                "classification": classification,
                "args_template": ARG_TEMPLATES.get(suffix, {}),
                "param_names": sorted(param_props.keys()),
                "required_params": params_schema.get("required", []),
                "parameters_schema": params_schema,
            }
        )

    by_instance = {
        "db_01": [x for x in items if x["tool_name"].startswith("db_01_")],
        "db_02": [x for x in items if x["tool_name"].startswith("db_02_")],
    }

    out = {
        "generated_at_utc": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        "total_tools": len(items),
        "db_01_count": len(by_instance["db_01"]),
        "db_02_count": len(by_instance["db_02"]),
        "expected_total": len(by_instance["db_01"]) * 2,
        "matrix": items,
    }

    if out["db_01_count"] != out["db_02_count"]:
        raise SystemExit("Tool count mismatch between db_01 and db_02")
    if out["total_tools"] != out["expected_total"]:
        raise SystemExit("Total tool count mismatch")

    target = Path("testing/tool_matrix.json")
    target.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {target} with {out['total_tools']} tools")


if __name__ == "__main__":
    asyncio.run(main())
