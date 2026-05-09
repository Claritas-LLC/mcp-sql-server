from __future__ import annotations

import json
import os
import pathlib
from typing import Any

import yaml
from pydantic import BaseModel

from .models import AuthConfig, RateLimitConfig, RuntimePolicy, SqlInstanceConfig


class AppConfig(BaseModel):
    instances: list[SqlInstanceConfig]
    policy: RuntimePolicy
    rate_limit: RateLimitConfig
    auth: AuthConfig


def _parse_bool_map(name: str, raw: str) -> dict[str, bool]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} must be valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be a JSON object")

    parsed: dict[str, bool] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, bool):
            raise ValueError(f"{name} entries must map string keys to boolean values")
        parsed[key] = value
    return parsed


def _parse_nested_bool_map(name: str, raw: str) -> dict[str, dict[str, bool]]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} must be valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be a JSON object")

    parsed: dict[str, dict[str, bool]] = {}
    for instance, mapping in payload.items():
        if not isinstance(instance, str) or not isinstance(mapping, dict):
            raise ValueError(f"{name} must map instance names to JSON objects")
        inner: dict[str, bool] = {}
        for tool, enabled in mapping.items():
            if not isinstance(tool, str) or not isinstance(enabled, bool):
                raise ValueError(f"{name} nested entries must map tool names to boolean values")
            inner[tool] = enabled
        parsed[instance] = inner
    return parsed


def apply_policy_env_overrides(policy: RuntimePolicy, env: dict[str, str] | None = None) -> RuntimePolicy:
    values = env or dict(os.environ)

    global_overrides = values.get("FASTMCP_TOOL_ENABLE_FLAGS_JSON")
    instance_overrides = values.get("FASTMCP_INSTANCE_TOOL_ENABLE_FLAGS_JSON")

    update_data: dict[str, Any] = {}
    if global_overrides:
        update_data["tool_enable_flags"] = _parse_bool_map("FASTMCP_TOOL_ENABLE_FLAGS_JSON", global_overrides)
    if instance_overrides:
        update_data["instance_tool_enable_flags"] = _parse_nested_bool_map(
            "FASTMCP_INSTANCE_TOOL_ENABLE_FLAGS_JSON", instance_overrides
        )

    if not update_data:
        return policy
    return policy.model_copy(update=update_data)


def _parse_csv_values(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_int_value(name: str, raw: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _parse_bool_value(name: str, raw: str) -> bool:
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def apply_instance_env_overrides(
    instances: list[SqlInstanceConfig], env: dict[str, str] | None = None
) -> list[SqlInstanceConfig]:
    values = env or dict(os.environ)

    update_data: dict[str, Any] = {}

    pool_enabled = values.get("FASTMCP_SQL_POOL_ENABLED")
    if pool_enabled:
        update_data["pool_enabled"] = _parse_bool_value("FASTMCP_SQL_POOL_ENABLED", pool_enabled)

    pool_max = values.get("FASTMCP_SQL_POOL_MAX")
    if pool_max:
        update_data["pool_max"] = _parse_int_value("FASTMCP_SQL_POOL_MAX", pool_max)

    pool_idle_timeout = values.get("FASTMCP_SQL_POOL_IDLE_TIMEOUT_SEC")
    if pool_idle_timeout:
        update_data["pool_idle_timeout_sec"] = _parse_int_value(
            "FASTMCP_SQL_POOL_IDLE_TIMEOUT_SEC", pool_idle_timeout
        )

    pool_acquire_timeout = values.get("FASTMCP_SQL_POOL_ACQUIRE_TIMEOUT_SEC")
    if pool_acquire_timeout:
        update_data["pool_acquire_timeout_sec"] = _parse_int_value(
            "FASTMCP_SQL_POOL_ACQUIRE_TIMEOUT_SEC", pool_acquire_timeout
        )

    if not update_data:
        return instances
    return [instance.model_copy(update=update_data) for instance in instances]


def apply_auth_env_overrides(auth: AuthConfig, env: dict[str, str] | None = None) -> AuthConfig:
    values = env or dict(os.environ)

    update_data: dict[str, Any] = {}

    mode = values.get("FASTMCP_AUTH_MODE")
    if mode:
        update_data["auth_mode"] = mode.strip()

    azure_auth_enabled = values.get("FASTMCP_AZURE_AUTH_ENABLED")
    if azure_auth_enabled:
        update_data["azure_auth_enabled"] = _parse_bool_value("FASTMCP_AZURE_AUTH_ENABLED", azure_auth_enabled)

    azure_group_authorization_enabled = values.get("FASTMCP_AZURE_GROUP_AUTHORIZATION_ENABLED")
    if azure_group_authorization_enabled:
        update_data["azure_group_authorization_enabled"] = _parse_bool_value(
            "FASTMCP_AZURE_GROUP_AUTHORIZATION_ENABLED", azure_group_authorization_enabled
        )

    tenant_id = values.get("FASTMCP_AZURE_TENANT_ID")
    if tenant_id:
        update_data["azure_tenant_id"] = tenant_id.strip()

    client_id = values.get("FASTMCP_AZURE_CLIENT_ID")
    if client_id:
        update_data["azure_client_id"] = client_id.strip()

    client_secret_ref = values.get("FASTMCP_AZURE_CLIENT_SECRET_REF")
    if client_secret_ref:
        update_data["azure_client_secret_ref"] = client_secret_ref.strip()

    required_scopes = values.get("FASTMCP_AZURE_REQUIRED_SCOPES")
    if required_scopes:
        update_data["azure_required_scopes"] = _parse_csv_values(required_scopes)

    base_url = values.get("FASTMCP_AZURE_BASE_URL")
    if base_url:
        update_data["azure_base_url"] = base_url.strip()

    identifier_uri = values.get("FASTMCP_AZURE_IDENTIFIER_URI")
    if identifier_uri:
        update_data["azure_identifier_uri"] = identifier_uri.strip()

    group_claim_name = values.get("FASTMCP_AZURE_GROUP_CLAIM_NAME")
    if group_claim_name:
        update_data["azure_group_claim_name"] = group_claim_name.strip()

    read_groups = values.get("FASTMCP_AZURE_READ_GROUPS")
    if read_groups:
        update_data["azure_read_groups"] = _parse_csv_values(read_groups)

    write_groups = values.get("FASTMCP_AZURE_WRITE_GROUPS")
    if write_groups:
        update_data["azure_write_groups"] = _parse_csv_values(write_groups)

    pool_max = values.get("FASTMCP_POOL_MAX_CONNECTIONS")
    if pool_max:
        update_data["pool_max_connections"] = _parse_int_value("FASTMCP_POOL_MAX_CONNECTIONS", pool_max)

    pool_keepalive = values.get("FASTMCP_POOL_MAX_KEEPALIVE")
    if pool_keepalive:
        update_data["pool_max_keepalive_connections"] = _parse_int_value("FASTMCP_POOL_MAX_KEEPALIVE", pool_keepalive)

    pool_timeout = values.get("FASTMCP_POOL_TIMEOUT_SECONDS")
    if pool_timeout:
        update_data["pool_timeout_seconds"] = _parse_int_value("FASTMCP_POOL_TIMEOUT_SECONDS", pool_timeout)

    if not update_data:
        return auth
    return auth.model_copy(update=update_data)


def _load_yaml(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML at {path} must be a mapping")
    return data


def load_config(instances_path: str, policy_path: str, rate_limit_path: str) -> AppConfig:
    instances_raw = _load_yaml(pathlib.Path(instances_path))
    policy_raw = _load_yaml(pathlib.Path(policy_path))
    rate_limit_raw = _load_yaml(pathlib.Path(rate_limit_path))

    instances = [SqlInstanceConfig.model_validate(item) for item in instances_raw.get("instances", [])]
    instances = apply_instance_env_overrides(instances)
    if not instances:
        raise ValueError("At least one SQL instance must be configured")

    policy = RuntimePolicy.model_validate(policy_raw)
    policy = apply_policy_env_overrides(policy)
    auth = AuthConfig.model_validate(policy_raw.get("auth", {}))
    auth = apply_auth_env_overrides(auth)

    return AppConfig(
        instances=instances,
        policy=policy,
        rate_limit=RateLimitConfig.model_validate(rate_limit_raw),
        auth=auth,
    )
