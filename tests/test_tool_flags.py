from src.models import RuntimePolicy
from src.tools.tool_flags import is_tool_enabled


def test_tool_enabled_by_default() -> None:
    policy = RuntimePolicy(
        write_mode_default="deny",
        allowed_write_tools=[],
        blocked_sql_patterns=[],
        max_result_rows=5000,
        max_query_duration_ms=15000,
        instance_enable_flags={"primary": True, "secondary": True},
    )
    assert is_tool_enabled(policy, "primary", "top_queries_report") is True


def test_global_tool_flag_disables_tool() -> None:
    policy = RuntimePolicy(
        write_mode_default="deny",
        allowed_write_tools=[],
        blocked_sql_patterns=[],
        max_result_rows=5000,
        max_query_duration_ms=15000,
        instance_enable_flags={"primary": True, "secondary": True},
        tool_enable_flags={"top_queries_report": False},
    )
    assert is_tool_enabled(policy, "primary", "top_queries_report") is False


def test_instance_flag_overrides_global_flag() -> None:
    policy = RuntimePolicy(
        write_mode_default="deny",
        allowed_write_tools=[],
        blocked_sql_patterns=[],
        max_result_rows=5000,
        max_query_duration_ms=15000,
        instance_enable_flags={"primary": True, "secondary": True},
        tool_enable_flags={"exec_proc": False},
        instance_tool_enable_flags={"primary": {"exec_proc": True}},
    )
    assert is_tool_enabled(policy, "primary", "exec_proc") is True
    assert is_tool_enabled(policy, "secondary", "exec_proc") is False
