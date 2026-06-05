from __future__ import annotations

import contextlib
import threading
import time
from typing import Any

import pyodbc

from src.models import SqlInstanceConfig


class ConnectionManager:
    """Holds independently configured connection details for each SQL instance."""

    _READ_RETRY_ATTEMPTS = 2
    _READ_RETRY_BACKOFF_SEC = 0.05

    def __init__(self, instances: list[SqlInstanceConfig], secret_resolver: callable):
        self._instances: dict[str, SqlInstanceConfig] = {
            item.id: item for item in instances if item.enabled
        }
        self._secret_resolver = secret_resolver
        self._lock = threading.RLock()
        self._pool_condition = threading.Condition(self._lock)
        self._health: dict[str, dict[str, Any]] = {
            k: {"state": "unknown", "checked_at": None, "error": None}
            for k in self._instances
        }
        self._pool_state: dict[str, dict[str, Any]] = {
            instance_id: {
                "available": [],
                "in_use": [],
                "created_total": 0,
                "reused_total": 0,
                "discarded_total": 0,
            }
            for instance_id in self._instances
        }

    def _connection_string(
        self, instance: SqlInstanceConfig, database_override: str | None = None
    ) -> str:
        creds = self._secret_resolver(instance.auth_secret_ref)
        user = creds.get("username")
        password = creds.get("password")
        database_name = database_override or instance.database
        return (
            "DRIVER={ODBC Driver 17 for SQL Server};"
            f"SERVER={instance.host},{instance.port};"
            f"DATABASE={database_name};"
            f"UID={user};PWD={{{password}}};"
            "Encrypt=no;TrustServerCertificate=yes;"
        )

    def _connect_new(
        self, instance: SqlInstanceConfig, database_override: str | None = None
    ) -> pyodbc.Connection:
        return pyodbc.connect(
            self._connection_string(instance, database_override=database_override),
            autocommit=False,
        )

    def _is_connection_usable(self, conn: pyodbc.Connection) -> bool:
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            return True
        except Exception:
            return False

    def _remove_in_use_connection(
        self, state: dict[str, Any], conn: pyodbc.Connection
    ) -> None:
        for idx, item in enumerate(state["in_use"]):
            if item is conn:
                state["in_use"].pop(idx)
                return

    @staticmethod
    def _is_transient_read_error(exc: BaseException) -> bool:
        """Detect transient transport-level SQL errors safe to retry for reads."""
        args = getattr(exc, "args", ())
        sqlstate = ""
        if isinstance(args, (tuple, list)) and args:
            sqlstate = str(args[0]).strip().upper()
        message = " ".join(str(part) for part in args).lower() if args else str(exc).lower()

        if sqlstate in {"08S01", "08001", "HYT00", "HYT01"}:
            return True

        return "tcp provider" in message or "communication link failure" in message

    def _run_read_operation(
        self,
        instance_id: str,
        operation: callable,
        database_override: str | None = None,
    ) -> Any:
        last_exc: BaseException | None = None
        for attempt in range(self._READ_RETRY_ATTEMPTS):
            try:
                with self.connect(instance_id, database_override=database_override) as conn:
                    return operation(conn)
            except Exception as exc:
                last_exc = exc
                can_retry = (
                    attempt < self._READ_RETRY_ATTEMPTS - 1
                    and self._is_transient_read_error(exc)
                )
                if not can_retry:
                    raise
                time.sleep(self._READ_RETRY_BACKOFF_SEC * (attempt + 1))

        if last_exc is not None:  # pragma: no cover - defensive fallback
            raise last_exc
        raise RuntimeError("Read operation failed unexpectedly")

    def _acquire_connection(
        self, instance_id: str, database_override: str | None = None
    ) -> tuple[pyodbc.Connection, bool]:
        instance = self._instances[instance_id]
        use_pool = instance.pool_enabled and database_override is None
        if not use_pool:
            return self._connect_new(
                instance, database_override=database_override
            ), False

        deadline = time.monotonic() + max(0, instance.pool_acquire_timeout_sec)
        while True:
            with self._pool_condition:
                state = self._pool_state[instance_id]
                if state["available"]:
                    conn = state["available"].pop()
                    state["in_use"].append(conn)
                    state["reused_total"] += 1
                else:
                    conn = None

                if conn is None:
                    pool_cap = max(1, instance.pool_max)
                    pool_size = len(state["available"]) + len(state["in_use"])
                    if pool_size < pool_cap:
                        create_new = True
                    else:
                        create_new = False
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError(
                                f"Connection pool acquire timeout for instance '{instance_id}' after "
                                f"{instance.pool_acquire_timeout_sec}s"
                            )
                        self._pool_condition.wait(timeout=remaining)

            if conn is not None:
                if self._is_connection_usable(conn):
                    return conn, True
                with self._pool_condition:
                    state = self._pool_state[instance_id]
                    self._remove_in_use_connection(state, conn)
                    state["discarded_total"] += 1
                    self._pool_condition.notify_all()
                with contextlib.suppress(Exception):
                    conn.close()
                continue

            if create_new:
                created = self._connect_new(
                    instance, database_override=database_override
                )
                with self._pool_condition:
                    state = self._pool_state[instance_id]
                    state["in_use"].append(created)
                    state["created_total"] += 1
                return created, True

    def _release_connection(
        self, instance_id: str, conn: pyodbc.Connection, pooled: bool, had_error: bool
    ) -> None:
        if had_error:
            with contextlib.suppress(Exception):
                conn.rollback()

        if not pooled:
            with contextlib.suppress(Exception):
                conn.close()
            return

        instance = self._instances[instance_id]
        should_discard = had_error or not self._is_connection_usable(conn)

        with self._pool_condition:
            state = self._pool_state[instance_id]
            self._remove_in_use_connection(state, conn)

            if should_discard:
                state["discarded_total"] += 1
                self._pool_condition.notify_all()
                close_now = True
            else:
                try:
                    conn.autocommit = False
                except Exception:
                    state["discarded_total"] += 1
                    self._pool_condition.notify_all()
                    close_now = True
                else:
                    pool_cap = max(1, instance.pool_max)
                    if len(state["available"]) < pool_cap:
                        state["available"].append(conn)
                        self._pool_condition.notify_all()
                        close_now = False
                    else:
                        state["discarded_total"] += 1
                        self._pool_condition.notify_all()
                        close_now = True

        if close_now:
            with contextlib.suppress(Exception):
                conn.close()

    @contextlib.contextmanager
    def connect(self, instance_id: str, database_override: str | None = None):
        conn, pooled = self._acquire_connection(
            instance_id, database_override=database_override
        )
        had_error = False
        try:
            yield conn
        except Exception:
            had_error = True
            raise
        finally:
            self._release_connection(
                instance_id, conn, pooled=pooled, had_error=had_error
            )

    def get_pool_diagnostics(self) -> dict[str, dict[str, Any]]:
        with self._pool_condition:
            payload: dict[str, dict[str, Any]] = {}
            for instance_id, instance in self._instances.items():
                state = self._pool_state[instance_id]
                payload[instance_id] = {
                    "enabled": bool(instance.pool_enabled),
                    "pool_max": int(instance.pool_max),
                    "pool_size": len(state["available"]) + len(state["in_use"]),
                    "in_use": len(state["in_use"]),
                    "available": len(state["available"]),
                    "created_total": int(state["created_total"]),
                    "reused_total": int(state["reused_total"]),
                    "discarded_total": int(state["discarded_total"]),
                }
            return payload

    def close_all_pools(self) -> None:
        with self._pool_condition:
            for state in self._pool_state.values():
                to_close = [*state["available"], *state["in_use"]]
                state["available"].clear()
                state["in_use"].clear()
                for conn in to_close:
                    with contextlib.suppress(Exception):
                        conn.close()
            self._pool_condition.notify_all()

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
        return {
            instance_id: self.healthcheck_instance(instance_id)
            for instance_id in self._instances
        }

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

    def execute_read(
        self, instance_id: str, sql: str, max_rows: int
    ) -> list[dict[str, Any]]:
        def _op(conn: pyodbc.Connection) -> list[dict[str, Any]]:
            cur = conn.cursor()
            cur.execute(sql)
            columns = self._normalize_column_names(
                [d[0] for d in cur.description or []]
            )
            rows = cur.fetchmany(max_rows)
            return [dict(zip(columns, row, strict=False)) for row in rows]

        return self._run_read_operation(instance_id, _op)

    def execute_read_in_database(
        self, instance_id: str, database_name: str, sql: str, max_rows: int
    ) -> dict[str, Any]:
        def _op(conn: pyodbc.Connection) -> dict[str, Any]:
            cur = conn.cursor()
            cur.execute(sql)
            columns = self._normalize_column_names(
                [d[0] for d in cur.description or []]
            )
            rows = cur.fetchmany(max_rows)
            payload = [dict(zip(columns, row, strict=False)) for row in rows]
            return {"columns": columns, "rows": payload}

        return self._run_read_operation(
            instance_id,
            _op,
            database_override=database_name,
        )

    def execute_catalog_query(
        self, instance_id: str, database_name: str, sql: str, max_rows: int = 5000
    ) -> dict[str, Any]:
        started = time.time()
        payload = self.execute_read_in_database(
            instance_id, database_name, sql, max_rows
        )
        return {
            "columns": payload["columns"],
            "rows": payload["rows"],
            "row_count": len(payload["rows"]),
            "latency_ms": int((time.time() - started) * 1000),
        }

    def fetch_single_row_in_database(
        self, instance_id: str, database_name: str, sql: str
    ) -> dict[str, Any]:
        def _op(conn: pyodbc.Connection) -> dict[str, Any]:
            cur = conn.cursor()
            cur.execute(sql)
            row = cur.fetchone()
            columns = self._normalize_column_names(
                [d[0] for d in cur.description or []]
            )
            if row is None:
                return {}
            return dict(zip(columns, row, strict=False))

        return self._run_read_operation(
            instance_id,
            _op,
            database_override=database_name,
        )

    def list_objects(
        self,
        instance_id: str,
        database_name: str,
        object_type: str,
        max_rows: int = 5000,
    ) -> list[dict[str, Any]]:
        object_type_map = {
            "table": "U",
            "view": "V",
            "procedure": "P",
            "function": "FN",
            "synonym": "SN",
        }
        key = object_type.lower().strip()
        if key not in object_type_map:
            raise ValueError(
                "INVALID_INPUT: object_type must be one of table, view, procedure, function, synonym"
            )

        sql = (
            f"SELECT TOP {max_rows} o.name AS object_name, s.name AS schema_name, o.type_desc AS object_type, "
            "DB_NAME() AS owning_database "
            "FROM sys.objects o "
            "JOIN sys.schemas s ON s.schema_id = o.schema_id "
            "WHERE o.type = ? "
            "ORDER BY s.name, o.name"
        )

        def _op(conn: pyodbc.Connection) -> list[dict[str, Any]]:
            cur = conn.cursor()
            cur.execute(sql, object_type_map[key])
            columns = self._normalize_column_names(
                [d[0] for d in cur.description or []]
            )
            rows = cur.fetchall()
            return [dict(zip(columns, row, strict=False)) for row in rows]

        return self._run_read_operation(
            instance_id,
            _op,
            database_override=database_name,
        )

    def explain_query(
        self, instance_id: str, database_name: str, sql: str
    ) -> dict[str, Any]:
        def _op(conn: pyodbc.Connection) -> tuple[list[str], list[Any]]:
            cur = conn.cursor()
            cur.execute("SET SHOWPLAN_ALL ON")
            try:
                cur.execute(sql)
                columns = self._normalize_column_names(
                    [d[0] for d in cur.description or []]
                )
                rows = cur.fetchall()
                return columns, rows
            finally:
                cur.execute("SET SHOWPLAN_ALL OFF")

        columns, rows = self._run_read_operation(
            instance_id,
            _op,
            database_override=database_name,
        )

        row_dicts = [dict(zip(columns, row, strict=False)) for row in rows]
        accessed_objects = sorted(
            {str(item.get("Object")) for item in row_dicts if item.get("Object")}
        )
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

    def execute_proc(
        self,
        instance_id: str,
        proc_name: str,
        params: list[str | int | float | bool | None] | None = None,
        database_override: str | None = None,
    ) -> dict[str, Any]:
        params = params or []
        placeholders = ", ".join(["?"] * len(params))
        statement = f"EXEC {proc_name} {placeholders}".strip()
        with self.connect(instance_id, database_override=database_override) as conn:
            cur = conn.cursor()
            cur.execute(statement, params)
            has_result_set = bool(cur.description)
            columns: list[str] = []
            rows: list[dict[str, Any]] = []

            if has_result_set:
                columns = self._normalize_column_names(
                    [d[0] for d in cur.description or []]
                )
                fetched = cur.fetchall()
                rows = [dict(zip(columns, row, strict=False)) for row in fetched]

            conn.commit()
            return {
                "status": "ok",
                "procedure": proc_name,
                "rowcount": cur.rowcount,
                "has_result_set": has_result_set,
                "columns": columns,
                "rows": rows,
            }
