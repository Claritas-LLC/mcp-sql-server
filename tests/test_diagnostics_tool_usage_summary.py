import json

from src.diagnostics.usage_summary import categorize_tool, summarize_audit_events


def test_categorize_tool() -> None:
    assert categorize_tool("db_primary_sql2019_exec_proc") == "controlled_write"
    assert categorize_tool("db_secondary_sql2019_top_queries_report") == "diagnostic"
    assert categorize_tool("db_1_sql2019_analyze_tab_health") == "analysis"
    assert categorize_tool("db_2_sql2019_sessions_dashboard") == "interactive"
    assert categorize_tool("db_primary_sql2019_select") == "read_only"


def test_summarize_audit_events(tmp_path) -> None:
    audit = tmp_path / "audit.log"
    rows = [
        {
            "tool": "db_primary_sql2019_select",
            "decision": "allow",
        },
        {
            "tool": "db_primary_sql2019_exec_proc",
            "decision": "deny",
        },
        {
            "tool": "db_secondary_sql2019_top_queries_report",
            "decision": "allow",
        },
    ]
    audit.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    summary = summarize_audit_events(audit)

    assert summary["events"] == 3
    assert summary["deny_total"] == 1
    assert summary["by_category"]["read_only"]["allow"] == 1
    assert summary["by_category"]["controlled_write"]["deny"] == 1
    assert summary["by_category"]["diagnostic"]["allow"] == 1
