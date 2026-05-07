from __future__ import annotations

import json
import os
import pathlib
from typing import Any

import yaml
from pydantic import BaseModel

from .models import RateLimitConfig, RuntimePolicy, SqlInstanceConfig


class AppConfig(BaseModel):
    instances: list[SqlInstanceConfig]
    policy: RuntimePolicy
    rate_limit: RateLimitConfig


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
    if not instances:
        raise ValueError("At least one SQL instance must be configured")

    policy = RuntimePolicy.model_validate(policy_raw)
    policy = apply_policy_env_overrides(policy)

    return AppConfig(
        instances=instances,
        policy=policy,
        rate_limit=RateLimitConfig.model_validate(rate_limit_raw),
    )
