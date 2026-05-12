from __future__ import annotations

import hashlib
import json
import pathlib
import threading
import time
from typing import Any


class AuditLogger:
    def __init__(self, file_path: str = "/var/log/mcp/audit.log"):
        self._path = pathlib.Path(file_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def hash_sql(sql: str) -> str:
        return hashlib.sha256(sql.encode("utf-8")).hexdigest()

    def log_event(
        self,
        *,
        request_id: str,
        actor: str,
        tool: str,
        instance: str,
        sql: str,
        decision: str,
        latency_ms: int,
        rows: int,
        error_code: str | None,
        auth_mode: str | None = None,
        auth_subject: str | None = None,
        privilege_level: str | None = None,
        group_match_result: dict[str, Any] | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": request_id,
            "actor": actor,
            "tool": tool,
            "instance": instance,
            "sql_hash": self.hash_sql(sql),
            "decision": decision,
            "latency_ms": latency_ms,
            "rows": rows,
            "error_code": error_code,
        }
        if auth_mode is not None:
            event["auth_mode"] = auth_mode
        if auth_subject is not None:
            event["auth_subject"] = auth_subject
        if privilege_level is not None:
            event["privilege_level"] = privilege_level
        if group_match_result is not None:
            event["group_match_result"] = group_match_result
        line = json.dumps(event, separators=(",", ":"), ensure_ascii=True)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
