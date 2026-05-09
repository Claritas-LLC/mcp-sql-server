from __future__ import annotations

from typing import Any


def _normalize_groups(raw: Any) -> set[str]:
    if raw is None:
        return set()
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",") if item.strip()]
        return {item.lower() for item in values}
    if isinstance(raw, list):
        values = [str(item).strip() for item in raw if str(item).strip()]
        return {item.lower() for item in values}
    return set()


def resolve_group_privilege(
    principal_groups: Any,
    read_groups: list[str],
    write_groups: list[str],
    group_authorization_enabled: bool,
) -> tuple[str, dict[str, Any]]:
    """Resolve privilege level from principal group claims.

    Returns a tuple:
    - privilege level: write|read|none
    - match metadata for diagnostics/audit
    """
    if not group_authorization_enabled:
        return "write", {
            "group_authorization_enabled": False,
            "matched_read_groups": [],
            "matched_write_groups": [],
        }

    principal = _normalize_groups(principal_groups)
    read_set = {group.strip().lower() for group in read_groups if group.strip()}
    write_set = {group.strip().lower() for group in write_groups if group.strip()}

    matched_read = sorted(principal.intersection(read_set))
    matched_write = sorted(principal.intersection(write_set))

    if matched_write:
        privilege = "write"
    elif matched_read:
        privilege = "read"
    else:
        privilege = "none"

    return privilege, {
        "group_authorization_enabled": True,
        "matched_read_groups": matched_read,
        "matched_write_groups": matched_write,
    }
