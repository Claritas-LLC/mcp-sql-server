import pytest

from src.middleware.write_guard import WriteGuard
from src.models import RuntimePolicy


def _guard() -> WriteGuard:
    policy = RuntimePolicy(
        write_mode_default="deny",
        allowed_write_tools=["db_primary_sql2019_exec_proc"],
        blocked_sql_patterns=[r"(?i)\b(drop|alter|truncate|create)\b"],
        max_result_rows=5000,
        max_query_duration_ms=15000,
        instance_enable_flags={"primary": True, "secondary": True},
    )
    return WriteGuard(policy)


def test_denies_non_allowlisted_write() -> None:
    guard = _guard()
    with pytest.raises(PermissionError):
        guard.enforce("db_primary_sql2019_select", "UPDATE dbo.Users SET IsActive = 0")


def test_allows_allowlisted_write_tool() -> None:
    guard = _guard()
    guard.enforce("db_primary_sql2019_exec_proc", "UPDATE dbo.Users SET IsActive = 0")


def test_denies_ddl_pattern() -> None:
    guard = _guard()
    with pytest.raises(PermissionError):
        guard.enforce("db_primary_sql2019_exec_proc", "DROP TABLE dbo.X")
