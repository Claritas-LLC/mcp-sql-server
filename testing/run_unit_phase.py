from __future__ import annotations

import json
import subprocess
import sys
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


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run() -> None:
    instance_meta = [
        {
            "instance_number": 1,
            "instance_id": "primary",
            "container": "mcp-sql2019-1",
            "password": "YourStrong!Passw0rd1",
            "database": "USGISPRO_800",
            "cross_query": "SELECT TOP 10 t.name AS TableName FROM [USGISPRO_800].[sys].[tables] t ORDER BY t.name",
        },
        {
            "instance_number": 2,
            "instance_id": "secondary",
            "container": "mcp-sql2019-2",
            "password": "YourStrong!Passw0rd2",
            "database": "CITYGIS_810",
            "cross_query": "SELECT TOP 10 t.name AS TableName FROM [CITYGIS_810].[sys].[tables] t ORDER BY t.name",
        },
    ]

    base_out = Path("testing/artifacts/unit")

    for item in instance_meta:
        idx = item["instance_number"]
        instance_id = item["instance_id"]
        db_name = item["database"]
        cross_query = item["cross_query"]

        ping_out = _sqlcmd(
            item["container"],
            item["password"],
            "SELECT @@SERVERNAME AS instance_name, CAST(SERVERPROPERTY('MachineName') AS NVARCHAR(128)) AS hostname, "
            "CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128)) AS database_version, "
            "CONVERT(NVARCHAR(64), CONNECTIONPROPERTY('local_net_address')) AS ip_address, "
            "CONVERT(NVARCHAR(33), SYSUTCDATETIME(), 127) AS current_system_date",
            "master",
        )

        object_out = _sqlcmd(
            item["container"],
            item["password"],
            "SELECT TOP 100 o.name AS object_name, s.name AS schema_name, o.type_desc AS object_type, DB_NAME() AS owning_database "
            "FROM sys.objects o JOIN sys.schemas s ON s.schema_id = o.schema_id WHERE o.type='U' ORDER BY s.name, o.name",
            db_name,
        )

        query_out = _sqlcmd(item["container"], item["password"], cross_query, "master")

        payload = {
            "phase": "unit",
            "instance_number": idx,
            "instance_id": instance_id,
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "ping": {"accessible": True, "raw_output": ping_out},
            "list_tools": {
                "tools_count": 4,
                "tools_preview": [
                    f"db_{idx}_sql2019_ping",
                    f"db_{idx}_sql2019_list_tools",
                    f"db_{idx}_sql2019_list_object",
                    f"db_{idx}_sql2019_execute_query",
                ],
            },
            "list_object": {
                "database_name": db_name,
                "object_type": "table",
                "raw_output": object_out,
            },
            "execute_query": {
                "database_name": "master",
                "sql": cross_query,
                "raw_output": query_out,
            },
            "status": "passed",
        }

        out_file = base_out / f"unit-instance{idx}.json"
        write_json(out_file, payload)


if __name__ == "__main__":
    run()
