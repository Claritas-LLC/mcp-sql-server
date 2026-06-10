import pytest

from src.middleware.write_guard import WriteGuard
from src.models import RuntimePolicy

EXPANDED_DENYLIST = [
    r"(?i)\b(drop|alter|truncate|create|insert|update|delete|merge|grant|revoke|deny)\b"
]


def _guard() -> WriteGuard:
    policy = RuntimePolicy(
        write_mode_default="deny",
        allowed_write_tools=["db_primary_sql2019_exec_proc"],
        blocked_sql_patterns=EXPANDED_DENYLIST,
        max_result_rows=5000,
        max_query_duration_ms=15000,
        instance_enable_flags={"primary": True, "secondary": True},
    )
    return WriteGuard(policy)


# ---------------------------------------------------------------------------
# Verb-based write check tests (non-allowlisted tools still block write verbs)
# ---------------------------------------------------------------------------


def test_denies_non_allowlisted_write() -> None:
    guard = _guard()
    with pytest.raises(PermissionError):
        guard.enforce("db_primary_sql2019_select", "EXEC dbo.usp_RunApprovedMaintenance")


def test_allows_allowlisted_write_tool() -> None:
    guard = _guard()
    guard.enforce("db_primary_sql2019_exec_proc", "EXEC dbo.usp_RunApprovedMaintenance")


# ---------------------------------------------------------------------------
# Denylist (regex) tests — DDL patterns
# ---------------------------------------------------------------------------


def test_denies_ddl_pattern() -> None:
    guard = _guard()
    with pytest.raises(PermissionError):
        guard.enforce("db_primary_sql2019_exec_proc", "DROP TABLE dbo.X")


def test_denies_exec_for_non_allowlisted_tool() -> None:
    guard = _guard()
    with pytest.raises(PermissionError):
        guard.enforce(
            "db_1_sql2019_execute_query", "EXEC USGISPRO_800.dbo.gisadmin_GetActiveCompanies"
        )


def test_allows_exec_for_allowlisted_write_tool() -> None:
    guard = _guard()
    guard.enforce("db_primary_sql2019_exec_proc", "EXEC dbo.usp_RunApprovedMaintenance")


def test_denies_execute_keyword_for_non_allowlisted_tool() -> None:
    guard = _guard()
    with pytest.raises(PermissionError):
        guard.enforce("db_1_sql2019_execute_query", "EXECUTE dbo.usp_RunApprovedMaintenance")


# ---------------------------------------------------------------------------
# Denylist (regex) tests — DML/DCL patterns (TASK-005, TASK-008)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql,keyword",
    [
        ("INSERT INTO t VALUES(1)", "INSERT"),
        ("UPDATE t SET x=1", "UPDATE"),
        ("DELETE FROM t", "DELETE"),
        ("MERGE t USING s ON t.id = s.id WHEN MATCHED THEN UPDATE SET x=1", "MERGE"),
        ("GRANT SELECT TO user", "GRANT"),
        ("REVOKE SELECT FROM user", "REVOKE"),
        ("DENY SELECT TO user", "DENY"),
    ],
)
def test_denies_dml_dcl_patterns_for_all_tools(sql: str, keyword: str) -> None:
    """Each DML/DCL keyword must be blocked by denylist for ALL tools, including exec_proc."""
    guard = _guard()
    with pytest.raises(PermissionError):
        guard.enforce("db_primary_sql2019_exec_proc", sql)


def test_write_probe_with_update_is_blocked() -> None:
    """Regression: the old UPDATE-based probe must be blocked by the expanded denylist."""
    guard = _guard()
    with pytest.raises(PermissionError):
        guard.enforce("db_primary_sql2019_exec_proc", "UPDATE __policy_probe__ SET x = 1")


# ---------------------------------------------------------------------------
# exec_proc EXEC-based probe test (TASK-007)
# ---------------------------------------------------------------------------


def test_exec_proc_probe_uses_exec_not_update() -> None:
    """The new EXEC-based probe must pass enforce() for allowlisted tools."""
    guard = _guard()
    guard.enforce("db_primary_sql2019_exec_proc", "EXEC __policy_probe__")


# ---------------------------------------------------------------------------
# False-positive avoidance (TASK-010)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT GrantID FROM t",
        "SELECT UpdateDate FROM t",
        "SELECT InsertedAt FROM t",
        "SELECT DeletedFlag FROM audit_log",
        "SELECT MergeKey FROM staging",
        "SELECT RevokedBy FROM permissions",
        "SELECT DenyReason FROM access_control",
    ],
)
def test_false_positives_avoided(sql: str) -> None:
    """Keywords embedded in identifiers must NOT trigger the denylist."""
    guard = _guard()
    guard.enforce("db_primary_sql2019_select", sql)
