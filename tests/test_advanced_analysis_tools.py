import pytest

from src.tools.analysis_contracts import (
    build_finding,
    build_recommendation,
    build_report_envelope,
    DBA_REVIEW_DISCLAIMER,
)
from src.tools.input_validation import (
    validate_database_name,
    validate_identifier,
    validate_positive_int,
    validate_view_mode,
)
from src.tools.model_graph import build_fk_graph
from src.tools.query_catalog import (
    database_statistics_settings_query,
    disabled_indexes_query,
    duplicate_key_candidate_query,
    excessive_permissions_query,
    fragmented_indexes_query,
    fk_graph_query,
    guest_access_query,
    heap_tables_query,
    lock_chain_query,
    missing_fk_index_query,
    missing_statistics_coverage_candidate_query,
    missing_pk_query,
    nullable_fk_columns_query,
    low_sampled_statistics_query,
    orphan_user_query,
    server_config_flags_query,
    stale_statistics_query,
    statistics_histogram_query,
    statistics_never_updated_query,
    table_size_query,
    tables_without_fk_query,
    top_statements_dmv_fallback_query,
    top_statements_object_pressure_query,
    top_statements_query_store_query,
    trustworthy_databases_query,
)
from src.tools.security_redaction import redact_sensitive_fields
from src.tools.sql_tools import (
    _classify_low_sample_statistics_row,
    _classify_stale_statistics_row,
    _recommend_top_statement_actions,
)


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
        validate_database_name("master; SELECT 1--")


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
        validate_identifier("Orders; SELECT 1--", "table_name")


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


def test_report_envelope_includes_disclaimer_when_recommendations_present() -> None:
    report = build_report_envelope(
        instance_number=1,
        database_name="testdb",
        tool_name="db_1_sql2019_analyze_tab_health",
        summary={"table_count_scanned": 3},
        findings=[],
        recommendations=[
            build_recommendation(
                priority="medium", action="Rebuild index", rationale="High fragmentation"
            ),
        ],
    )
    assert "disclaimer" in report
    assert report["disclaimer"] == DBA_REVIEW_DISCLAIMER


def test_report_envelope_omits_disclaimer_when_no_recommendations() -> None:
    report = build_report_envelope(
        instance_number=1,
        database_name="testdb",
        tool_name="db_1_sql2019_analyze_tab_health",
        summary={"table_count_scanned": 3},
        findings=[
            build_finding(code="F01", severity="info", title="OK", detail="All good"),
        ],
        recommendations=[],
    )
    assert "disclaimer" not in report


def test_disclaimer_text_matches_constant() -> None:
    report = build_report_envelope(
        instance_number=2,
        database_name="testdb",
        tool_name="db_2_sql2019_analyze_db_data_model",
        summary={},
        findings=[],
        recommendations=[
            build_recommendation(
                priority="low", action="Review FK", rationale="Missing index"
            ),
        ],
    )
    assert report["disclaimer"] == DBA_REVIEW_DISCLAIMER
    assert "database administrator" in report["disclaimer"]
    assert "DBA" in report["disclaimer"]


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
    assert "NOT EXISTS" in sql


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


def test_statistics_never_updated_query_top_n() -> None:
    sql = statistics_never_updated_query(7)
    assert "TOP 7" in sql
    assert "last_updated IS NULL" in sql


def test_low_sampled_statistics_query_structure() -> None:
    sql = low_sampled_statistics_query(9)
    assert "TOP 9" in sql
    assert "sample_ratio" in sql


def test_database_statistics_settings_query_structure() -> None:
    sql = database_statistics_settings_query()
    assert "is_auto_create_stats_on" in sql
    assert "is_auto_update_stats_on" in sql


def test_missing_statistics_coverage_candidate_query_structure() -> None:
    sql = missing_statistics_coverage_candidate_query(11)
    assert "TOP 11" in sql
    assert "usable_stats_count" in sql


def test_statistics_histogram_query_structure() -> None:
    sql = statistics_histogram_query("dbo", "Orders", "IX_Orders_CreatedAt")
    assert "dm_db_stats_histogram" in sql
    assert "OBJECT_ID('dbo.Orders')" in sql
    assert "IX_Orders_CreatedAt" in sql


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


def test_classify_stale_statistics_row_medium() -> None:
    row = {
        "schema_name": "dbo",
        "table_name": "Orders",
        "stat_name": "IX_Orders_Date",
        "rows": 10000,
        "modification_counter": 2500,
        "last_updated": "2026-05-01T00:00:00+00:00",
    }
    classified = _classify_stale_statistics_row(row)
    assert classified is not None
    assert classified["severity"] == "medium"
    assert classified["modification_ratio"] >= 0.2


def test_classify_stale_statistics_row_high() -> None:
    row = {
        "schema_name": "dbo",
        "table_name": "FactSales",
        "stat_name": "IX_FactSales_Date",
        "rows": 500000,
        "modification_counter": 200000,
        "last_updated": "2026-01-01T00:00:00+00:00",
    }
    classified = _classify_stale_statistics_row(row)
    assert classified is not None
    assert classified["severity"] == "high"


def test_classify_low_sample_statistics_row_high() -> None:
    row = {
        "schema_name": "dbo",
        "table_name": "FactSales",
        "stat_name": "IX_FactSales_Product",
        "rows": 250000,
        "rows_sampled": 1000,
    }
    classified = _classify_low_sample_statistics_row(row)
    assert classified is not None
    assert classified["severity"] == "high"
    assert classified["sample_ratio"] < 0.01


def test_classify_low_sample_statistics_row_none_when_healthy() -> None:
    row = {
        "schema_name": "dbo",
        "table_name": "Orders",
        "stat_name": "IX_Orders_Status",
        "rows": 12000,
        "rows_sampled": 6000,
    }
    classified = _classify_low_sample_statistics_row(row)
    assert classified is None


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


# ---------------------------------------------------------------------------
# top_statements – query builder structural tests
# ---------------------------------------------------------------------------


def test_top_statements_query_store_query_structure() -> None:
    sql = top_statements_query_store_query(20, 1440)
    assert "TOP 20" in sql
    assert "sys.query_store_query" in sql
    assert "sys.query_store_runtime_stats" in sql
    assert "weighted_avg_duration_us" in sql
    assert "execution_count" in sql
    assert "DATEADD(minute" in sql
    assert "SYSUTCDATETIME" in sql
    assert "ORDER BY weighted_avg_duration_us DESC" in sql


def test_top_statements_dmv_fallback_query_structure() -> None:
    sql = top_statements_dmv_fallback_query(15)
    assert "TOP 15" in sql
    assert "sys.dm_exec_query_stats" in sql
    assert "sys.dm_exec_sql_text" in sql
    assert "weighted_avg_duration_us" in sql
    assert "execution_count" in sql
    assert "query_sql_text" in sql
    assert "ORDER BY weighted_avg_duration_us DESC" in sql


def test_top_statements_object_pressure_query_structure() -> None:
    sql = top_statements_object_pressure_query(10)
    assert "TOP 10" in sql
    assert "sys.dm_db_partition_stats" in sql
    assert "user_scans" in sql
    assert "user_seeks" in sql
    assert "scan_ratio" in sql
    assert "ORDER BY scan_ratio DESC" in sql


# ---------------------------------------------------------------------------
# top_statements – recommendation engine tests
# ---------------------------------------------------------------------------


def test_recommend_empty_statements_produces_no_findings() -> None:
    findings, recs = _recommend_top_statement_actions([], [])
    assert findings == []
    assert recs == []


def test_recommend_high_duration_triggers_finding() -> None:
    stmt_rows = [
        {
            "query_id": 1,
            "weighted_avg_duration_us": 6000000,
            "execution_count": 50,
            "query_sql_text": "SELECT * FROM Orders WHERE ...",
        }
    ]
    findings, recs = _recommend_top_statement_actions(stmt_rows, [])
    codes = [f["code"] for f in findings]
    assert "TOP_STMT_HIGH_DURATION" in codes
    assert any("index" in r["action"].lower() or "scan" in r["action"].lower() for r in recs)


def test_recommend_high_execution_count_triggers_finding() -> None:
    stmt_rows = [
        {
            "query_id": 2,
            "weighted_avg_duration_us": 500000,
            "execution_count": 50000,
            "query_sql_text": "EXEC dbo.LookupCustomer @id",
        }
    ]
    findings, recs = _recommend_top_statement_actions(stmt_rows, [])
    codes = [f["code"] for f in findings]
    assert "TOP_STMT_HIGH_EXECUTION_COUNT" in codes
    assert any("parameter" in r["action"].lower() for r in recs)


def test_recommend_high_scan_pressure_triggers_finding() -> None:
    obj_rows = [
        {
            "schema_name": "dbo",
            "table_name": "BigTable",
            "user_seeks": 10,
            "user_scans": 500,
            "scan_ratio": 0.98,
            "row_count": 1000000,
        }
    ]
    findings, recs = _recommend_top_statement_actions([], obj_rows)
    codes = [f["code"] for f in findings]
    assert "TOP_STMT_HIGH_SCAN_PRESSURE" in codes
    assert any("index" in r["action"].lower() for r in recs)


def test_recommend_large_table_triggers_partition_candidate() -> None:
    obj_rows = [
        {
            "schema_name": "dbo",
            "table_name": "FactSales",
            "user_seeks": 1000,
            "user_scans": 100,
            "scan_ratio": 0.09,
            "row_count": 15000000,
        }
    ]
    findings, recs = _recommend_top_statement_actions([], obj_rows)
    codes = [f["code"] for f in findings]
    assert "TOP_STMT_LARGE_TABLE_CANDIDATE" in codes
    assert any("partition" in r["action"].lower() for r in recs)


def test_recommend_medium_duration_triggers_rewrite_hint() -> None:
    stmt_rows = [
        {
            "query_id": 5,
            "weighted_avg_duration_us": 2500000,
            "execution_count": 200,
            "query_sql_text": "SELECT ... FROM ... JOIN ...",
        }
    ]
    findings, recs = _recommend_top_statement_actions(stmt_rows, [])
    codes = [f["code"] for f in findings]
    assert "TOP_STMT_REWRITE_CANDIDATE" in codes
    assert any("hint" in r["action"].lower() or "rewrite" in r["action"].lower() for r in recs)


def test_recommend_low_duration_no_op() -> None:
    stmt_rows = [
        {
            "query_id": 10,
            "weighted_avg_duration_us": 500000,
            "execution_count": 10,
            "query_sql_text": "SELECT TOP 1 ...",
        }
    ]
    findings, recs = _recommend_top_statement_actions(stmt_rows, [])
    codes = [f["code"] for f in findings]
    assert "TOP_STMT_HIGH_DURATION" not in codes
    assert "TOP_STMT_HIGH_EXECUTION_COUNT" not in codes
