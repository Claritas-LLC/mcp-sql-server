import pytest

from src.tools.analysis_contracts import (
    build_finding,
    build_recommendation,
    build_report_envelope,
)
from src.tools.input_validation import (
    validate_database_name,
    validate_identifier,
    validate_positive_int,
    validate_view_mode,
)
from src.tools.model_graph import build_fk_graph
from src.tools.query_catalog import (
    disabled_indexes_query,
    duplicate_key_candidate_query,
    excessive_permissions_query,
    fragmented_indexes_query,
    fk_graph_query,
    guest_access_query,
    heap_tables_query,
    lock_chain_query,
    missing_fk_index_query,
    missing_pk_query,
    nullable_fk_columns_query,
    orphan_user_query,
    server_config_flags_query,
    stale_statistics_query,
    table_size_query,
    tables_without_fk_query,
    trustworthy_databases_query,
)
from src.tools.security_redaction import redact_sensitive_fields


def test_report_envelope_severity_counts() -> None:
    report = build_report_envelope(
        instance_number=1,
        database_name="master",
        tool_name="db_1_sql2019_analyze_tab_health",
        summary={"table_count_scanned": 10},
        findings=[
            {
                "code": "A",
                "severity": "high",
                "title": "A",
                "detail": "A",
                "evidence": [],
            },
            {
                "code": "B",
                "severity": "medium",
                "title": "B",
                "detail": "B",
                "evidence": [],
            },
        ],
        recommendations=[],
    )
    assert report["severity_counts"]["high"] == 1
    assert report["severity_counts"]["medium"] == 1
    assert report["severity_counts"]["critical"] == 0


def test_fk_graph_detects_cycle() -> None:
    graph = build_fk_graph(
        [
            {
                "fk_name": "fk_a_b",
                "parent_schema": "dbo",
                "parent_table": "A",
                "referenced_schema": "dbo",
                "referenced_table": "B",
            },
            {
                "fk_name": "fk_b_a",
                "parent_schema": "dbo",
                "parent_table": "B",
                "referenced_schema": "dbo",
                "referenced_table": "A",
            },
        ]
    )
    assert graph["edge_count"] == 2
    assert graph["node_count"] == 2
    assert "dbo.A" in graph["circular_dependency_tables"]
    assert "dbo.B" in graph["circular_dependency_tables"]


def test_redacts_sensitive_fields() -> None:
    rows = [{"login": "alice", "password_hash": "abc", "token_value": "xyz"}]
    redacted = redact_sensitive_fields(rows)
    assert redacted[0]["login"] == "alice"
    assert redacted[0]["password_hash"] == "***REDACTED***"
    assert redacted[0]["token_value"] == "***REDACTED***"


# ---------------------------------------------------------------------------
# Error-contract tests – input_validation
# ---------------------------------------------------------------------------


def test_validate_database_name_empty_raises_invalid_input() -> None:
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        validate_database_name("")


def test_validate_database_name_whitespace_raises_invalid_input() -> None:
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        validate_database_name("   ")


def test_validate_database_name_semicolon_raises_invalid_input() -> None:
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        validate_database_name("master; DROP TABLE foo--")


def test_validate_database_name_comment_raises_invalid_input() -> None:
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        validate_database_name("master -- comment")


def test_validate_database_name_valid_passes() -> None:
    assert validate_database_name("  master  ") == "master"


def test_validate_identifier_blank_raises() -> None:
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        validate_identifier("", "table_name")


def test_validate_identifier_injection_raises() -> None:
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        validate_identifier("Orders; DROP TABLE Orders--", "table_name")


def test_validate_positive_int_below_minimum_raises() -> None:
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        validate_positive_int(0, "top_n", 1, 500)


def test_validate_positive_int_above_maximum_raises() -> None:
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        validate_positive_int(501, "top_n", 1, 500)


def test_validate_positive_int_boundary_passes() -> None:
    assert validate_positive_int(1, "top_n", 1, 500) == 1
    assert validate_positive_int(500, "top_n", 1, 500) == 500


def test_validate_view_mode_invalid_raises() -> None:
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        validate_view_mode("SUMMARY")


def test_validate_view_mode_case_insensitive() -> None:
    assert validate_view_mode("full") == "FULL"
    assert validate_view_mode("Compact") == "COMPACT"


# ---------------------------------------------------------------------------
# Error-contract tests – analysis_contracts
# ---------------------------------------------------------------------------


def test_build_finding_invalid_severity_raises() -> None:
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        build_finding(code="X", severity="fatal", title="T", detail="D")


def test_build_recommendation_invalid_priority_raises() -> None:
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        build_recommendation(priority="urgent", action="fix it", rationale="yes")


def test_build_finding_valid_severities() -> None:
    for sev in ("critical", "high", "medium", "low", "info"):
        f = build_finding(code="C1", severity=sev, title="T", detail="D")
        assert f["severity"] == sev


def test_report_envelope_has_required_keys() -> None:
    report = build_report_envelope(
        instance_number=2,
        database_name="testdb",
        tool_name="db_2_sql2019_analyze_tab_health",
        summary={"table_count_scanned": 5},
        findings=[],
        recommendations=[],
    )
    for key in (
        "instance_number",
        "database_name",
        "tool",
        "generated_at_utc",
        "summary",
        "severity_counts",
        "findings",
        "recommendations",
    ):
        assert key in report, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# query_catalog – structural / pattern tests (no live DB required)
# ---------------------------------------------------------------------------


def test_table_size_query_contains_top_n() -> None:
    sql = table_size_query(20)
    assert "TOP 20" in sql
    assert "total_space_mb" in sql


def test_fragmented_indexes_query_structure() -> None:
    sql = fragmented_indexes_query(10)
    assert "TOP 10" in sql
    assert "avg_fragmentation_in_percent" in sql


def test_missing_pk_query_structure() -> None:
    sql = missing_pk_query()
    assert "key_constraints" in sql
    assert "IS NULL" in sql


def test_fk_graph_query_contains_foreign_keys() -> None:
    sql = fk_graph_query()
    assert "sys.foreign_keys" in sql
    assert "parent_table" in sql


def test_heap_tables_query_structure() -> None:
    sql = heap_tables_query()
    assert "index_id = 0" in sql


def test_disabled_indexes_query_structure() -> None:
    sql = disabled_indexes_query()
    assert "is_disabled = 1" in sql


def test_stale_statistics_query_top_n() -> None:
    sql = stale_statistics_query(15)
    assert "TOP 15" in sql
    assert "modification_counter" in sql


def test_duplicate_key_candidate_query_top_n() -> None:
    sql = duplicate_key_candidate_query(5)
    assert "TOP 5" in sql
    assert "index_count" in sql


def test_tables_without_fk_query_structure() -> None:
    sql = tables_without_fk_query()
    assert "NOT EXISTS" in sql
    assert "foreign_keys" in sql


def test_nullable_fk_columns_query_structure() -> None:
    sql = nullable_fk_columns_query()
    assert "is_nullable = 1" in sql
    assert "foreign_key_columns" in sql


def test_missing_fk_index_query_structure() -> None:
    sql = missing_fk_index_query()
    assert "NOT EXISTS" in sql
    assert "index_columns" in sql


def test_server_config_flags_query_contains_xp_cmdshell() -> None:
    sql = server_config_flags_query()
    assert "xp_cmdshell" in sql
    assert "sys.configurations" in sql


def test_trustworthy_databases_query_structure() -> None:
    sql = trustworthy_databases_query()
    assert "is_trustworthy_on = 1" in sql
    assert "msdb" in sql


def test_guest_access_query_structure() -> None:
    sql = guest_access_query()
    assert "guest" in sql
    assert "CONNECT" in sql


def test_excessive_permissions_query_top_n() -> None:
    sql = excessive_permissions_query(10)
    assert "TOP 10" in sql
    assert "explicit_grant_count" in sql


def test_orphan_user_query_structure() -> None:
    sql = orphan_user_query()
    assert "server_principals" in sql
    assert "sp.sid IS NULL" in sql


def test_lock_chain_query_top_n() -> None:
    sql = lock_chain_query(25)
    assert "TOP 25" in sql
    assert "blocking_session_id" in sql
