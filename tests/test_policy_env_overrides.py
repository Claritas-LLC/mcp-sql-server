import pytest

from src.config_loader import apply_auth_env_overrides, apply_policy_env_overrides
from src.models import AuthConfig
from src.models import RuntimePolicy


def _base_policy() -> RuntimePolicy:
    return RuntimePolicy(
        write_mode_default="deny",
        allowed_write_tools=["db_primary_sql2019_exec_proc"],
        blocked_sql_patterns=[r"(?i)\\b(drop|alter|truncate|create)\\b"],
        max_result_rows=5000,
        max_query_duration_ms=15000,
        instance_enable_flags={"primary": True, "secondary": True},
        tool_enable_flags={"top_queries_report": True},
        instance_tool_enable_flags={"secondary": {"exec_proc": False}},
    )


def test_apply_policy_env_overrides_global_and_instance() -> None:
    policy = _base_policy()
    overridden = apply_policy_env_overrides(
        policy,
        {
            "FASTMCP_TOOL_ENABLE_FLAGS_JSON": '{"top_queries_report": false, "active_sessions_report": true}',
            "FASTMCP_INSTANCE_TOOL_ENABLE_FLAGS_JSON": '{"primary": {"exec_proc": true}, "secondary": {"exec_proc": false}}',
        },
    )

    assert overridden.tool_enable_flags["top_queries_report"] is False
    assert overridden.tool_enable_flags["active_sessions_report"] is True
    assert overridden.instance_tool_enable_flags["primary"]["exec_proc"] is True


def test_apply_policy_env_overrides_no_values_returns_original() -> None:
    policy = _base_policy()
    overridden = apply_policy_env_overrides(policy, {})
    assert overridden == policy


def test_apply_policy_env_overrides_invalid_json_raises() -> None:
    policy = _base_policy()
    with pytest.raises(ValueError, match="FASTMCP_TOOL_ENABLE_FLAGS_JSON"):
        apply_policy_env_overrides(
            policy, {"FASTMCP_TOOL_ENABLE_FLAGS_JSON": "{bad-json"}
        )


def test_apply_policy_env_overrides_invalid_structure_raises() -> None:
    policy = _base_policy()
    with pytest.raises(ValueError, match="string keys to boolean values"):
        apply_policy_env_overrides(
            policy, {"FASTMCP_TOOL_ENABLE_FLAGS_JSON": '{"x": "yes"}'}
        )


def test_apply_auth_env_overrides_defaults_unchanged() -> None:
    auth = AuthConfig()
    overridden = apply_auth_env_overrides(auth, {})
    assert overridden.auth_mode == "disabled"
    assert overridden.pool_max_connections == 10
    assert overridden.pool_max_keepalive_connections == 10
    assert overridden.pool_timeout_seconds == 10


def test_apply_auth_env_overrides_with_values() -> None:
    auth = AuthConfig()
    overridden = apply_auth_env_overrides(
        auth,
        {
            "FASTMCP_AUTH_MODE": "azure_token_verifier",
            "FASTMCP_AZURE_TENANT_ID": "tenant-123",
            "FASTMCP_AZURE_CLIENT_ID": "client-123",
            "FASTMCP_AZURE_REQUIRED_SCOPES": "read, write",
            "FASTMCP_POOL_MAX_CONNECTIONS": "25",
            "FASTMCP_POOL_MAX_KEEPALIVE": "8",
            "FASTMCP_POOL_TIMEOUT_SECONDS": "12",
        },
    )

    assert overridden.auth_mode == "azure_token_verifier"
    assert overridden.azure_tenant_id == "tenant-123"
    assert overridden.azure_client_id == "client-123"
    assert overridden.azure_required_scopes == ["read", "write"]
    assert overridden.pool_max_connections == 25
    assert overridden.pool_max_keepalive_connections == 8
    assert overridden.pool_timeout_seconds == 12


def test_apply_auth_env_overrides_invalid_pool_raises() -> None:
    auth = AuthConfig()
    with pytest.raises(ValueError, match="FASTMCP_POOL_MAX_CONNECTIONS"):
        apply_auth_env_overrides(auth, {"FASTMCP_POOL_MAX_CONNECTIONS": "not-an-int"})
