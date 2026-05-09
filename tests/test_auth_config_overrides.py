import pytest

from src.config_loader import apply_auth_env_overrides, apply_instance_env_overrides
from src.models import AuthConfig, SqlInstanceConfig


def _base_instance() -> SqlInstanceConfig:
    return SqlInstanceConfig(
        id="primary",
        host="localhost",
        database="master",
        auth_secret_ref="secret/sql/primary",
    )


def test_auth_toggle_and_group_overrides_parse() -> None:
    auth = AuthConfig()
    overridden = apply_auth_env_overrides(
        auth,
        {
            "FASTMCP_AZURE_AUTH_ENABLED": "true",
            "FASTMCP_AZURE_GROUP_AUTHORIZATION_ENABLED": "false",
            "FASTMCP_AZURE_READ_GROUPS": "group-a, group-b",
            "FASTMCP_AZURE_WRITE_GROUPS": "group-c",
        },
    )

    assert overridden.azure_auth_enabled is True
    assert overridden.azure_group_authorization_enabled is False
    assert overridden.azure_read_groups == ["group-a", "group-b"]
    assert overridden.azure_write_groups == ["group-c"]


def test_auth_toggle_invalid_bool_raises() -> None:
    auth = AuthConfig()
    with pytest.raises(ValueError, match="FASTMCP_AZURE_AUTH_ENABLED"):
        apply_auth_env_overrides(auth, {"FASTMCP_AZURE_AUTH_ENABLED": "maybe"})


def test_instance_pool_env_overrides_apply_to_all_instances() -> None:
    instances = [
        _base_instance(),
        SqlInstanceConfig(
            id="secondary",
            host="localhost",
            database="master",
            auth_secret_ref="secret/sql/secondary",
        ),
    ]

    overridden = apply_instance_env_overrides(
        instances,
        {
            "FASTMCP_SQL_POOL_ENABLED": "false",
            "FASTMCP_SQL_POOL_MAX": "25",
            "FASTMCP_SQL_POOL_IDLE_TIMEOUT_SEC": "120",
            "FASTMCP_SQL_POOL_ACQUIRE_TIMEOUT_SEC": "7",
        },
    )

    assert all(i.pool_enabled is False for i in overridden)
    assert all(i.pool_max == 25 for i in overridden)
    assert all(i.pool_idle_timeout_sec == 120 for i in overridden)
    assert all(i.pool_acquire_timeout_sec == 7 for i in overridden)


def test_instance_pool_env_override_invalid_int_raises() -> None:
    with pytest.raises(ValueError, match="FASTMCP_SQL_POOL_MAX"):
        apply_instance_env_overrides([_base_instance()], {"FASTMCP_SQL_POOL_MAX": "bad"})
