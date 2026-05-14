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
        is_write = verb in {
            "INSERT",
            "UPDATE",
            "DELETE",
            "MERGE",
            "EXEC",
            "EXECUTE",
            "CREATE",
            "ALTER",
            "DROP",
            "TRUNCATE",
        }

        if (
            self._policy.write_mode_default == "deny"
            and is_write
            and tool_name not in set(self._policy.allowed_write_tools)
        ):
            raise PermissionError(f"Write blocked by policy for tool {tool_name}")

    @staticmethod
    def _normalize_proc_name(name: str, mode: str, default_schema: str) -> str:
        normalized = name.strip().lower().replace("[", "").replace("]", "")
        parts = [p for p in normalized.split(".") if p]
        if not parts:
            return ""
        if len(parts) >= 2:
            return f"{parts[-2]}.{parts[-1]}"
        if mode == "default_schema_expand":
            return f"{default_schema}.{parts[0]}"
        return parts[0]

    def validate_procedure(self, tool_name: str, proc_name: str) -> None:
        """Validate that a procedure is in the allowlist for the given tool.

        Args:
            tool_name: The MCP tool name (e.g., 'db_primary_sql2019_exec_proc')
            proc_name: The procedure name, optionally schema-qualified (e.g., 'dbo.usp_X' or 'usp_X')

        Raises:
            PermissionError: If the procedure is not in the allowed list for the tool.
        """
        # Get the allowed procedures for this tool; default to empty list (deny all).
        if tool_name not in self._policy.allowed_tools:
            raise PermissionError(
                f"Procedure execution not configured for tool {tool_name}"
            )

        tool_config = self._policy.allowed_tools[tool_name]
        if not isinstance(tool_config, dict):
            raise PermissionError(
                f"Invalid allowed_tools entry for {tool_name}: expected dict, got {type(tool_config).__name__} ({tool_config!r})"
            )
        allowed_procedures = tool_config.get("allowed_procedures", [])

        mode = (
            str(
                getattr(
                    self._policy, "procedure_name_match_mode", "default_schema_expand"
                )
                or "default_schema_expand"
            )
            .strip()
            .lower()
        )
        if mode not in {"strict", "default_schema_expand"}:
            mode = "default_schema_expand"
        default_schema = (
            str(getattr(self._policy, "procedure_default_schema", "dbo") or "dbo")
            .strip()
            .lower()
        )

        normalized_proc = self._normalize_proc_name(
            proc_name, mode=mode, default_schema=default_schema
        )
        normalized_allowed = [
            self._normalize_proc_name(p, mode=mode, default_schema=default_schema)
            for p in allowed_procedures
        ]

        if normalized_proc not in normalized_allowed:
            raise PermissionError(
                f"Procedure {proc_name} is not in the allowed procedures list for tool {tool_name}"
            )
