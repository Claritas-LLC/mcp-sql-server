from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from mcp_sqlserver import server as s


def main() -> None:
    audit_path = os.path.join("testing", "hardening_audit_smoke.jsonl")
    if os.path.exists(audit_path):
        os.remove(audit_path)

    s.SETTINGS.table_scope_enforced = True
    s._TABLE_SCOPE_PATTERNS = {"dbo.*"}

    denied = False
    try:
        s._enforce_table_scope_for_sql("SELECT TOP 1 name FROM sys.tables")
    except ValueError as exc:
        denied = True
        print("TABLE_SCOPE_DENY_OK", str(exc))

    if not denied:
        raise RuntimeError("Expected table scope deny did not occur")

    s.SETTINGS.rate_limit_enabled = True
    s.SETTINGS.rate_limit_window_seconds = 60
    s.SETTINGS.rate_limit_max_requests = 2
    s.SETTINGS.rate_limit_breaker_violations = 1
    s.SETTINGS.rate_limit_breaker_seconds = 5
    s._RATE_LIMIT_REQUESTS.clear()
    s._RATE_LIMIT_VIOLATIONS.clear()
    s._RATE_LIMIT_BLOCKED_UNTIL.clear()

    print("RATE1", s._rate_limit_check("smoke-client"))
    print("RATE2", s._rate_limit_check("smoke-client"))
    rate3 = s._rate_limit_check("smoke-client")
    print("RATE3", rate3)
    if rate3[0]:
        raise RuntimeError("Expected rate limit block on third request")

    s.SETTINGS.audit_log_queries = True
    s.SETTINGS.audit_log_file = audit_path
    s.SETTINGS.audit_log_include_params = False
    s.SETTINGS.allow_raw_prompts = True
    # Ensure instance 1 has a complete config shape so downstream access is safe.
    if 1 in s.SETTINGS.db_instances:
        s.SETTINGS.db_instances[1]["db_user"] = "readonly_user"
    else:
        template = next(iter(s.SETTINGS.db_instances.values()), {})
        s.SETTINGS.db_instances[1] = {
            "db_server": template.get("db_server", "127.0.0.1"),
            "db_port": template.get("db_port", 1433),
            "db_user": "readonly_user",
            "db_password": template.get("db_password", ""),
            "db_name": template.get("db_name", "TEST_DB"),
            "db_driver": template.get("db_driver", "ODBC Driver 17 for SQL Server"),
            "db_encrypt": template.get("db_encrypt", "no"),
            "db_trust_cert": template.get("db_trust_cert", "yes"),
        }
    s._write_query_audit_record(
        tool_name="db_sql2019_run_query",
        database_name="TEST_DB",
        sql="SELECT TOP 1 * FROM sales.Customers ORDER BY CreatedDate DESC, CustomerID DESC",
        params_json=None,
        prompt_context="User asked for latest customer row",
    )

    if not os.path.exists(audit_path):
        raise RuntimeError("Audit log file was not created")

    with open(audit_path, "r", encoding="utf-8") as handle:
        line = handle.readline().strip()
    payload = json.loads(line)

    if payload.get("prompt") != "User asked for latest customer row":
        raise RuntimeError("Prompt context missing from audit record")

    print("AUDIT_PROMPT_OK", payload.get("prompt"))
    print("SMOKE_OK")


if __name__ == "__main__":
    main()
