from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Sequence

import pyodbc
from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

load_dotenv()

logger = logging.getLogger("mcp-sqlserver")
logging.basicConfig(
    level=getattr(logging, os.getenv("MCP_LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Settings:
    db_server: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    db_driver: str
    db_encrypt: str
    db_trust_cert: str
    statement_timeout_ms: int
    max_rows: int
    allow_write: bool
    confirm_write: bool
    transport: str
    host: str
    port: int
    auth_type: str
    api_key: str


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    return int(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def _load_settings() -> Settings:
    db_server = _env("DB_SERVER") or _env("SQL_SERVER")
    db_port = _env_int("DB_PORT", _env_int("SQL_PORT", 1433))
    db_user = _env("DB_USER") or _env("SQL_USER")
    db_password = _env("DB_PASSWORD") or _env("SQL_PASSWORD")
    db_name = _env("DB_NAME") or _env("SQL_DATABASE") or "master"
    db_driver = _env("DB_DRIVER") or _env("SQL_DRIVER") or "ODBC Driver 17 for SQL Server"

    return Settings(
        db_server=db_server,
        db_port=db_port,
        db_user=db_user,
        db_password=db_password,
        db_name=db_name,
        db_driver=db_driver,
        db_encrypt=_env("DB_ENCRYPT", "no"),
        db_trust_cert=_env("DB_TRUST_CERT", "yes"),
        statement_timeout_ms=_env_int("MCP_STATEMENT_TIMEOUT_MS", 120000),
        max_rows=_env_int("MCP_MAX_ROWS", 500),
        allow_write=_env_bool("MCP_ALLOW_WRITE", False),
        confirm_write=_env_bool("MCP_CONFIRM_WRITE", False),
        transport=_env("MCP_TRANSPORT", "http").lower(),
        host=_env("MCP_HOST", "0.0.0.0"),
        port=_env_int("MCP_PORT", 8000),
        auth_type=_env("FASTMCP_AUTH_TYPE", "").lower(),
        api_key=_env("FASTMCP_API_KEY", ""),
    )


SETTINGS = _load_settings()


def _validate_runtime_guards() -> None:
    if SETTINGS.allow_write and not SETTINGS.confirm_write:
        raise RuntimeError("Write mode requires MCP_CONFIRM_WRITE=true.")
    if SETTINGS.allow_write and SETTINGS.transport in {"http", "sse"} and SETTINGS.auth_type in {"", "none"}:
        raise RuntimeError("Write mode over HTTP requires FASTMCP_AUTH_TYPE.")


_validate_runtime_guards()


def _connection_string(database: str | None = None) -> str:
    db_name = database or SETTINGS.db_name
    return (
        f"DRIVER={{{SETTINGS.db_driver}}};"
        f"SERVER={SETTINGS.db_server},{SETTINGS.db_port};"
        f"DATABASE={db_name};"
        f"UID={SETTINGS.db_user};"
        f"PWD={SETTINGS.db_password};"
        f"Encrypt={SETTINGS.db_encrypt};"
        f"TrustServerCertificate={SETTINGS.db_trust_cert};"
    )


def get_connection(database: str | None = None) -> pyodbc.Connection:
    if not SETTINGS.db_server or not SETTINGS.db_user or not SETTINGS.db_password:
        raise RuntimeError("Database credentials are not configured. Set DB_SERVER, DB_USER, DB_PASSWORD.")

    conn = pyodbc.connect(_connection_string(database), timeout=max(1, SETTINGS.statement_timeout_ms // 1000))
    conn.autocommit = True
    return conn


def _execute_safe(cur: pyodbc.Cursor, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> None:
    if params is None:
        cur.execute(sql)
    else:
        cur.execute(sql, params)


def _fetch_limited(cur: pyodbc.Cursor, max_rows: int) -> list[Any]:
    if max_rows <= 0:
        return []
    return cur.fetchmany(max_rows)


def _rows_to_dicts(cur: pyodbc.Cursor, rows: Sequence[Any]) -> list[dict[str, Any]]:
    if not rows or not cur.description:
        return []
    columns = [col[0] for col in cur.description]
    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for index, value in enumerate(row):
            if isinstance(value, (datetime,)):
                item[columns[index]] = value.isoformat()
            else:
                item[columns[index]] = value
        out.append(item)
    return out


def _strip_sql_comments_and_literals(sql: str) -> str:
    if not sql:
        return ""
    s = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    s = re.sub(r"--.*?(\r\n|\r|\n|$)", " ", s)
    s = re.sub(r"'(?:''|[^'])*'", " ", s)
    s = re.sub(r'"(?:""|[^"])*"', " ", s)
    return s


def _is_sql_readonly(sql: str) -> bool:
    cleaned = _strip_sql_comments_and_literals(sql)
    if not cleaned.strip():
        return False
    if re.search(
        r"\b(insert|update|delete|merge|drop|create|alter|truncate|grant|revoke|deny|exec|execute|backup|restore|dbcc)\b",
        cleaned,
        flags=re.I,
    ):
        return False
    return bool(re.search(r"\b(select|with)\b", cleaned, flags=re.I))


def _require_readonly(sql: str) -> None:
    if not _is_sql_readonly(sql):
        raise ValueError("Write operations are disabled. Query contains write statements.")


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(value: str, label: str = "identifier") -> str:
    if not value or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def _quoted_ident(value: str) -> str:
    return f"[{value.replace(']', ']]')}]"


def _execute_in_database(
    cur: pyodbc.Cursor,
    database_name: str,
    sql: str,
    params: list[Any] | tuple[Any, ...] | None = None,
) -> None:
    _validate_identifier(database_name, "database")
    _execute_safe(cur, f"USE {_quoted_ident(database_name)}")
    _execute_safe(cur, sql, params)


def _ensure_write_enabled() -> None:
    if not SETTINGS.allow_write:
        raise ValueError("Write operations are disabled. Set MCP_ALLOW_WRITE=true and MCP_CONFIRM_WRITE=true.")


# FastMCP app initialization
mcp = FastMCP(name=os.getenv("MCP_SERVER_NAME", "SQL Server MCP Server"))
app = mcp


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path == "/mcp" and request.method == "GET":
            return RedirectResponse(url="/sse")

        if path.startswith("/sse") or path.startswith("/messages") or path.startswith("/mcp"):
            if SETTINGS.auth_type == "apikey":
                token = None
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header.split(" ", 1)[1].strip()
                if token is None:
                    token = request.query_params.get("token") or request.query_params.get("api_key")

                if not SETTINGS.api_key:
                    return JSONResponse({"detail": "Server API key is not configured."}, status_code=500)
                if not token:
                    return JSONResponse({"detail": "Missing Authorization token."}, status_code=401)
                if token != SETTINGS.api_key:
                    return JSONResponse({"detail": "Invalid API key."}, status_code=403)

        return await call_next(request)


class BrowserFriendlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/mcp" and "text/html" in request.headers.get("accept", ""):
            return HTMLResponse(
                "<html><body><h2>SQL Server MCP Server</h2>"
                "<p>This endpoint is for MCP clients. Use /sse for stream transport.</p></body></html>"
            )
        return await call_next(request)


def _resolve_http_app() -> Any | None:
    candidate = getattr(mcp, "http_app", None)
    if candidate is None:
        return None
    if callable(candidate):
        try:
            candidate = candidate()
        except TypeError:
            return None
    if hasattr(candidate, "add_middleware"):
        return candidate
    return None


HTTP_APP = _resolve_http_app()
if HTTP_APP is not None:
    HTTP_APP.add_middleware(APIKeyMiddleware)
    HTTP_APP.add_middleware(BrowserFriendlyMiddleware)


@mcp.tool
def db_sql2019_ping() -> dict[str, Any]:
    """Basic connectivity probe."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        _execute_safe(cur, "SELECT 1 AS ok")
        row = cur.fetchone()
        return {
            "status": "ok",
            "database": SETTINGS.db_name,
            "server": SETTINGS.db_server,
            "result": int(row[0]) if row else 1,
            "timestamp": _now_utc_iso(),
        }
    finally:
        conn.close()


@mcp.tool
def db_sql2019_list_databases() -> list[str]:
    """List online databases visible to the current login."""
    conn = get_connection("master")
    try:
        cur = conn.cursor()
        _execute_safe(
            cur,
            """
            SELECT name
            FROM sys.databases
            WHERE state_desc = 'ONLINE'
            ORDER BY name
            """,
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


@mcp.tool
def db_sql2019_list_tables(database_name: str, schema_name: str | None = None) -> list[dict[str, Any]]:
    """List tables for a database/schema."""
    conn = get_connection(database_name)
    try:
        cur = conn.cursor()
        if schema_name:
            _execute_safe(
                cur,
                """
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_SCHEMA = ?
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """,
                [schema_name],
            )
        else:
            _execute_safe(
                cur,
                """
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """,
            )
        rows = cur.fetchall()
        return [{"TABLE_SCHEMA": row[0], "TABLE_NAME": row[1]} for row in rows]
    finally:
        conn.close()


@mcp.tool
def db_sql2019_get_schema(database_name: str, table_name: str, schema_name: str = "dbo") -> dict[str, Any]:
    """Get column metadata for a table."""
    conn = get_connection(database_name)
    try:
        cur = conn.cursor()
        _execute_safe(
            cur,
            """
            SELECT
                c.COLUMN_NAME,
                c.ORDINAL_POSITION,
                c.DATA_TYPE,
                c.IS_NULLABLE,
                c.CHARACTER_MAXIMUM_LENGTH,
                c.NUMERIC_PRECISION,
                c.NUMERIC_SCALE,
                c.COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS c
            WHERE c.TABLE_SCHEMA = ? AND c.TABLE_NAME = ?
            ORDER BY c.ORDINAL_POSITION
            """,
            [schema_name, table_name],
        )
        rows = cur.fetchall()
        columns = [
            {
                "COLUMN_NAME": row[0],
                "ORDINAL_POSITION": row[1],
                "DATA_TYPE": row[2],
                "IS_NULLABLE": row[3],
                "CHARACTER_MAXIMUM_LENGTH": row[4],
                "NUMERIC_PRECISION": row[5],
                "NUMERIC_SCALE": row[6],
                "COLUMN_DEFAULT": row[7],
            }
            for row in rows
        ]
        return {
            "database": database_name,
            "schema": schema_name,
            "table": table_name,
            "columns": columns,
        }
    finally:
        conn.close()


def _parse_params_json(params_json: str | None) -> list[Any] | None:
    if not params_json:
        return None
    decoded = json.loads(params_json)
    if isinstance(decoded, list):
        return decoded
    if isinstance(decoded, dict):
        return [decoded]
    raise ValueError("params_json must decode to a list or object")


def _run_query_internal(
    database_name: str,
    sql: str,
    params_json: str | None = None,
    max_rows: int | None = None,
    enforce_readonly: bool = True,
) -> list[dict[str, Any]]:
    if enforce_readonly and not SETTINGS.allow_write:
        _require_readonly(sql)

    params = _parse_params_json(params_json)
    row_cap = max_rows if isinstance(max_rows, int) and max_rows > 0 else SETTINGS.max_rows

    conn = get_connection(database_name)
    try:
        cur = conn.cursor()
        _execute_safe(cur, sql, params)
        rows = _fetch_limited(cur, row_cap)
        return _rows_to_dicts(cur, rows)
    finally:
        conn.close()


@mcp.tool
def db_sql2019_execute_query(
    database_name: str,
    sql: str,
    params_json: str | None = None,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    """Legacy-compatible query executor (read-only unless write mode is enabled)."""
    return _run_query_internal(
        database_name=database_name,
        sql=sql,
        params_json=params_json,
        max_rows=max_rows,
        enforce_readonly=True,
    )


@mcp.tool
def db_sql2019_run_query(
    arg1: str,
    arg2: str | None = None,
    params_json: str | None = None,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    """Execute SQL; supports both legacy (db, sql) and new (sql only) signatures."""
    if arg2 is None:
        database_name = SETTINGS.db_name
        sql = arg1
    else:
        database_name = arg1
        sql = arg2

    return _run_query_internal(
        database_name=database_name,
        sql=sql,
        params_json=params_json,
        max_rows=max_rows,
        enforce_readonly=True,
    )


@mcp.tool
def db_sql2019_list_objects(
    database_name: str,
    object_type: str = "TABLE",
    object_name: str | None = None,
    schema: str | None = None,
    order_by: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]] | list[str]:
    """Unified object listing for database/schema/table/view/index/function/procedure/trigger."""
    conn = get_connection(database_name)
    try:
        cur = conn.cursor()
        object_type_norm = object_type.strip().upper()

        if object_type_norm in {"DATABASE", "DATABASES"}:
            return db_sql2019_list_databases()

        if object_type_norm in {"SCHEMA", "SCHEMAS"}:
            _execute_safe(cur, "SELECT name FROM sys.schemas ORDER BY name")
            return [row[0] for row in cur.fetchall()]

        if object_type_norm in {"TABLE", "VIEW"}:
            table_type = "BASE TABLE" if object_type_norm == "TABLE" else "VIEW"
            sql = (
                "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
                "FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_TYPE = ?"
            )
            params: list[Any] = [table_type]
            if schema:
                sql += " AND TABLE_SCHEMA = ?"
                params.append(schema)
            if object_name:
                sql += " AND TABLE_NAME LIKE ?"
                params.append(object_name)
            sql += " ORDER BY TABLE_SCHEMA, TABLE_NAME"
            _execute_safe(cur, sql, params)
            rows = _fetch_limited(cur, max(1, limit))
            return _rows_to_dicts(cur, rows)

        if object_type_norm == "INDEX":
            sql = """
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                i.name AS index_name,
                i.type_desc AS index_type,
                i.is_disabled
            FROM sys.indexes i
            JOIN sys.tables t ON i.object_id = t.object_id
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE i.name IS NOT NULL
            """
            params = []
            if schema:
                sql += " AND s.name = ?"
                params.append(schema)
            if object_name:
                sql += " AND i.name LIKE ?"
                params.append(object_name)
            sql += " ORDER BY s.name, t.name, i.name"
            _execute_safe(cur, sql, params)
            return _rows_to_dicts(cur, _fetch_limited(cur, max(1, limit)))

        if object_type_norm in {"FUNCTION", "PROCEDURE", "TRIGGER"}:
            code = {"FUNCTION": "FN", "PROCEDURE": "P", "TRIGGER": "TR"}[object_type_norm]
            sql = """
            SELECT s.name AS schema_name, o.name AS object_name, o.type_desc
            FROM sys.objects o
            JOIN sys.schemas s ON o.schema_id = s.schema_id
            WHERE o.type = ?
            """
            params = [code]
            if schema:
                sql += " AND s.name = ?"
                params.append(schema)
            if object_name:
                sql += " AND o.name LIKE ?"
                params.append(object_name)
            sql += " ORDER BY s.name, o.name"
            _execute_safe(cur, sql, params)
            return _rows_to_dicts(cur, _fetch_limited(cur, max(1, limit)))

        raise ValueError(f"Unsupported object_type: {object_type}")
    finally:
        conn.close()


def _get_index_fragmentation_data(
    database_name: str,
    schema: str | None = None,
    min_fragmentation: float = 10.0,
    min_page_count: int = 100,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = get_connection(database_name)
    try:
        cur = conn.cursor()
        sql = """
        SELECT TOP (?)
            s.name AS schema_name,
            t.name AS table_name,
            i.name AS index_name,
            ips.avg_fragmentation_in_percent,
            ips.page_count,
            i.type_desc AS index_type
        FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'SAMPLED') ips
        JOIN sys.indexes i
            ON ips.object_id = i.object_id AND ips.index_id = i.index_id
        JOIN sys.tables t ON i.object_id = t.object_id
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE i.name IS NOT NULL
          AND ips.page_count >= ?
          AND ips.avg_fragmentation_in_percent >= ?
        """
        params: list[Any] = [max(1, limit), min_page_count, min_fragmentation]
        if schema:
            sql += " AND s.name = ?"
            params.append(schema)
        sql += " ORDER BY ips.avg_fragmentation_in_percent DESC"

        _execute_safe(cur, sql, params)
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


@mcp.tool
def db_sql2019_get_index_fragmentation(
    database_name: str,
    schema: str | None = None,
    min_fragmentation: float = 10.0,
    min_page_count: int = 100,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return index fragmentation rows from dm_db_index_physical_stats."""
    return _get_index_fragmentation_data(
        database_name=database_name,
        schema=schema,
        min_fragmentation=min_fragmentation,
        min_page_count=min_page_count,
        limit=limit,
    )


@mcp.tool
def db_sql2019_analyze_index_health(
    database_name: str,
    schema: str | None = None,
    min_fragmentation: float = 10.0,
    min_page_count: int = 100,
    limit: int = 50,
) -> dict[str, Any]:
    """High-level index health summary."""
    items = _get_index_fragmentation_data(
        database_name=database_name,
        schema=schema,
        min_fragmentation=min_fragmentation,
        min_page_count=min_page_count,
        limit=limit,
    )

    severe = [r for r in items if (r.get("avg_fragmentation_in_percent") or 0) >= 30]
    medium = [r for r in items if 10 <= (r.get("avg_fragmentation_in_percent") or 0) < 30]

    return {
        "database": database_name,
        "schema": schema,
        "fragmented_indexes": items,
        "summary": {
            "severe": len(severe),
            "medium": len(medium),
            "total": len(items),
        },
    }


@mcp.tool
def db_sql2019_analyze_table_health(database_name: str, schema: str, table_name: str) -> dict[str, Any]:
    """Table-level storage/index/stats/constraint analysis."""
    conn = get_connection(database_name)
    try:
        cur = conn.cursor()

        _execute_safe(
            cur,
            """
            SELECT
                t.name AS TableName,
                s.name AS SchemaName,
                SUM(p.rows) AS RowCounts,
                SUM(a.total_pages) * 8 AS TotalSpaceKB,
                SUM(a.used_pages) * 8 AS UsedSpaceKB,
                (SUM(a.total_pages) - SUM(a.used_pages)) * 8 AS UnusedSpaceKB
            FROM sys.tables t
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            JOIN sys.indexes i ON t.object_id = i.object_id
            JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
            JOIN sys.allocation_units a ON p.partition_id = a.container_id
            WHERE s.name = ? AND t.name = ?
            GROUP BY t.name, s.name
            """,
            [schema, table_name],
        )
        table_info_rows = _rows_to_dicts(cur, cur.fetchall())
        table_info = table_info_rows[0] if table_info_rows else {}

        _execute_safe(
            cur,
            """
            SELECT i.name AS IndexName, i.type_desc AS IndexType,
                   CAST(SUM(a.used_pages) * 8.0 / 1024 AS DECIMAL(18, 4)) AS IndexSizeMB,
                   i.is_disabled
            FROM sys.indexes i
            JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
            JOIN sys.allocation_units a ON p.partition_id = a.container_id
            JOIN sys.tables t ON i.object_id = t.object_id
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE s.name = ? AND t.name = ? AND i.name IS NOT NULL
            GROUP BY i.name, i.type_desc, i.is_disabled
            ORDER BY IndexSizeMB DESC
            """,
            [schema, table_name],
        )
        indexes = _rows_to_dicts(cur, cur.fetchall())

        _execute_safe(
            cur,
            """
            SELECT
                fk.name AS FK_Name,
                OBJECT_NAME(fk.parent_object_id) AS ParentTable,
                pc.name AS ParentColumn,
                OBJECT_NAME(fk.referenced_object_id) AS ReferencedTable,
                rc.name AS ReferencedColumn
            FROM sys.foreign_keys fk
            JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
            JOIN sys.columns pc ON fkc.parent_object_id = pc.object_id AND fkc.parent_column_id = pc.column_id
            JOIN sys.columns rc ON fkc.referenced_object_id = rc.object_id AND fkc.referenced_column_id = rc.column_id
            WHERE OBJECT_SCHEMA_NAME(fk.parent_object_id) = ?
              AND OBJECT_NAME(fk.parent_object_id) = ?
            ORDER BY fk.name
            """,
            [schema, table_name],
        )
        foreign_keys = _rows_to_dicts(cur, cur.fetchall())

        _execute_safe(
            cur,
            """
            SELECT TOP 25
                c.name AS ColumnName,
                st.name AS StatsName,
                sp.last_updated,
                sp.rows,
                sp.rows_sampled,
                sp.modification_counter
            FROM sys.stats st
            JOIN sys.stats_columns sc ON st.object_id = sc.object_id AND st.stats_id = sc.stats_id
            JOIN sys.columns c ON sc.object_id = c.object_id AND sc.column_id = c.column_id
            OUTER APPLY sys.dm_db_stats_properties(st.object_id, st.stats_id) sp
            JOIN sys.tables t ON st.object_id = t.object_id
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE s.name = ? AND t.name = ?
            ORDER BY st.name
            """,
            [schema, table_name],
        )
        statistics_sample = _rows_to_dicts(cur, cur.fetchall())

        _execute_safe(
            cur,
            """
            SELECT
                fk.name AS fk_name,
                pc.name AS column_name,
                CASE WHEN ix.index_id IS NULL THEN 1 ELSE 0 END AS missing_index
            FROM sys.foreign_keys fk
            JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
            JOIN sys.columns pc ON fkc.parent_object_id = pc.object_id AND fkc.parent_column_id = pc.column_id
            LEFT JOIN sys.index_columns ic
              ON ic.object_id = fkc.parent_object_id AND ic.column_id = fkc.parent_column_id AND ic.key_ordinal = 1
            LEFT JOIN sys.indexes ix
              ON ix.object_id = ic.object_id AND ix.index_id = ic.index_id
            WHERE OBJECT_SCHEMA_NAME(fk.parent_object_id) = ?
              AND OBJECT_NAME(fk.parent_object_id) = ?
            """,
            [schema, table_name],
        )
        fk_index_checks = _rows_to_dicts(cur, cur.fetchall())

        constraint_issues: list[dict[str, Any]] = []
        recommendations: list[dict[str, Any]] = []
        for fk in fk_index_checks:
            if fk.get("missing_index") == 1:
                fk_name = fk.get("fk_name")
                column_name = fk.get("column_name")
                constraint_issues.append(
                    {
                        "type": "Unindexed Foreign Key",
                        "message": (
                            f"Warning: Foreign key '{fk_name}' on column '{column_name}' "
                            "is not indexed. This can impact joins and cascading operations."
                        ),
                    }
                )
                recommendations.append(
                    {
                        "severity": "Medium",
                        "recommendation": f"Create index on '{column_name}' to support foreign key '{fk_name}'.",
                    }
                )

        return {
            "table_info": table_info,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
            "statistics_sample": statistics_sample,
            "health_analysis": {
                "constraint_issues": constraint_issues,
                "index_issues": [],
            },
            "recommendations": recommendations,
        }
    finally:
        conn.close()


@mcp.tool
def db_sql2019_db_stats(database: str | None = None) -> dict[str, Any]:
    """Database object counts."""
    db_name = database or SETTINGS.db_name
    conn = get_connection(db_name)
    try:
        cur = conn.cursor()
        _execute_safe(
            cur,
            """
            SELECT
                DB_NAME() AS DatabaseName,
                (SELECT COUNT(*) FROM sys.tables) AS TableCount,
                (SELECT COUNT(*) FROM sys.views) AS ViewCount,
                (SELECT COUNT(*) FROM sys.procedures) AS ProcedureCount,
                (SELECT COUNT(*) FROM sys.indexes WHERE name IS NOT NULL) AS IndexCount,
                (SELECT COUNT(*) FROM sys.schemas) AS SchemaCount
            """,
        )
        row = cur.fetchone()
        if not row:
            return {"DatabaseName": db_name}
        return {
            "DatabaseName": row[0],
            "TableCount": row[1],
            "ViewCount": row[2],
            "ProcedureCount": row[3],
            "IndexCount": row[4],
            "SchemaCount": row[5],
        }
    finally:
        conn.close()


@mcp.tool
def db_sql2019_server_info_mcp() -> dict[str, Any]:
    """Get SQL Server and MCP runtime information."""
    conn = get_connection("master")
    try:
        cur = conn.cursor()
        _execute_safe(
            cur,
            """
            SELECT
                @@VERSION AS server_version,
                @@SERVERNAME AS server_name,
                DB_NAME() AS database_name,
                SUSER_SNAME() AS login_name,
                CONVERT(varchar(128), SERVERPROPERTY('ProductVersion')) AS server_version_short,
                CONVERT(varchar(128), SERVERPROPERTY('Edition')) AS server_edition
            """,
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Could not retrieve server information")
        return {
            "server_version": row[0],
            "server_name": row[1],
            "database": row[2],
            "user": row[3],
            "server_version_short": row[4],
            "server_edition": row[5],
            "server_addr": SETTINGS.db_server,
            "server_port": SETTINGS.db_port,
            "mcp_transport": SETTINGS.transport,
            "mcp_max_rows": SETTINGS.max_rows,
            "mcp_allow_write": SETTINGS.allow_write,
        }
    finally:
        conn.close()


@mcp.tool
def db_sql2019_show_top_queries(database_name: str) -> dict[str, Any]:
    """Query Store summary for high-cost queries."""
    conn = get_connection(database_name)
    try:
        cur = conn.cursor()

        _execute_safe(
            cur,
            """
            SELECT actual_state_desc, desired_state_desc, current_storage_size_mb, max_storage_size_mb
            FROM sys.database_query_store_options
            """,
        )
        qs = cur.fetchone()
        query_store_enabled = bool(qs and str(qs[0]).upper() not in {"OFF", "ERROR"})

        output: dict[str, Any] = {
            "database": database_name,
            "query_store_enabled": query_store_enabled,
            "query_store_config": {
                "state": qs[0] if qs else None,
                "desired_state": qs[1] if qs else None,
                "current_storage_mb": qs[2] if qs else None,
                "max_storage_mb": qs[3] if qs else None,
            },
            "long_running_queries": [],
            "regressed_queries": [],
            "high_cpu_queries": [],
            "high_io_queries": [],
            "high_execution_queries": [],
            "recommendations": [],
            "summary": {},
        }

        if not query_store_enabled:
            output["summary"] = {
                "long_running_queries_count": 0,
                "regressed_queries_count": 0,
                "high_cpu_queries_count": 0,
                "high_io_queries_count": 0,
                "high_execution_queries_count": 0,
                "total_recommendations": 1,
                "high_priority_recommendations": 1,
                "analysis_timestamp": _now_utc_iso(),
            }
            output["recommendations"].append(
                {
                    "type": "query_store",
                    "priority": "high",
                    "issue": "Query Store is disabled",
                    "recommendation": f"Enable Query Store: ALTER DATABASE [{database_name}] SET QUERY_STORE = ON;",
                }
            )
            return output

        _execute_safe(
            cur,
            """
            SELECT TOP 10
                q.query_id,
                qt.query_sql_text,
                SUM(rs.count_executions) AS executions,
                CAST(AVG(rs.avg_duration) / 1000.0 AS DECIMAL(18,2)) AS avg_duration_ms,
                CAST(AVG(rs.avg_cpu_time) / 1000.0 AS DECIMAL(18,2)) AS avg_cpu_ms,
                CAST(AVG(rs.avg_logical_io_reads) AS DECIMAL(18,2)) AS avg_logical_io_reads
            FROM sys.query_store_query q
            JOIN sys.query_store_query_text qt ON q.query_text_id = qt.query_text_id
            JOIN sys.query_store_plan p ON q.query_id = p.query_id
            JOIN sys.query_store_runtime_stats rs ON p.plan_id = rs.plan_id
            GROUP BY q.query_id, qt.query_sql_text
            ORDER BY AVG(rs.avg_duration) DESC
            """,
        )
        long_running = _rows_to_dicts(cur, cur.fetchall())
        output["long_running_queries"] = long_running[:3]
        output["high_cpu_queries"] = sorted(long_running, key=lambda x: x.get("avg_cpu_ms") or 0, reverse=True)[:3]
        output["high_io_queries"] = sorted(
            long_running,
            key=lambda x: x.get("avg_logical_io_reads") or 0,
            reverse=True,
        )[:5]
        output["high_execution_queries"] = sorted(
            long_running,
            key=lambda x: x.get("executions") or 0,
            reverse=True,
        )[:5]

        recommendations: list[dict[str, Any]] = []
        for query_row in output["long_running_queries"]:
            recommendations.append(
                {
                    "type": "long_running_query",
                    "priority": "high",
                    "query_id": query_row.get("query_id"),
                    "issue": f"Query average duration {query_row.get('avg_duration_ms')}ms",
                    "recommendation": "Inspect execution plan and add/adjust indexes for join/filter columns.",
                }
            )

        output["recommendations"] = recommendations
        output["summary"] = {
            "long_running_queries_count": len(output["long_running_queries"]),
            "regressed_queries_count": len(output["regressed_queries"]),
            "high_cpu_queries_count": len(output["high_cpu_queries"]),
            "high_io_queries_count": len(output["high_io_queries"]),
            "high_execution_queries_count": len(output["high_execution_queries"]),
            "total_recommendations": len(recommendations),
            "high_priority_recommendations": len([r for r in recommendations if r.get("priority") == "high"]),
            "analysis_timestamp": _now_utc_iso(),
        }
        return output
    finally:
        conn.close()


@mcp.tool
def db_sql2019_check_fragmentation(
    database_name: str,
    min_fragmentation: float = 10.0,
    min_page_count: int = 100,
    include_recommendations: bool = True,
) -> dict[str, Any]:
    """Fragmentation summary with maintenance recommendations."""
    fragmented_indexes = _get_index_fragmentation_data(
        database_name=database_name,
        schema=None,
        min_fragmentation=min_fragmentation,
        min_page_count=min_page_count,
        limit=200,
    )

    summary = {"severe": 0, "high": 0, "medium": 0, "low": 0}
    top_items: list[dict[str, Any]] = []
    fix_commands: list[str] = []

    for row in fragmented_indexes:
        frag = float(row.get("avg_fragmentation_in_percent") or 0)
        category = "LOW"
        action = "MONITOR"
        key = "low"

        if frag >= 40:
            category = "SEVERE"
            action = "REBUILD"
            key = "severe"
        elif frag >= 30:
            category = "HIGH"
            action = "REBUILD"
            key = "high"
        elif frag >= 10:
            category = "MEDIUM"
            action = "REORGANIZE"
            key = "medium"

        summary[key] += 1

        enriched = {
            "schema": row.get("schema_name"),
            "table_name": row.get("table_name"),
            "index_name": row.get("index_name"),
            "fragmentation_percent": frag,
            "category": category,
            "page_count": row.get("page_count"),
            "recommended_action": action,
        }
        top_items.append(enriched)

        if action in {"REBUILD", "REORGANIZE"} and row.get("index_name"):
            fix_commands.append(
                f"ALTER INDEX [{row['index_name']}] ON [{row['schema_name']}].[{row['table_name']}] {action};"
            )

    output = {
        "database": database_name,
        "analysis_timestamp": _now_utc_iso(),
        "total_fragmented_indexes": len(fragmented_indexes),
        "fragmentation_summary": summary,
        "top_fragmented_indexes": top_items[:10],
        "fix_commands": fix_commands[:20],
        "maintenance_plan": {
            "immediate": summary["severe"] + summary["high"],
            "this_week": summary["medium"],
            "this_month": summary["low"],
            "monitoring": 0,
        },
        "recommendations": [],
    }

    if include_recommendations:
        recs: list[dict[str, Any]] = []
        if summary["severe"] + summary["high"] > 0:
            recs.append(
                {
                    "category": "MAINTENANCE",
                    "message": "High/severe fragmentation found. Rebuild those indexes in maintenance window.",
                    "action": "Run ALTER INDEX ... REBUILD",
                }
            )
        if summary["medium"] > 0:
            recs.append(
                {
                    "category": "MAINTENANCE",
                    "message": "Medium fragmentation found. Reorganize indexes during low-usage periods.",
                    "action": "Run ALTER INDEX ... REORGANIZE",
                }
            )
        recs.append(
            {
                "category": "MONITORING",
                "message": "Use scheduled index maintenance and periodic fragmentation analysis.",
                "action": "Configure SQL Agent maintenance jobs.",
            }
        )
        output["recommendations"] = recs

    return output


@mcp.tool
def db_sql2019_db_sec_perf_metrics(profile: Literal["oltp", "olap", "mixed"] = "oltp") -> dict[str, Any]:
    """Security and performance quick audit."""
    conn = get_connection("master")
    try:
        cur = conn.cursor()

        login_audit: list[dict[str, Any]]
        permissions_audit: list[dict[str, Any]]
        security_config: dict[str, Any] = {}
        wait_stats: dict[str, Any] = {}
        memory_usage: dict[str, Any] = {}
        cpu_stats: dict[str, Any] = {}
        risk_factors: list[dict[str, Any]] = []

        _execute_safe(
            cur,
            """
            SELECT TOP 50 name, type_desc, is_disabled, create_date, modify_date, default_database_name
            FROM sys.server_principals
            WHERE type IN ('S', 'U', 'G')
            ORDER BY name
            """,
        )
        login_audit = _rows_to_dicts(cur, cur.fetchall())

        _execute_safe(
            cur,
            """
            SELECT TOP 100
                pr.name AS principal_name,
                pr.type_desc AS principal_type,
                pe.permission_name,
                pe.state_desc AS permission_state,
                pe.class_desc
            FROM sys.server_permissions pe
            JOIN sys.server_principals pr ON pe.grantee_principal_id = pr.principal_id
            ORDER BY pr.name
            """,
        )
        permissions_audit = _rows_to_dicts(cur, cur.fetchall())

        _execute_safe(
            cur,
            """
            SELECT
                CAST(SERVERPROPERTY('IsIntegratedSecurityOnly') AS INT) AS windows_auth_only,
                CAST(SERVERPROPERTY('ProductVersion') AS VARCHAR(128)) AS product_version,
                CAST(SERVERPROPERTY('Edition') AS VARCHAR(128)) AS edition
            """,
        )
        cfg = cur.fetchone()
        security_config = {
            "windows_auth_only": int(cfg[0]) if cfg else None,
            "product_version": cfg[1] if cfg else None,
            "edition": cfg[2] if cfg else None,
        }

        _execute_safe(
            cur,
            """
            SELECT TOP 10 wait_type, waiting_tasks_count, wait_time_ms
            FROM sys.dm_os_wait_stats
            WHERE wait_type NOT LIKE 'SLEEP%'
            ORDER BY wait_time_ms DESC
            """,
        )
        wait_stats = {"top_waits": _rows_to_dicts(cur, cur.fetchall())}

        _execute_safe(
            cur,
            """
            SELECT
                total_physical_memory_kb,
                available_physical_memory_kb,
                system_cache_kb,
                system_memory_state_desc
            FROM sys.dm_os_sys_memory
            """,
        )
        mem = cur.fetchone()
        memory_usage = {
            "total_physical_memory_kb": mem[0] if mem else None,
            "available_physical_memory_kb": mem[1] if mem else None,
            "system_cache_kb": mem[2] if mem else None,
            "system_memory_state_desc": mem[3] if mem else None,
        }

        _execute_safe(
            cur,
            """
            SELECT TOP 1 sqlserver_start_time, cpu_count, scheduler_count
            FROM sys.dm_os_sys_info
            """,
        )
        cpu = cur.fetchone()
        cpu_stats = {
            "sqlserver_start_time": cpu[0].isoformat() if cpu and cpu[0] else None,
            "cpu_count": cpu[1] if cpu else None,
            "scheduler_count": cpu[2] if cpu else None,
        }

        if any((row.get("is_disabled") is False and "sa" in str(row.get("name", "")).lower()) for row in login_audit):
            risk_factors.append(
                {
                    "category": "security",
                    "severity": "medium",
                    "issue": "Built-in sa login appears enabled",
                    "recommendation": "Disable sa login when not required.",
                }
            )

        overall_risk_score = min(100, len(risk_factors) * 15)
        risk_level = "LOW" if overall_risk_score < 30 else "MEDIUM" if overall_risk_score < 70 else "HIGH"

        return {
            "profile": profile,
            "analysis_timestamp": _now_utc_iso(),
            "security_assessment": {
                "login_audit": login_audit,
                "permissions_audit": permissions_audit,
                "security_config": security_config,
            },
            "performance_metrics": {
                "wait_stats": wait_stats,
                "memory_usage": memory_usage,
                "cpu_stats": cpu_stats,
            },
            "risk_assessment": {
                "overall_risk_score": overall_risk_score,
                "risk_level": risk_level,
                "risk_factors": risk_factors,
                "profile_specific_metrics": {
                    "profile": profile,
                    "compliance_status": "COMPLIANT" if overall_risk_score < 50 else "ATTENTION_REQUIRED",
                },
            },
            "recommendations": risk_factors,
        }
    finally:
        conn.close()


@mcp.tool
def db_sql2019_explain_query(sql: str, analyze: bool = False, output_format: str = "xml") -> dict[str, Any]:
    """Return estimated or actual XML execution plan."""
    if output_format.lower() != "xml":
        raise ValueError("Only XML output_format is currently supported.")
    if not SETTINGS.allow_write:
        _require_readonly(sql)

    conn = get_connection(SETTINGS.db_name)
    try:
        cur = conn.cursor()
        if analyze:
            _execute_safe(cur, "SET STATISTICS XML ON")
            _execute_safe(cur, sql)
            rows = cur.fetchall()
            _execute_safe(cur, "SET STATISTICS XML OFF")
            last = rows[-1][0] if rows else None
            return {"format": "xml", "analyze": True, "plan_xml": last}

        _execute_safe(cur, f"SET SHOWPLAN_XML ON; {sql}; SET SHOWPLAN_XML OFF;")
        plan_rows = cur.fetchall()
        return {
            "format": "xml",
            "analyze": False,
            "plan_xml": plan_rows[0][0] if plan_rows else None,
        }
    finally:
        conn.close()


def _fetch_relationships(
    cur: pyodbc.Cursor,
    schema: str,
    include_views: bool,
    max_entities: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    object_types = ["U"] + (["V"] if include_views else [])
    placeholders = ", ".join("?" for _ in object_types)

    sql_entities = f"""
    SELECT t.object_id, s.name AS schema_name, t.name AS entity_name, t.type
    FROM sys.objects t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE t.type IN ({placeholders}) AND s.name = ?
    ORDER BY t.name
    """
    params: list[Any] = list(object_types) + [schema]
    _execute_safe(cur, sql_entities, params)
    entities = _rows_to_dicts(cur, cur.fetchall())
    if max_entities is not None and max_entities > 0:
        entities = entities[:max_entities]

    _execute_safe(
        cur,
        """
        SELECT
            fk.name AS name,
            OBJECT_SCHEMA_NAME(fk.parent_object_id) AS from_schema,
            OBJECT_NAME(fk.parent_object_id) AS from_entity,
            OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS to_schema,
            OBJECT_NAME(fk.referenced_object_id) AS to_entity
        FROM sys.foreign_keys fk
        WHERE OBJECT_SCHEMA_NAME(fk.parent_object_id) = ?
        ORDER BY fk.name
        """,
        [schema],
    )
    relationships = _rows_to_dicts(cur, cur.fetchall())
    return entities, relationships


@mcp.tool
def db_sql2019_analyze_logical_data_model(
    database_name: str,
    schema: str = "dbo",
    include_views: bool = False,
    max_entities: int | None = None,
    include_attributes: bool = True,
) -> dict[str, Any]:
    """Analyze schema entities and relationships."""
    return _analyze_logical_data_model_internal(
        database_name=database_name,
        schema=schema,
        include_views=include_views,
        max_entities=max_entities,
        include_attributes=include_attributes,
    )


def _analyze_logical_data_model_internal(
    database_name: str,
    schema: str = "dbo",
    include_views: bool = False,
    max_entities: int | None = None,
    include_attributes: bool = True,
) -> dict[str, Any]:
    conn = get_connection(database_name)
    try:
        cur = conn.cursor()
        entities, relationships = _fetch_relationships(cur, schema, include_views, max_entities)

        if include_attributes:
            for entity in entities:
                _execute_safe(
                    cur,
                    """
                    SELECT c.name, c.column_id, ty.name, c.is_nullable, c.max_length, c.precision, c.scale
                    FROM sys.columns c
                    JOIN sys.types ty ON c.user_type_id = ty.user_type_id
                    WHERE c.object_id = OBJECT_ID(?)
                    ORDER BY c.column_id
                    """,
                    [f"[{entity['schema_name']}].[{entity['entity_name']}]"] ,
                )
                attrs = _rows_to_dicts(cur, cur.fetchall())
                entity["attributes"] = attrs

        return {
            "summary": {
                "database": database_name,
                "schema": schema,
                "generated_at_utc": _now_utc_iso(),
                "entities": len(entities),
                "relationships": len(relationships),
                "issues_count": {
                    "entities": 0,
                    "attributes": 0,
                    "relationships": 0,
                    "identifiers": 0,
                    "normalization": 0,
                },
            },
            "logical_model": {
                "entities": entities,
                "relationships": [
                    {
                        "name": rel["name"],
                        "from_entity": f"{rel['from_schema']}.{rel['from_entity']}",
                        "to_entity": f"{rel['to_schema']}.{rel['to_entity']}",
                    }
                    for rel in relationships
                ],
            },
            "issues": {
                "entities": [],
                "attributes": [],
                "relationships": [],
                "identifiers": [],
                "normalization": [],
            },
            "recommendations": {
                "entities": [],
                "attributes": [],
                "relationships": [],
                "identifiers": [],
                "normalization": [],
            },
        }
    finally:
        conn.close()


_OPEN_MODEL_CACHE: dict[str, dict[str, Any]] = {}


@mcp.tool
def db_sql2019_open_logical_model(database_name: str) -> dict[str, Any]:
    """Generate a URL to the in-memory logical model snapshot."""
    model = _analyze_logical_data_model_internal(database_name)
    model_id = str(uuid.uuid4())
    _OPEN_MODEL_CACHE[model_id] = model
    base = f"http://localhost:{SETTINGS.port}"
    return {
        "message": f"ERD webpage generated for database '{database_name}'.",
        "database": database_name,
        "erd_url": f"{base}/data-model-analysis?id={model_id}",
        "summary": model.get("summary", {}),
    }


@mcp.tool
def db_sql2019_generate_ddl(database_name: str, object_name: str, object_type: str) -> dict[str, Any]:
    """Generate CREATE script for table/view/procedure/function/trigger object."""
    conn = get_connection(database_name)
    try:
        cur = conn.cursor()
        object_type_norm = object_type.lower()

        if object_type_norm == "table":
            _execute_safe(
                cur,
                """
                SELECT
                    c.name AS column_name,
                    ty.name AS data_type,
                    c.max_length AS max_length,
                    c.precision AS numeric_precision,
                    c.scale AS numeric_scale,
                    c.is_nullable AS is_nullable
                FROM sys.columns c
                JOIN sys.types ty ON c.user_type_id = ty.user_type_id
                JOIN sys.tables t ON c.object_id = t.object_id
                WHERE t.name = ?
                ORDER BY c.column_id
                """,
                [object_name],
            )
            cols = _rows_to_dicts(cur, cur.fetchall())
            if not cols:
                return {
                    "database_name": database_name,
                    "object_name": object_name,
                    "object_type": object_type,
                    "success": False,
                    "error": "Object not found",
                }

            col_lines = []

            def _render_type(col: dict[str, Any]) -> str:
                data_type = str(col.get("data_type", "nvarchar"))
                max_length = col.get("max_length")
                precision = col.get("numeric_precision")
                scale = col.get("numeric_scale")

                if data_type in {"nvarchar", "nchar"} and isinstance(max_length, int):
                    size = "max" if max_length == -1 else str(max_length // 2)
                    return f"{data_type}({size})"
                if data_type in {"varchar", "char", "varbinary", "binary"} and isinstance(max_length, int):
                    size = "max" if max_length == -1 else str(max_length)
                    return f"{data_type}({size})"
                if data_type in {"decimal", "numeric"} and precision is not None and scale is not None:
                    return f"{data_type}({precision},{scale})"
                if data_type in {"datetime2", "datetimeoffset", "time"} and scale is not None:
                    return f"{data_type}({scale})"
                return data_type

            for col in cols:
                data_type = _render_type(col)
                nullable = "NULL" if col.get("is_nullable") else "NOT NULL"
                col_lines.append(f"    [{col['column_name']}] {data_type} {nullable}")
            ddl = f"CREATE TABLE [dbo].[{object_name}] (\n" + ",\n".join(col_lines) + "\n);"

            return {
                "database_name": database_name,
                "object_name": object_name,
                "object_type": object_type,
                "success": True,
                "metadata": {},
                "dependencies": [],
                "ddl": ddl,
            }

        _execute_safe(cur, "SELECT OBJECT_DEFINITION(OBJECT_ID(?))", [object_name])
        row = cur.fetchone()
        ddl = row[0] if row and row[0] else None
        return {
            "database_name": database_name,
            "object_name": object_name,
            "object_type": object_type,
            "success": ddl is not None,
            "metadata": {},
            "dependencies": [],
            "ddl": ddl,
        }
    finally:
        conn.close()


@mcp.tool
def db_sql2019_create_db_user(
    username: str,
    password: str,
    privileges: Literal["read", "readwrite"] | str = "read",
    database: str | None = None,
) -> dict[str, Any]:
    """Create SQL login/user and grant role permissions."""
    _ensure_write_enabled()
    db_name = database or SETTINGS.db_name
    safe_user = _validate_identifier(username, "username")

    conn = get_connection("master")
    try:
        cur = conn.cursor()
        _execute_safe(cur, f"CREATE LOGIN {_quoted_ident(safe_user)} WITH PASSWORD = ?", [password])
        _execute_in_database(cur, db_name, f"CREATE USER {_quoted_ident(safe_user)} FOR LOGIN {_quoted_ident(safe_user)}")

        role = "db_datareader"
        if str(privileges).lower() in {"rw", "readwrite", "write"}:
            role = "db_datawriter"
        _execute_in_database(cur, db_name, f"ALTER ROLE {_quoted_ident(role)} ADD MEMBER {_quoted_ident(safe_user)}")

        return {
            "status": "success",
            "database": db_name,
            "username": safe_user,
            "role": role,
        }
    finally:
        conn.close()


@mcp.tool
def db_sql2019_drop_db_user(username: str, database: str | None = None) -> dict[str, Any]:
    """Drop SQL user and login if present."""
    _ensure_write_enabled()
    db_name = database or SETTINGS.db_name
    safe_user = _validate_identifier(username, "username")

    conn = get_connection("master")
    try:
        cur = conn.cursor()
        _execute_in_database(
            cur,
            db_name,
            (
                "IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = ?) "
                f"DROP USER {_quoted_ident(safe_user)}"
            ),
            [safe_user],
        )
        _execute_safe(
            cur,
            (
                "IF EXISTS (SELECT 1 FROM sys.server_principals WHERE name = ?) "
                f"DROP LOGIN {_quoted_ident(safe_user)}"
            ),
            [safe_user],
        )
        return {
            "status": "success",
            "database": db_name,
            "username": safe_user,
        }
    finally:
        conn.close()


@mcp.tool
def db_sql2019_kill_session(session_id: int) -> dict[str, Any]:
    """Terminate a SQL Server session."""
    _ensure_write_enabled()
    if session_id <= 0:
        raise ValueError("session_id must be > 0")

    conn = get_connection("master")
    try:
        cur = conn.cursor()
        _execute_safe(cur, "SELECT @@SPID")
        spid_row = cur.fetchone()
        if spid_row is None:
            raise RuntimeError("Could not determine current session id.")
        current_spid = int(spid_row[0])
        if session_id == current_spid:
            raise ValueError("Refusing to kill current MCP session.")

        _execute_safe(cur, f"KILL {session_id}")
        return {"status": "success", "session_id": session_id}
    finally:
        conn.close()


def _build_create_object_sql(object_type: str, object_name: str, schema: str, parameters: dict[str, Any] | None) -> str:
    params = parameters or {}
    object_type_norm = object_type.lower()
    fq_name = f"{_quoted_ident(schema)}.{_quoted_ident(object_name)}"

    if object_type_norm == "table":
        columns = params.get("columns")
        if not isinstance(columns, list) or not columns:
            raise ValueError("table creation requires parameters.columns list")
        col_defs = []
        for col in columns:
            col_name = _validate_identifier(col["name"], "column name")
            col_type = str(col["type"]).strip()
            nullable = "NULL" if col.get("nullable", True) else "NOT NULL"
            col_defs.append(f"{_quoted_ident(col_name)} {col_type} {nullable}")
        return f"CREATE TABLE {fq_name} (" + ", ".join(col_defs) + ")"

    if object_type_norm == "view":
        definition = params.get("definition")
        if not definition:
            raise ValueError("view creation requires parameters.definition")
        return f"CREATE VIEW {fq_name} AS {definition}"

    if object_type_norm == "index":
        table = params.get("table")
        columns = params.get("columns")
        if not table or not columns:
            raise ValueError("index creation requires parameters.table and parameters.columns")
        table_schema = params.get("table_schema", schema)
        return (
            f"CREATE INDEX {_quoted_ident(object_name)} ON "
            f"{_quoted_ident(table_schema)}.{_quoted_ident(_validate_identifier(table, 'table name'))}"
            f" ({', '.join(_quoted_ident(_validate_identifier(c, 'column')) for c in columns)})"
        )

    if object_type_norm in {"function", "procedure", "trigger"}:
        definition = params.get("definition")
        if not definition:
            raise ValueError(f"{object_type} creation requires parameters.definition")
        return str(definition)

    raise ValueError(f"Unsupported object_type: {object_type}")


@mcp.tool
def db_sql2019_create_object(
    object_type: str,
    object_name: str,
    schema: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create table/view/index/function/procedure/trigger."""
    _ensure_write_enabled()
    safe_schema = _validate_identifier(schema or "dbo", "schema")
    safe_name = _validate_identifier(object_name, "object name")

    sql = _build_create_object_sql(object_type, safe_name, safe_schema, parameters)

    conn = get_connection(SETTINGS.db_name)
    try:
        cur = conn.cursor()
        _execute_safe(cur, sql)
        return {
            "status": "success",
            "operation": "create",
            "object_type": object_type,
            "schema": safe_schema,
            "object_name": safe_name,
        }
    finally:
        conn.close()


@mcp.tool
def db_sql2019_alter_object(
    object_type: str,
    object_name: str,
    operation: str,
    schema: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Alter object using predefined operations."""
    _ensure_write_enabled()
    safe_schema = _validate_identifier(schema or "dbo", "schema")
    safe_name = _validate_identifier(object_name, "object name")
    operation_norm = operation.lower().strip()

    params = parameters or {}
    fq_name = f"{_quoted_ident(safe_schema)}.{_quoted_ident(safe_name)}"

    if operation_norm == "rename":
        new_name = _validate_identifier(str(params.get("new_name")), "new_name")
        sql = f"EXEC sp_rename '{safe_schema}.{safe_name}', '{new_name}'"
    elif operation_norm == "set_definition":
        definition = params.get("definition")
        if not definition:
            raise ValueError("set_definition requires parameters.definition")
        sql = str(definition)
    elif operation_norm == "add_column" and object_type.lower() == "table":
        column_name = _validate_identifier(str(params.get("name")), "column name")
        column_type = str(params.get("type", "nvarchar(255)"))
        nullable = "NULL" if params.get("nullable", True) else "NOT NULL"
        sql = f"ALTER TABLE {fq_name} ADD {_quoted_ident(column_name)} {column_type} {nullable}"
    else:
        raise ValueError(f"Unsupported alter operation: {operation}")

    conn = get_connection(SETTINGS.db_name)
    try:
        cur = conn.cursor()
        _execute_safe(cur, sql)
        return {
            "status": "success",
            "operation": operation,
            "object_type": object_type,
            "schema": safe_schema,
            "object_name": safe_name,
        }
    finally:
        conn.close()


@mcp.tool
def db_sql2019_drop_object(
    object_type: str,
    object_name: str,
    schema: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Drop object with optional IF EXISTS and CASCADE-like behavior where supported."""
    _ensure_write_enabled()
    _ = parameters or {}

    safe_schema = _validate_identifier(schema or "dbo", "schema")
    safe_name = _validate_identifier(object_name, "object name")
    object_type_norm = object_type.lower().strip()

    type_map = {
        "table": "TABLE",
        "view": "VIEW",
        "index": "INDEX",
        "function": "FUNCTION",
        "procedure": "PROCEDURE",
        "trigger": "TRIGGER",
    }
    if object_type_norm not in type_map:
        raise ValueError(f"Unsupported object_type: {object_type}")

    fq_name = f"{_quoted_ident(safe_schema)}.{_quoted_ident(safe_name)}"

    if object_type_norm == "index":
        table_name = (parameters or {}).get("table")
        table_schema = (parameters or {}).get("table_schema", safe_schema)
        if not table_name:
            raise ValueError("Dropping index requires parameters.table")
        safe_table_name = _validate_identifier(str(table_name), "table")
        safe_table_schema = _validate_identifier(str(table_schema), "table_schema")
        sql = (
            f"DROP INDEX {_quoted_ident(safe_name)} ON "
            f"{_quoted_ident(safe_table_schema)}.{_quoted_ident(safe_table_name)}"
        )
    else:
        sql = f"DROP {type_map[object_type_norm]} {fq_name}"

    conn = get_connection(SETTINGS.db_name)
    try:
        cur = conn.cursor()
        _execute_safe(cur, sql)
        return {
            "status": "success",
            "operation": "drop",
            "object_type": object_type,
            "schema": safe_schema,
            "object_name": safe_name,
        }
    finally:
        conn.close()


def _render_data_model_html(model_id: str, model: dict[str, Any]) -> str:
    summary = model.get("summary", {})
    entities = model.get("logical_model", {}).get("entities", [])
    relationships = model.get("logical_model", {}).get("relationships", [])
    return (
        "<html><head><title>Data Model Analysis</title></head><body>"
        f"<h2>Logical Model Report: {summary.get('database')}</h2>"
        f"<p>Report ID: {model_id}</p>"
        f"<p>Entities: {len(entities)} | Relationships: {len(relationships)}</p>"
        "<h3>Entities</h3><ul>"
        + "".join(f"<li>{e.get('schema_name')}.{e.get('entity_name')}</li>" for e in entities[:500])
        + "</ul></body></html>"
    )


if HTTP_APP is not None and hasattr(HTTP_APP, "add_route"):

    async def data_model_analysis_page(request: Request):
        model_id = request.query_params.get("id")
        if not model_id:
            return JSONResponse({"error": "Missing id query parameter"}, status_code=400)
        model = _OPEN_MODEL_CACHE.get(model_id)
        if not model:
            return JSONResponse({"error": "Model id not found"}, status_code=404)
        return HTMLResponse(_render_data_model_html(model_id, model))

    HTTP_APP.add_route("/data-model-analysis", data_model_analysis_page, methods=["GET"])


if __name__ == "__main__":
    transport = SETTINGS.transport
    logger.info(
        "Starting SQL Server MCP server",
        extra={
            "transport": transport,
            "host": SETTINGS.host,
            "port": SETTINGS.port,
            "allow_write": SETTINGS.allow_write,
        },
    )

    if transport in {"http", "sse"}:
        mcp.run(transport="http", host=SETTINGS.host, port=SETTINGS.port)
    else:
        mcp.run(transport="stdio")
