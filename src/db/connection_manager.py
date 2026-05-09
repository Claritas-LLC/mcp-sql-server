from __future__ import annotations

import contextlib
import threading
import time
from typing import Any

import pyodbc

from src.models import SqlInstanceConfig


class ConnectionManager:
    """Holds independently configured connection details for each SQL instance."""

    def __init__(self, instances: list[SqlInstanceConfig], secret_resolver: callable):
        self._instances: dict[str, SqlInstanceConfig] = {item.id: item for item in instances if item.enabled}
        self._secret_resolver = secret_resolver
        self._lock = threading.RLock()
        self._health: dict[str, dict[str, Any]] = {k: {"state": "unknown", "checked_at": None, "error": None} for k in self._instances}

    def _connection_string(self, instance: SqlInstanceConfig, database_override: str | None = None) -> str:
        creds = self._secret_resolver(instance.auth_secret_ref)
        user = creds.get("username")
        password = creds.get("password")
        database_name = database_override or instance.database
        return (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={instance.host},{instance.port};"
            f"DATABASE={database_name};"
            f"UID={user};PWD={password};"
            f"Encrypt={'yes' if instance.encrypt else 'no'};"
            f"TrustServerCertificate={'yes' if instance.trust_server_certificate else 'no'};"
            f"Connection Timeout={instance.connect_timeout_sec};"
        )

    @contextlib.contextmanager
    def connect(self, instance_id: str, database_override: str | None = None):
        instance = self._instances[instance_id]
        conn = pyodbc.connect(self._connection_string(instance, database_override=database_override), autocommit=False)
        try:
            yield conn
        finally:
            conn.close()

    def healthcheck_instance(self, instance_id: str) -> dict[str, Any]:
        with self._lock:
            started = time.time()
            try:
                with self.connect(instance_id) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT 1")
                    cur.fetchone()
                self._health[instance_id] = {
                    "state": "healthy",
                    "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "latency_ms": int((time.time() - started) * 1000),
                    "error": None,
                }
            except Exception as exc:  # pragma: no cover
                self._health[instance_id] = {
                    "state": "unhealthy",
                    "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "latency_ms": int((time.time() - started) * 1000),
                    "error": str(exc),
                }
            return dict(self._health[instance_id])

    def healthcheck_all(self) -> dict[str, dict[str, Any]]:
        return {instance_id: self.healthcheck_instance(instance_id) for instance_id in self._instances}

    def list_enabled_instances(self) -> list[str]:
        return list(self._instances)

    @staticmethod
    def _normalize_column_names(raw_columns: list[Any]) -> list[str]:
        """Ensure row dict keys are always stable, non-empty strings.

        Some SQL Server expressions/DMVs can surface unnamed columns via ODBC,
        which produces None column names and breaks downstream JSON/tool handling.
        """
        normalized: list[str] = []
        seen: dict[str, int] = {}
        final_names: set[str] = set()
        for idx, value in enumerate(raw_columns, start=1):
            name = str(value).strip() if value is not None else ""
            if not name:
                name = f"col_{idx}"
            seen[name] = seen.get(name, 0) + 1
            count = seen[name]
            if count > 1:
                normalized_name = f"{name}_{count}"
            else:
                normalized_name = name
            # Ensure uniqueness against final names (not just original)
            while normalized_name in final_names:
                if "_" in normalized_name:
                    base, suffix = normalized_name.rsplit("_", 1)
                    if suffix.isdigit():
                        normalized_name = f"{base}_{int(suffix) + 1}"
                    else:
                        normalized_name = f"{normalized_name}_1"
                else:
                    normalized_name = f"{normalized_name}_1"
            final_names.add(normalized_name)
            normalized.append(normalized_name)
        return normalized

    def execute_read(self, instance_id: str, sql: str, max_rows: int) -> list[dict[str, Any]]:
        with self.connect(instance_id) as conn:
            cur = conn.cursor()
            cur.execute(sql)
            columns = self._normalize_column_names([d[0] for d in cur.description or []])
            rows = cur.fetchmany(max_rows)
            return [dict(zip(columns, row, strict=False)) for row in rows]

    def execute_read_in_database(self, instance_id: str, database_name: str, sql: str, max_rows: int) -> dict[str, Any]:
        with self.connect(instance_id, database_override=database_name) as conn:
            cur = conn.cursor()
            cur.execute(sql)
            columns = self._normalize_column_names([d[0] for d in cur.description or []])
            rows = cur.fetchmany(max_rows)
            payload = [dict(zip(columns, row, strict=False)) for row in rows]
            return {"columns": columns, "rows": payload}

    def execute_catalog_query(self, instance_id: str, database_name: str, sql: str, max_rows: int = 5000) -> dict[str, Any]:
        started = time.time()
        payload = self.execute_read_in_database(instance_id, database_name, sql, max_rows)
        return {
            "columns": payload["columns"],
            "rows": payload["rows"],
            "row_count": len(payload["rows"]),
            "latency_ms": int((time.time() - started) * 1000),
        }

    def fetch_single_row_in_database(self, instance_id: str, database_name: str, sql: str) -> dict[str, Any]:
        with self.connect(instance_id, database_override=database_name) as conn:
            cur = conn.cursor()
            cur.execute(sql)
            row = cur.fetchone()
            columns = self._normalize_column_names([d[0] for d in cur.description or []])
            if row is None:
                return {}
            return dict(zip(columns, row, strict=False))

    def list_objects(self, instance_id: str, database_name: str, object_type: str, max_rows: int = 5000) -> list[dict[str, Any]]:
        object_type_map = {
            "table": "U",
            "view": "V",
            "procedure": "P",
            "function": "FN",
            "synonym": "SN",
        }
        key = object_type.lower().strip()
        if key not in object_type_map:
            raise ValueError("INVALID_INPUT: object_type must be one of table, view, procedure, function, synonym")

        sql = (
            f"SELECT TOP {max_rows} o.name AS object_name, s.name AS schema_name, o.type_desc AS object_type, "
            "DB_NAME() AS owning_database "
            "FROM sys.objects o "
            "JOIN sys.schemas s ON s.schema_id = o.schema_id "
            "WHERE o.type = ? "
            "ORDER BY s.name, o.name"
        )

        with self.connect(instance_id, database_override=database_name) as conn:
            cur = conn.cursor()
            cur.execute(sql, object_type_map[key])
            columns = self._normalize_column_names([d[0] for d in cur.description or []])
            rows = cur.fetchall()
            return [dict(zip(columns, row, strict=False)) for row in rows]

    def explain_query(self, instance_id: str, database_name: str, sql: str) -> dict[str, Any]:
        with self.connect(instance_id, database_override=database_name) as conn:
            cur = conn.cursor()
            cur.execute("SET SHOWPLAN_ALL ON")
            try:
                cur.execute(sql)
                columns = self._normalize_column_names([d[0] for d in cur.description or []])
                rows = cur.fetchall()
            finally:
                cur.execute("SET SHOWPLAN_ALL OFF")

        row_dicts = [dict(zip(columns, row, strict=False)) for row in rows]
        accessed_objects = sorted({str(item.get("Object")) for item in row_dicts if item.get("Object")})
        total_cost = 0.0
        for item in row_dicts:
            value = item.get("TotalSubtreeCost")
            if value is None:
                continue
            try:
                total_cost += float(value)
            except (TypeError, ValueError):
                continue

        return {
            "available": True,
            "estimated_cost": round(total_cost, 4),
            "accessed_objects": accessed_objects,
        }

    def execute_proc(self, instance_id: str, proc_name: str, params: list[str | int | float | bool | None] | None = None) -> dict[str, Any]:
        params = params or []
        placeholders = ", ".join(["?"] * len(params))
        statement = f"EXEC {proc_name} {placeholders}".strip()
        with self.connect(instance_id) as conn:
            cur = conn.cursor()
            cur.execute(statement, params)
            conn.commit()
            return {"status": "ok", "procedure": proc_name, "rowcount": cur.rowcount}
