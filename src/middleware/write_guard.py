from __future__ import annotations

import re

from src.models import RuntimePolicy


class WriteGuard:
    def __init__(self, policy: RuntimePolicy):
        self._policy = policy
        self._blocked = [re.compile(p) for p in policy.blocked_sql_patterns]

    @staticmethod
    def _first_verb(sql: str) -> str:
        trimmed = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
        trimmed = re.sub(r"--.*?$", "", trimmed, flags=re.M).strip()
        token = trimmed.split(None, 1)[0] if trimmed else ""
        return token.upper()

    def enforce(self, tool_name: str, sql: str) -> None:
        for pattern in self._blocked:
            if pattern.search(sql):
                raise PermissionError("SQL blocked by denylist policy")

        verb = self._first_verb(sql)
        is_write = verb in {"INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "ALTER", "DROP", "TRUNCATE"}

        if self._policy.write_mode_default == "deny" and is_write and tool_name not in set(self._policy.allowed_write_tools):
            raise PermissionError(f"Write blocked by policy for tool {tool_name}")
