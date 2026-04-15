import queue
import logging
from logging.handlers import RotatingFileHandler
import os
import pathlib
import re
import json
import time
import base64
import hashlib
import uuid
import sys
from datetime import datetime, timezone
from threading import Lock
from contextvars import ContextVar
from typing import Any, Sequence, Literal, Union
from html import escape
from functools import wraps
import fastmcp
import pyodbc
from fastmcp import FastMCP


# --- Helper for normalizing db_name consistently ---
def _normalize_db_name(db_name: str | int | None) -> str | None:
    if db_name is None:
        return None
    if isinstance(db_name, str):
        return db_name
    return str(db_name)

# --- Connection Pool Wrapper ---

# --- Connection Pool Wrapper ---
class PooledConnection:
    """Wraps a pyodbc.Connection to override close() for pooling."""
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
    def __getattr__(self, name):
        return getattr(self._conn, name)
    def close(self):
        try:
            self._pool.put(self._conn, block=False)
        except queue.Full:
            self._conn.close()

# Generative UI support (FastMCP 3.2.0+)
try:
    from fastmcp.apps.generative import GenerativeUI
    GENERATIVE_UI_AVAILABLE = True
except ImportError:
    GenerativeUI = None  # type: ignore
    GENERATIVE_UI_AVAILABLE = False
    logger_temp = logging.getLogger("mcp_sqlserver")
    logger_temp.debug("GenerativeUI not available; fastmcp[apps] not installed")

logger = logging.getLogger("mcp_sqlserver")

_TOOL_EXEC_LOG_ENABLED = os.getenv("MCP_TOOL_EXECUTION_LOG_ENABLED", "true").lower() in {"1", "true", "yes", "on", "y"}
_SENSITIVE_LOG_KEYS = {"password", "token", "secret", "api_key", "prompt_context", "headers", "authorization"}

# Report storage for web UI (UUID -> HTML content)
_REPORT_STORAGE: dict[str, dict[str, Any]] = {}
_REPORT_STORAGE_LOCK = Lock()
_REPORT_STORAGE_DIR = pathlib.Path(os.getenv("MCP_REPORT_STORAGE_DIR", ".mcp_reports"))


def _sanitize_tool_log_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive fields from log context."""
    def _sanitize_value(value: Any) -> Any:
        if isinstance(value, dict):
            clean_dict: dict[str, Any] = {}
            for key, nested_value in value.items():
                key_text = str(key)
                if key_text.lower() in _SENSITIVE_LOG_KEYS:
                    clean_dict[key_text] = "[redacted]"
                else:
                    clean_dict[key_text] = _sanitize_value(nested_value)
            return clean_dict
        if isinstance(value, list):
            return [_sanitize_value(item) for item in value]
        return value

    return _sanitize_value(payload)


def _extract_result_meta(result: Any) -> dict[str, Any]:
    """Summarize result metadata without dumping full payload."""
    meta: dict[str, Any] = {"result_type": type(result).__name__}
    if isinstance(result, dict):
        meta["keys"] = sorted(list(result.keys()))[:20]
        if "status" in result:
            meta["status"] = result.get("status")
        if "count" in result and isinstance(result.get("count"), int):
            meta["count"] = result.get("count")
        if "items" in result and isinstance(result.get("items"), list):
            meta["items_count"] = len(result.get("items", []))
    elif isinstance(result, list):
        meta["count"] = len(result)
    return meta


def _log_tool_start(tool_name: str, function_name: str, invocation_id: str, context: dict[str, Any]) -> None:
    if not _TOOL_EXEC_LOG_ENABLED:
        return
    logger.info(
        "tool.start tool=%s function=%s invocation_id=%s context=%s",
        tool_name,
        function_name,
        invocation_id,
        json.dumps(_sanitize_tool_log_context(context), default=str),
    )


def _log_tool_success(tool_name: str, function_name: str, invocation_id: str, elapsed_ms: int, result: Any) -> None:
    if not _TOOL_EXEC_LOG_ENABLED:
        return
    logger.info(
        "tool.success tool=%s function=%s invocation_id=%s elapsed_ms=%s result=%s",
        tool_name,
        function_name,
        invocation_id,
        elapsed_ms,
        json.dumps(_extract_result_meta(result), default=str),
    )


def _log_tool_error(tool_name: str, function_name: str, invocation_id: str, elapsed_ms: int, exc: Exception) -> None:
    if not _TOOL_EXEC_LOG_ENABLED:
        return
    logger.exception(
        "tool.error tool=%s function=%s invocation_id=%s elapsed_ms=%s error=%s",
        tool_name,
        function_name,
        invocation_id,
        elapsed_ms,
        str(exc),
    )

# Minimal Settings class to satisfy code references
class Settings:
    def __init__(self, **kwargs):
        self.db_instances = kwargs.get('db_instances', {})
        self.db_pool_sizes = kwargs.get('db_pool_sizes', {})
        self.statement_timeout_ms = kwargs.get('statement_timeout_ms', 120000)
        self.max_rows = kwargs.get('max_rows', 500)
        self.allow_write = kwargs.get('allow_write', False)
        self.confirm_write = kwargs.get('confirm_write', False)
        self.transport = kwargs.get('transport', 'http')
        self.host = kwargs.get('host', '0.0.0.0')
        self.port = kwargs.get('port', 8000)
        self.auth_type = kwargs.get('auth_type', '')
        self.api_key = kwargs.get('api_key', '')
        self.allow_query_token_auth = kwargs.get('allow_query_token_auth', False)
        self.public_base_url = kwargs.get('public_base_url', '')
        self.ssl_cert = kwargs.get('ssl_cert', '')
        self.ssl_key = kwargs.get('ssl_key', '')
        self.ssl_strict = kwargs.get('ssl_strict', False)
        self.table_scope_enforced = kwargs.get('table_scope_enforced', False)
        self.allowed_tables = kwargs.get('allowed_tables', '')
        self.rate_limit_enabled = kwargs.get('rate_limit_enabled', True)
        self.rate_limit_window_seconds = kwargs.get('rate_limit_window_seconds', 60)
        self.rate_limit_max_requests = kwargs.get('rate_limit_max_requests', 240)
        self.rate_limit_breaker_seconds = kwargs.get('rate_limit_breaker_seconds', 60)
        self.rate_limit_breaker_violations = kwargs.get('rate_limit_breaker_violations', 3)
        self.audit_log_queries = kwargs.get('audit_log_queries', False)
        self.audit_log_file = kwargs.get('audit_log_file', 'mcp_query_audit.jsonl')
        self.audit_log_include_params = kwargs.get('audit_log_include_params', False)
        self.allow_raw_prompts = kwargs.get('allow_raw_prompts', False)
        self.tool_search_enabled = kwargs.get('tool_search_enabled', False)
        self.tool_search_strategy = kwargs.get('tool_search_strategy', 'regex')
        self.tool_search_max_results = kwargs.get('tool_search_max_results', None)
        self.tool_search_always_visible = kwargs.get('tool_search_always_visible', '')
        self.tool_search_tool_name = kwargs.get('tool_search_tool_name', 'search_tools')
        self.tool_call_tool_name = kwargs.get('tool_call_tool_name', 'call_tool')

# Minimal _now_utc_iso helper
def _now_utc_iso():
    return datetime.now(timezone.utc).isoformat()

def validate_instance(instance: int) -> None:
    if instance not in SETTINGS.db_instances:
        raise ValueError(f"Invalid instance: {instance}. Available: {list(SETTINGS.db_instances.keys())}")


 # --- Logging setup: honor MCP_LOG_LEVEL and support log rotation ---


# Ensure log directory exists if log file is specified
_log_file = os.getenv("MCP_LOG_FILE", "server.log")
if _log_file:
    log_path = pathlib.Path(_log_file)
    if log_path.parent and not log_path.parent.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)

_log_level = os.getenv("MCP_LOG_LEVEL", "INFO").upper()
_log_level_value = getattr(logging, _log_level, logging.INFO)
_log_rotate_enabled = os.getenv("MCP_LOG_ROTATE_ENABLED", "false").lower() in {"1", "true", "yes", "on", "y"}
_log_rotate_max_bytes = int(os.getenv("MCP_LOG_ROTATE_MAX_BYTES", "10485760"))  # 10MB default
_log_rotate_backup_count = int(os.getenv("MCP_LOG_ROTATE_BACKUP_COUNT", "5"))

if _log_file:
    if _log_rotate_enabled:
        handler = RotatingFileHandler(_log_file, maxBytes=_log_rotate_max_bytes, backupCount=_log_rotate_backup_count)
    else:
        handler = logging.FileHandler(_log_file)
    handler.setLevel(_log_level_value)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    logging.getLogger().handlers = [handler]
    logging.getLogger().setLevel(_log_level_value)
else:
    logging.basicConfig(level=_log_level_value)


# Audit log rotation (for query audit log)
_audit_log_file = os.getenv("MCP_AUDIT_LOG_FILE", "mcp_query_audit.jsonl")
_audit_log_rotate_enabled = os.getenv("MCP_AUDIT_LOG_ROTATE_ENABLED", "false").lower() in {"1", "true", "yes", "on", "y"}
_audit_log_rotate_max_bytes = int(os.getenv("MCP_AUDIT_LOG_ROTATE_MAX_BYTES", "10485760"))
_audit_log_rotate_backup_count = int(os.getenv("MCP_AUDIT_LOG_ROTATE_BACKUP_COUNT", "5"))

# Module-level audit log handler and lock
_AUDIT_LOG_HANDLER = None
_AUDIT_LOG_HANDLER_INIT_LOCK = Lock()

def _get_audit_handler():
    global _AUDIT_LOG_HANDLER
    if _AUDIT_LOG_HANDLER is not None:
        return _AUDIT_LOG_HANDLER
    with _AUDIT_LOG_HANDLER_INIT_LOCK:
        if _AUDIT_LOG_HANDLER is not None:
            return _AUDIT_LOG_HANDLER
        log_path = _audit_log_file
        log_dir = os.path.dirname(log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        if _audit_log_rotate_enabled:
            handler = RotatingFileHandler(
                log_path,
                maxBytes=_audit_log_rotate_max_bytes,
                backupCount=_audit_log_rotate_backup_count,
                encoding="utf-8"
            )
        else:
            handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(message)s"))
        _AUDIT_LOG_HANDLER = handler
        return handler


# --- Simple Connection Pool Implementation ---

_CONN_POOLS: dict[int, queue.Queue] = {}
_CONN_POOL_LOCKS: dict[int, Lock] = {}



def initialize_connection_pools():
    """Call this at server startup, not on import. Safe for tests."""
    for inst, cfg in SETTINGS.db_instances.items():
        pool_size = SETTINGS.db_pool_sizes.get(inst, 1)
        if pool_size > 1:
            _CONN_POOLS[inst] = queue.Queue(maxsize=pool_size)
            _CONN_POOL_LOCKS[inst] = Lock()
            # Pre-fill pool with live connections
            for _ in range(pool_size):
                try:
                    conn = pyodbc.connect(_connection_string(cfg["db_name"], inst), timeout=max(1, SETTINGS.statement_timeout_ms // 1000))
                    conn.autocommit = True
                    _CONN_POOLS[inst].put(conn)
                except Exception as e:
                    logger.warning(f"Failed to prefill connection pool for instance {inst}: {e}")

def get_instance_config(instance: int = 1) -> dict[str, str | int]:
    if instance not in SETTINGS.db_instances:
        raise RuntimeError(f"Database instance {instance} is not configured.")
    return SETTINGS.db_instances[instance]


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    return int(value)


def _env_optional_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        logger.warning("Invalid integer value for %s: %r", name, value)
        return None
    if parsed <= 0:
        return None
    return parsed


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}



def _load_settings() -> Settings:
    # Load up to 2 instances: DB_01_*, DB_02_*, fallback to DB_* for instance 1
    def load_instance(idx: int) -> dict[str, str | int]:
        prefix = f"DB_{idx:02d}_"
        def get(key: str, default=None):
            return os.getenv(prefix + key, default)

        # Fallback for instance 1: support legacy DB_*
        if idx == 1:
            def get(key: str, default=None):
                return os.getenv(prefix + key, os.getenv("DB_" + key, default))

        port_val = get("PORT") or get("SQL_PORT") or "1433"
        try:
            db_port = int(port_val)
            # Optional: validate port range
            if not (0 < db_port < 65536):
                db_port = 1433
        except (ValueError, TypeError):
            db_port = 1433
        return {
            "db_server": get("SERVER") or get("SQL_SERVER") or "",
            "db_port": db_port,
            "db_user": get("USER") or get("SQL_USER") or "",
            "db_password": get("PASSWORD") or get("SQL_PASSWORD") or "",
            "db_name": get("NAME") or get("SQL_DATABASE") or "master",
            "db_driver": get("DRIVER") or get("SQL_DRIVER") or "ODBC Driver 17 for SQL Server",
            "db_encrypt": get("ENCRYPT", "no") or "no",
            "db_trust_cert": get("TRUST_CERT", "yes") or "yes",
        }
    db_instances = {}
    db_pool_sizes = {}
    for idx in (1, 2):
        inst = load_instance(idx)
        if inst["db_server"] and inst["db_user"] and inst["db_password"]:
            db_instances[idx] = inst
            # Pool size: DB_01_POOL_SIZE, DB_02_POOL_SIZE, fallback default 10
            pool_env = f"DB_{idx:02d}_POOL_SIZE"
            try:
                pool_size = int(os.getenv(pool_env, "10"))
                if pool_size <= 0:
                    pool_size = 10
            except (TypeError, ValueError):
                pool_size = 10
            db_pool_sizes[idx] = pool_size
    return Settings(
        db_instances=db_instances,
        db_pool_sizes=db_pool_sizes,
        statement_timeout_ms=_env_int("MCP_STATEMENT_TIMEOUT_MS", 120000),
        max_rows=_env_int("MCP_MAX_ROWS", 500),
        allow_write=_env_bool("MCP_ALLOW_WRITE", False),
        confirm_write=_env_bool("MCP_CONFIRM_WRITE", False),
        transport=_env("MCP_TRANSPORT", "http").lower(),
        host=_env("MCP_HOST", "0.0.0.0"),
        port=_env_int("MCP_PORT", 8000),
        auth_type=_env("FASTMCP_AUTH_TYPE", "").lower(),
        api_key=_env("FASTMCP_API_KEY", ""),
        allow_query_token_auth=_env_bool("MCP_ALLOW_QUERY_TOKEN_AUTH", False),
        public_base_url=_env("MCP_PUBLIC_BASE_URL", "").strip(),
        ssl_cert=_env("MCP_SSL_CERT", "").strip(),
        ssl_key=_env("MCP_SSL_KEY", "").strip(),
        ssl_strict=_env_bool("MCP_SSL_STRICT", False),
        table_scope_enforced=_env_bool("MCP_TABLE_SCOPE_ENFORCED", False),
        allowed_tables=_env("MCP_ALLOWED_TABLES", "").strip(),
        rate_limit_enabled=_env_bool("MCP_RATE_LIMIT_ENABLED", True),
        rate_limit_window_seconds=_env_int("MCP_RATE_LIMIT_WINDOW_SECONDS", 60),
        rate_limit_max_requests=_env_int("MCP_RATE_LIMIT_MAX_REQUESTS", 240),
        rate_limit_breaker_seconds=_env_int("MCP_RATE_LIMIT_BREAKER_SECONDS", 60),
        rate_limit_breaker_violations=_env_int("MCP_RATE_LIMIT_BREAKER_VIOLATIONS", 3),
        audit_log_queries=_env_bool("MCP_AUDIT_LOG_QUERIES", False),
        audit_log_file=_env("MCP_AUDIT_LOG_FILE", "mcp_query_audit.jsonl").strip() or "mcp_query_audit.jsonl",
        audit_log_include_params=_env_bool("MCP_AUDIT_LOG_INCLUDE_PARAMS", False),
        allow_raw_prompts=_env_bool("MCP_ALLOW_RAW_PROMPTS", _env_bool("ALLOW_RAW_PROMPTS", False)),
        tool_search_enabled=_env_bool("MCP_TOOL_SEARCH_ENABLED", False),
        tool_search_strategy=_env("MCP_TOOL_SEARCH_STRATEGY", "regex").strip().lower(),
        tool_search_max_results=_env_optional_int("MCP_TOOL_SEARCH_MAX_RESULTS"),
        tool_search_always_visible=_env("MCP_TOOL_SEARCH_ALWAYS_VISIBLE", "").strip(),
        tool_search_tool_name=_env("MCP_TOOL_SEARCH_TOOL_NAME", "search_tools").strip(),
        tool_call_tool_name=_env("MCP_TOOL_CALL_TOOL_NAME", "call_tool").strip(),
    )


SETTINGS = _load_settings()

_PYODBC_CONNECT_LOCK = Lock() if sys.platform == "win32" else None
_AUDIT_LOG_LOCK = Lock()
_RATE_LIMIT_LOCK = Lock()
_DEFAULT_API_CALLER = "system:local"
_API_CALLER_CONTEXT: ContextVar[str] = ContextVar("api_caller", default=_DEFAULT_API_CALLER)
_RATE_LIMIT_REQUESTS: dict[str, list[float]] = {}
_RATE_LIMIT_VIOLATIONS: dict[str, int] = {}
_RATE_LIMIT_BLOCKED_UNTIL: dict[str, float] = {}
_RATE_LIMIT_CHECK_COUNTER = 0
_RATE_LIMIT_CLEANUP_EVERY_REQUESTS = 256
_SCOPE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _parse_allowed_table_patterns(raw_value: str) -> set[str]:
    patterns: set[str] = set()
    if not raw_value:
        return patterns

    for item in raw_value.split(","):
        pattern = item.strip().lower()
        if not pattern:
            continue
        if "." not in pattern:
            raise ValueError(f"Invalid table scope pattern: {item!r}. Use schema.table format.")
        schema_name, table_name = pattern.split(".", 1)
        schema_valid = schema_name == "*" or bool(_SCOPE_IDENTIFIER_RE.fullmatch(schema_name))
        table_valid = table_name == "*" or bool(_SCOPE_IDENTIFIER_RE.fullmatch(table_name))
        if not schema_valid or not table_valid:
            raise ValueError(f"Invalid table scope pattern: {item!r}. Use identifiers and optional '*' wildcard.")
        patterns.add(f"{schema_name}.{table_name}")

    return patterns


_TABLE_SCOPE_PATTERNS = _parse_allowed_table_patterns(SETTINGS.allowed_tables)


def _validate_runtime_guards() -> None:
    if SETTINGS.allow_write and not SETTINGS.confirm_write:
        raise RuntimeError("Write mode requires MCP_CONFIRM_WRITE=true.")
    if SETTINGS.allow_write and SETTINGS.transport in {"http", "sse"} and SETTINGS.auth_type in {"", "none"}:
        raise RuntimeError("Write mode over HTTP requires FASTMCP_AUTH_TYPE.")
    if SETTINGS.table_scope_enforced and not _TABLE_SCOPE_PATTERNS:
        raise RuntimeError("MCP_TABLE_SCOPE_ENFORCED=true requires MCP_ALLOWED_TABLES.")
    if SETTINGS.rate_limit_window_seconds <= 0:
        raise RuntimeError("MCP_RATE_LIMIT_WINDOW_SECONDS must be > 0.")
    if SETTINGS.rate_limit_max_requests <= 0:
        raise RuntimeError("MCP_RATE_LIMIT_MAX_REQUESTS must be > 0.")
    if SETTINGS.rate_limit_breaker_seconds <= 0:
        raise RuntimeError("MCP_RATE_LIMIT_BREAKER_SECONDS must be > 0.")
    if SETTINGS.rate_limit_breaker_violations <= 0:
        raise RuntimeError("MCP_RATE_LIMIT_BREAKER_VIOLATIONS must be > 0.")
    if SETTINGS.tool_search_enabled and SETTINGS.tool_search_strategy not in {"regex", "bm25"}:
        raise RuntimeError("MCP_TOOL_SEARCH_STRATEGY must be 'regex' or 'bm25'.")


_validate_runtime_guards()


def _is_table_allowed(schema_name: str, table_name: str) -> bool:
    if not SETTINGS.table_scope_enforced:
        return True

    schema_norm = (schema_name or "").strip().lower() or "dbo"
    table_norm = (table_name or "").strip().lower()
    if not table_norm:
        return False

    for pattern in _TABLE_SCOPE_PATTERNS:
        pattern_schema, pattern_table = pattern.split(".", 1)
        schema_ok = pattern_schema == "*" or pattern_schema == schema_norm
        table_ok = pattern_table == "*" or pattern_table == table_norm
        if schema_ok and table_ok:
            return True
    return False


def _enforce_table_scope_for_ident(schema_name: str, table_name: str) -> None:
    if SETTINGS.table_scope_enforced and not _is_table_allowed(schema_name, table_name):
        raise ValueError(f"Access denied by table scope policy for {schema_name}.{table_name}.")


def _strip_identifier_quotes(value: str) -> str:
    s = value.strip()
    if s.startswith("[") and s.endswith("]") and len(s) >= 2:
        s = s[1:-1]
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        s = s[1:-1]
    return s.strip().lower()


def _extract_referenced_tables(sql: str) -> list[tuple[str, str]]:
    cleaned = _strip_sql_comments_and_literals(sql)
    ident = r"(?:\[[^\]]+\]|[A-Za-z_][A-Za-z0-9_]*)"
    object_ref = rf"(?:{ident}\s*\.\s*{ident}|{ident})"
    cte_patterns = [
        # CTE declarations can include an optional column list before AS.
        re.compile(rf"\bwith\s+({ident})(?:\s*\([^\)]*\))?\s+as\s*\(", flags=re.I),
        re.compile(rf",\s*({ident})(?:\s*\([^\)]*\))?\s+as\s*\(", flags=re.I),
    ]

    cte_aliases: set[str] = set()
    for pattern in cte_patterns:
        for match in pattern.finditer(cleaned):
            cte_alias = _strip_identifier_quotes(match.group(1).strip())
            if cte_alias:
                cte_aliases.add(cte_alias)

    patterns = [
        re.compile(rf"\b(?:from|join)\s+({object_ref})", flags=re.I),
        re.compile(rf"\b(?:insert(?:\s+into)?|update|merge(?:\s+into)?)\s+({object_ref})", flags=re.I),
        # This matches only DELETE FROM <table>; alias forms (DELETE t FROM ...)
        # are resolved by the separate FROM/JOIN extraction pattern above.
        re.compile(rf"\bdelete\s+from\s+({object_ref})", flags=re.I),
    ]
    references: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for pattern in patterns:
        for match in pattern.finditer(cleaned):
            raw_target = match.group(1).strip()
            if raw_target.startswith("("):
                continue
            parts = [p.strip() for p in raw_target.split(".")]
            if len(parts) == 2:
                schema_name = _strip_identifier_quotes(parts[0])
                table_name = _strip_identifier_quotes(parts[1])
            else:
                schema_name = "dbo"
                table_name = _strip_identifier_quotes(parts[0])

            # Ignore CTE aliases when they appear as FROM/JOIN targets.
            if len(parts) == 1 and table_name in cte_aliases:
                continue

            if table_name:
                entry = (schema_name, table_name)
                if entry not in seen:
                    seen.add(entry)
                    references.append(entry)
    return references


def _enforce_table_scope_for_sql(sql: str) -> None:
    if not SETTINGS.table_scope_enforced:
        return
    for schema_name, table_name in _extract_referenced_tables(sql):
        _enforce_table_scope_for_ident(schema_name, table_name)


def _parse_schema_qualified_name(object_name: str, default_schema: str = "dbo") -> tuple[str, str]:
    raw = (object_name or "").strip()
    if not raw:
        raise ValueError("object_name is required")

    match = re.fullmatch(
        r"\s*(?:\[(?P<schema_br>[^\]]+)\]|(?P<schema_plain>[^.\[\]]+))\s*\.\s*(?:\[(?P<table_br>[^\]]+)\]|(?P<table_plain>[^.\[\]]+))\s*",
        raw,
    )
    if match:
        schema_name = (match.group("schema_br") or match.group("schema_plain") or "").strip()
        table_name = (match.group("table_br") or match.group("table_plain") or "").strip()
        if not schema_name or not table_name:
            raise ValueError(f"Invalid object_name: {object_name!r}")
        return schema_name, table_name

    table_name = raw
    if table_name.startswith("[") and table_name.endswith("]") and len(table_name) >= 2:
        table_name = table_name[1:-1].strip()
    if not table_name:
        raise ValueError(f"Invalid object_name: {object_name!r}")
    return default_schema, table_name


def _current_api_caller() -> str:
    caller = (_API_CALLER_CONTEXT.get() or "").strip()
    if not caller or caller.lower() == "unknown":
        return _DEFAULT_API_CALLER
    return caller


def _extract_jwt_subject(token: str) -> str | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload_part = parts[1]
    padding = "=" * ((4 - len(payload_part) % 4) % 4)
    try:
        payload_bytes = base64.urlsafe_b64decode((payload_part + padding).encode("ascii"))
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        return None
    return subject.strip()


def _write_query_audit_record(
    tool_name: str,
    database_name: str,
    sql: str,
    params_json: str | None = None,
    prompt_context: str | None = None,
) -> None:
    if not SETTINGS.audit_log_queries:
        return

    prompt_sha256: str | None = None
    prompt_redaction_token: str | None = None
    if prompt_context:
        prompt_redaction_token, prompt_sha256 = sanitize_prompt(prompt_context)

    sql_sha256 = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    prompt_storage_mode = "raw_opt_in" if SETTINGS.allow_raw_prompts else "hashed_redacted"
    redacted_sql = f"[REDACTED_SQL:{sql_sha256[:12]}]"

    payload: dict[str, Any] = {
        "timestamp": _now_utc_iso(),
        "event": "query_execution",
        "tool": tool_name,
        "database": database_name,
        "api_caller": _current_api_caller(),
        "redacted_sql": redacted_sql,
        "sql_sha256": sql_sha256,
        "sql_anonymized_hash": f"sha256:{sql_sha256}",
        "prompt_sha256": prompt_sha256,
        "prompt_redaction_token": prompt_redaction_token,
        "prompt_storage_mode": prompt_storage_mode,
        # Use db_user from instance 1 config if available
        "db_user": get_instance_config(1).get("db_user", "") if 1 in SETTINGS.db_instances else "",
    }
    if SETTINGS.allow_raw_prompts and prompt_context:
        payload["prompt"] = prompt_context
        payload["raw_prompt_storage_enabled"] = True
    if SETTINGS.audit_log_include_params:
        payload["params_json"] = params_json


    line = json.dumps(payload, ensure_ascii=False, default=str)
    handler = _get_audit_handler()
    record = logging.LogRecord(
        name="mcp_sqlserver.audit",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=line,
        args=(),
        exc_info=None
    )
    with _AUDIT_LOG_LOCK:
        handler.emit(record)


def sanitize_prompt(prompt_context: str) -> tuple[str, str]:
    prompt_sha256 = hashlib.sha256(prompt_context.encode("utf-8")).hexdigest()
    return f"[REDACTED_PROMPT:{prompt_sha256[:12]}]", prompt_sha256


def _rate_limit_cleanup(now: float | None = None) -> int:
    current = now if now is not None else time.monotonic()
    stale_threshold = current - (SETTINGS.rate_limit_window_seconds + SETTINGS.rate_limit_breaker_seconds)

    with _RATE_LIMIT_LOCK:
        stale_keys: list[str] = []
        for key, timestamps in _RATE_LIMIT_REQUESTS.items():
            if not timestamps:
                stale_keys.append(key)
                continue
            if max(timestamps) < stale_threshold:
                stale_keys.append(key)

        for key in stale_keys:
            _RATE_LIMIT_REQUESTS.pop(key, None)
            _RATE_LIMIT_VIOLATIONS.pop(key, None)
            _RATE_LIMIT_BLOCKED_UNTIL.pop(key, None)

    return len(stale_keys)


def _rate_limit_check(client_key: str) -> tuple[bool, int | None]:
    if not SETTINGS.rate_limit_enabled:
        return True, None

    global _RATE_LIMIT_CHECK_COUNTER
    now = time.monotonic()

    run_cleanup = False
    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_CHECK_COUNTER += 1
        if _RATE_LIMIT_CHECK_COUNTER >= _RATE_LIMIT_CLEANUP_EVERY_REQUESTS:
            _RATE_LIMIT_CHECK_COUNTER = 0
            run_cleanup = True

    if run_cleanup:
        _rate_limit_cleanup(now)

    with _RATE_LIMIT_LOCK:
        blocked_until = _RATE_LIMIT_BLOCKED_UNTIL.get(client_key, 0.0)
        if blocked_until > now:
            retry_after = max(1, int(blocked_until - now))
            return False, retry_after

        request_times = _RATE_LIMIT_REQUESTS.get(client_key, [])
        window_start = now - SETTINGS.rate_limit_window_seconds
        request_times = [t for t in request_times if t >= window_start]

        if len(request_times) >= SETTINGS.rate_limit_max_requests:
            violations = _RATE_LIMIT_VIOLATIONS.get(client_key, 0) + 1
            _RATE_LIMIT_VIOLATIONS[client_key] = violations
            if violations >= SETTINGS.rate_limit_breaker_violations:
                _RATE_LIMIT_BLOCKED_UNTIL[client_key] = now + SETTINGS.rate_limit_breaker_seconds
                _RATE_LIMIT_REQUESTS[client_key] = request_times
                return False, SETTINGS.rate_limit_breaker_seconds

            retry_after = SETTINGS.rate_limit_window_seconds
            if request_times:
                oldest_request_time = request_times[0]
                retry_after = max(
                    1,
                    int((oldest_request_time + SETTINGS.rate_limit_window_seconds) - now),
                )
            _RATE_LIMIT_REQUESTS[client_key] = request_times
            return False, retry_after

        request_times.append(now)
        _RATE_LIMIT_REQUESTS[client_key] = request_times
        if _RATE_LIMIT_VIOLATIONS.get(client_key, 0) > 0 and len(request_times) < SETTINGS.rate_limit_max_requests // 2:
            _RATE_LIMIT_VIOLATIONS[client_key] = max(0, _RATE_LIMIT_VIOLATIONS.get(client_key, 0) - 1)
        return True, None



def _connection_string(database: str | None = None, instance: int = 1) -> str:
    validate_instance(instance)
    inst = SETTINGS.db_instances.get(instance)
    if not inst:
        raise RuntimeError(f"No database instance configured for instance={instance}. Valid options: 1 (SETTINGS.db_01), 2 (SETTINGS.db_02)")
    db_name = database or inst["db_name"]
    return (
        f"DRIVER={{{inst['db_driver']}}};"
        f"SERVER={inst['db_server']},{inst['db_port']};"
        f"DATABASE={db_name};"
        f"UID={inst['db_user']};"
        f"PWD={inst['db_password']};"
        f"Encrypt={inst['db_encrypt']};"
        f"TrustServerCertificate={inst['db_trust_cert']};"
        f"MARS_Connection=Yes;"
    )


def _quote_sql_ident(identifier: str) -> str:
    return f"[{identifier.replace(']', ']]')}]"


def _ensure_connection_database_scope(conn: pyodbc.Connection, database: str | None, instance: int) -> None:
    """Force connection context to the requested (or default) database."""
    inst = SETTINGS.db_instances.get(instance)
    if not inst:
        raise RuntimeError(f"No database instance configured for instance={instance}.")
    target_db = str(database or inst["db_name"])
    cur = conn.cursor()
    try:
        cur.execute(f"USE {_quote_sql_ident(target_db)}")
    finally:
        cur.close()

def get_connection(database: str | None = None, instance: int = 1) -> Union[pyodbc.Connection, 'PooledConnection']:
    validate_instance(instance)
    pool = _CONN_POOLS.get(instance)
    pool_lock = _CONN_POOL_LOCKS.get(instance)
    if pool and pool_lock:
        # Try to get a pooled connection, else create new if pool is empty
        try:
            conn = pool.get(timeout=5)
            # Validate connection is alive
            try:
                cur = conn.cursor()
                try:
                    cur.execute("SELECT 1")
                finally:
                    cur.close()
            except Exception:
                # Connection is dead, replace
                conn.close()
                conn = pyodbc.connect(_connection_string(database, instance), timeout=max(1, SETTINGS.statement_timeout_ms // 1000))
                conn.autocommit = True
        except queue.Empty:
            # Pool exhausted, create new connection (not pooled)
            conn = pyodbc.connect(_connection_string(database, instance), timeout=max(1, SETTINGS.statement_timeout_ms // 1000))
            conn.autocommit = True

        # Reset scope on every checkout since pool keys are per-instance (not per-database).
        # If a pooled connection is left in a bad state (e.g., busy with previous results),
        # replace it and retry scope reset once.
        try:
            _ensure_connection_database_scope(conn, database, instance)
        except Exception as exc:
            logger.warning(f"Discarding pooled connection after scope reset failure: {exc}")
            try:
                conn.close()
            except Exception:
                pass
            conn = pyodbc.connect(_connection_string(database, instance), timeout=max(1, SETTINGS.statement_timeout_ms // 1000))
            conn.autocommit = True
            try:
                _ensure_connection_database_scope(conn, database, instance)
            except Exception as retry_exc:
                logger.warning(f"Failed scope reset on replacement pooled connection: {retry_exc}")
                try:
                    conn.close()
                except Exception:
                    pass
                raise

        # Return a wrapped connection with pooled close
        return PooledConnection(conn, pool)
    else:
        # No pool, fallback to direct connect
        if _PYODBC_CONNECT_LOCK is not None:
            with _PYODBC_CONNECT_LOCK:
                conn = pyodbc.connect(_connection_string(database, instance), timeout=max(1, SETTINGS.statement_timeout_ms // 1000))
        else:
            conn = pyodbc.connect(_connection_string(database, instance), timeout=max(1, SETTINGS.statement_timeout_ms // 1000))
        conn.autocommit = True
        _ensure_connection_database_scope(conn, database, instance)
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


DEFAULT_TOOL_PAGE_SIZE = 10
MAX_TOOL_PAGE_SIZE = 200


def _normalize_tool_pagination(page: int = 1, page_size: int = DEFAULT_TOOL_PAGE_SIZE) -> tuple[int, int]:
    safe_page = page if isinstance(page, int) and page > 0 else 1
    safe_page_size = page_size if isinstance(page_size, int) and page_size > 0 else DEFAULT_TOOL_PAGE_SIZE
    safe_page_size = min(MAX_TOOL_PAGE_SIZE, safe_page_size)
    return safe_page, safe_page_size


def _paginate_sequence(items: Sequence[Any], page: int, page_size: int) -> tuple[list[Any], dict[str, int]]:
    total_items = len(items)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    safe_page = min(page, total_pages)
    start = (safe_page - 1) * page_size
    paged_items = list(items[start:start + page_size])
    return paged_items, {
        "page": safe_page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
    }


def _paginate_lists_in_object(value: Any, page: int, page_size: int, path: str) -> tuple[Any, dict[str, dict[str, int]]]:
    if isinstance(value, list):
        paged_items, pagination = _paginate_sequence(value, page, page_size)
        return paged_items, {path: pagination}

    if isinstance(value, dict):
        transformed: dict[str, Any] = {}
        list_pagination: dict[str, dict[str, int]] = {}
        for key, item in value.items():
            transformed_item, item_pagination = _paginate_lists_in_object(item, page, page_size, f"{path}.{key}")
            transformed[key] = transformed_item
            list_pagination.update(item_pagination)
        return transformed, list_pagination
    
    return value, {}


def _paginate_tool_result(result: Any, page: int = 1, page_size: int = DEFAULT_TOOL_PAGE_SIZE) -> Any:
    safe_page, safe_page_size = _normalize_tool_pagination(page, page_size)

    if isinstance(result, list):
        paged_items, pagination = _paginate_sequence(result, safe_page, safe_page_size)
        return {
            "items": paged_items,
            "pagination": pagination,
        }

    if isinstance(result, dict):
        transformed, list_pagination = _paginate_lists_in_object(result, safe_page, safe_page_size, "root")
        if list_pagination:
            transformed["_pagination"] = {
                "page": safe_page,
                "page_size": safe_page_size,
                "lists": list_pagination,
            }
        return transformed

    return result


def _estimate_tokens(value: Any) -> int:
    try:
        payload = json.dumps(value, default=str, ensure_ascii=False)
    except Exception:
        payload = str(value)
    return max(1, len(payload) // 4)


def _shrink_lists(value: Any, max_items: int) -> Any:
    if isinstance(value, list):
        return [_shrink_lists(item, max_items) for item in value[:max_items]]
    if isinstance(value, dict):
        return {key: _shrink_lists(item, max_items) for key, item in value.items()}
    return value


def _apply_token_budget(result: Any, token_budget: int | None) -> Any:
    if token_budget is None or token_budget <= 0:
        return result

    estimated = _estimate_tokens(result)
    if estimated <= token_budget:
        return result

    for max_items in (50, 25, 10, 5, 3, 1):
        candidate = _shrink_lists(result, max_items)
        estimated_candidate = _estimate_tokens(candidate)
        if estimated_candidate <= token_budget:
            if isinstance(candidate, dict):
                candidate["_truncation"] = {
                    "applied": True,
                    "token_budget": token_budget,
                    "estimated_tokens": estimated_candidate,
                    "list_max_items": max_items,
                }
            return candidate

    fallback = {
        "summary": "Result exceeds token budget and was compacted to minimal payload.",
        "_truncation": {
            "applied": True,
            "token_budget": token_budget,
            "estimated_tokens": _estimate_tokens(result),
            "list_max_items": 0,
        },
    }
    if isinstance(result, dict):
        for key in ("database", "schema", "table_info"):
            if key in result:
                fallback[key] = result.get(key)
        if "summary" in result and isinstance(result.get("summary"), dict):
            fallback["original_summary"] = result.get("summary")
    return fallback


def _build_projection_tree(paths: list[list[str]]) -> dict[str, Any]:
    tree: dict[str, Any] = {}
    for parts in paths:
        node = tree
        for part in parts:
            node = node.setdefault(part, {})
        node["__leaf__"] = True
    return tree


def _project_with_tree(value: Any, tree: dict[str, Any]) -> Any:
    if not tree or tree.get("__leaf__"):
        return value

    if isinstance(value, dict):
        projected: dict[str, Any] = {}
        for key, subtree in tree.items():
            if key == "__leaf__":
                continue
            if key not in value:
                continue
            child = _project_with_tree(value.get(key), subtree)
            if child is not None:
                projected[key] = child
        return projected or None

    if isinstance(value, list):
        items: list[Any] = []
        for item in value:
            child = _project_with_tree(item, tree)
            if child is not None:
                items.append(child)
        return items or None

    return None


def _apply_field_projection(result: Any, fields: str | None) -> Any:
    if not fields or not isinstance(result, dict):
        return result

    parsed_fields = [item.strip() for item in fields.split(",") if item.strip()]
    if not parsed_fields:
        return result

    path_parts = [[segment for segment in path.split(".") if segment] for path in parsed_fields]
    path_parts = [parts for parts in path_parts if parts]
    if not path_parts:
        return result

    projection_tree = _build_projection_tree(path_parts)
    projected = _project_with_tree(result, projection_tree)
    if not isinstance(projected, dict):
        return result

    for metadata_key in ("pagination", "_pagination", "_truncation"):
        if metadata_key in result and metadata_key not in projected:
            projected[metadata_key] = result[metadata_key]

    return projected or result


def _slice_query_text(value: Any, max_chars: int = 240) -> Any:
    if not isinstance(value, str):
        return value
    compact = " ".join(value.split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[:max_chars]}…"


def _apply_top_queries_view(result: dict[str, Any], view: str) -> dict[str, Any]:
    if view == "full":
        return result

    compact_keys = ["long_running_queries", "high_cpu_queries", "high_io_queries", "high_execution_queries"]
    if view == "summary":
        return {
            "database": result.get("database"),
            "query_store_enabled": result.get("query_store_enabled"),
            "query_store_config": result.get("query_store_config"),
            "summary": result.get("summary", {}),
            "recommendations": result.get("recommendations", []),
        }

    transformed = dict(result)
    for key in compact_keys:
        queries = transformed.get(key)
        if isinstance(queries, list):
            transformed[key] = [
                {
                    **query,
                    "query_sql_text": _slice_query_text(query.get("query_sql_text"), 240),
                }
                for query in queries
            ]
    return transformed


def _apply_table_health_view(result: dict[str, Any], view: str) -> dict[str, Any]:
    if view == "full":
        return result

    indexes = result.get("indexes", [])
    foreign_keys = result.get("foreign_keys", [])
    statistics_sample = result.get("statistics_sample", [])
    health_analysis = result.get("health_analysis", {})
    recommendations = result.get("recommendations", [])

    if view == "summary":
        return {
            "table_info": result.get("table_info", {}),
            "health_summary": {
                "indexes_count": len(indexes) if isinstance(indexes, list) else 0,
                "foreign_keys_count": len(foreign_keys) if isinstance(foreign_keys, list) else 0,
                "statistics_count": len(statistics_sample) if isinstance(statistics_sample, list) else 0,
                "constraint_issues_count": len(health_analysis.get("constraint_issues", [])) if isinstance(health_analysis, dict) else 0,
                "recommendations_count": len(recommendations) if isinstance(recommendations, list) else 0,
            },
            "recommendations": recommendations,
        }

    transformed = dict(result)
    if isinstance(indexes, list):
        transformed["indexes"] = indexes[:10]
    if isinstance(statistics_sample, list):
        transformed["statistics_sample"] = statistics_sample[:10]
    return transformed


def _apply_logical_model_view(result: dict[str, Any], view: str) -> dict[str, Any]:
    if view == "full":
        return result

    summary = result.get("summary", {})
    logical_model = result.get("logical_model", {}) if isinstance(result.get("logical_model"), dict) else {}
    recommendations = result.get("recommendations", {}) if isinstance(result.get("recommendations"), dict) else {}
    issues = result.get("issues", {}) if isinstance(result.get("issues"), dict) else {}

    if view == "summary":
        return {
            "summary": summary,
            "sample_relationships": logical_model.get("relationships", [])[:10] if isinstance(logical_model.get("relationships"), list) else [],
            "recommendations": {
                "entities": recommendations.get("entities", [])[:5],
                "attributes": recommendations.get("attributes", [])[:5],
                "relationships": recommendations.get("relationships", [])[:5],
                "identifiers": recommendations.get("identifiers", [])[:5],
                "normalization": recommendations.get("normalization", [])[:5],
            },
        }

    transformed = dict(result)
    model_copy = dict(logical_model)
    if isinstance(model_copy.get("entities"), list):
        trimmed_entities: list[dict[str, Any]] = []
        for entity in model_copy["entities"]:
            if not isinstance(entity, dict):
                continue
            entity_copy = dict(entity)
            attrs = entity_copy.get("attributes")
            if isinstance(attrs, list):
                entity_copy["attributes"] = attrs[:12]
            trimmed_entities.append(entity_copy)
        model_copy["entities"] = trimmed_entities
    transformed["logical_model"] = model_copy

    issues_copy = dict(issues)
    for key in ("entities", "attributes", "relationships", "identifiers", "normalization"):
        values = issues_copy.get(key)
        if isinstance(values, list):
            issues_copy[key] = values[:12]
    transformed["issues"] = issues_copy
    return transformed


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


def _public_base_url() -> str:
    if SETTINGS.public_base_url:
        return SETTINGS.public_base_url.rstrip("/")

    host = SETTINGS.host.strip() or "localhost"
    if host in {"0.0.0.0", "::", "127.0.0.1"}:
        host = "localhost"
    return f"http://{host}:{SETTINGS.port}"


def _report_file_path(report_id: str) -> pathlib.Path:
    return _REPORT_STORAGE_DIR / f"{report_id}.html"


def _persist_report_html(report_id: str, html: str) -> None:
    try:
        _REPORT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        _report_file_path(report_id).write_text(html, encoding="utf-8")
    except OSError as exc:
        raise IOError(f"Failed to persist report '{report_id}'") from exc


def _load_report_html(report_id: str) -> str | None:
    report_path = _report_file_path(report_id)
    if not report_path.exists():
        return None
    return report_path.read_text(encoding="utf-8")


def _get_report_html(report_id: str) -> str | None:
    with _REPORT_STORAGE_LOCK:
        report = _REPORT_STORAGE.get(report_id)
    html = report.get("html") if report else None
    if html is None:
        html = _load_report_html(report_id)
    return html



# FastMCP app initialization
MCP_SERVER_NAME = os.getenv("MCP_SERVER_NAME", "SQL Server MCP Server")
mcp = FastMCP(name=MCP_SERVER_NAME)

# Add Generative UI provider for dynamic dashboard generation
if GENERATIVE_UI_AVAILABLE and GenerativeUI is not None:
    try:
        mcp.add_provider(GenerativeUI())  # type: ignore
        logger.info("GenerativeUI provider registered for dynamic dashboard generation")
    except Exception as e:
        logger.warning(f"Failed to add GenerativeUI provider: {e}")

print(f"\n=== MCP Server Banner ===\n{MCP_SERVER_NAME} | FastMCP version: {fastmcp.__version__}\n========================\n")


def _configure_tool_search_transform() -> None:
    if not SETTINGS.tool_search_enabled:
        return

    strategy = SETTINGS.tool_search_strategy
    kwargs: dict[str, Any] = {}
    if SETTINGS.tool_search_max_results is not None:
        kwargs["max_results"] = SETTINGS.tool_search_max_results

    always_visible = [name.strip() for name in SETTINGS.tool_search_always_visible.split(",") if name.strip()]
    if always_visible:
        kwargs["always_visible"] = always_visible

    if SETTINGS.tool_search_tool_name:
        kwargs["search_tool_name"] = SETTINGS.tool_search_tool_name
    if SETTINGS.tool_call_tool_name:
        kwargs["call_tool_name"] = SETTINGS.tool_call_tool_name

    try:
        if strategy == "bm25":
            pass
        else:
            pass
    except Exception as exc:
        logger.warning(
            "Tool search transform requested but unavailable in current FastMCP runtime: %s",
            exc,
        )
        return

def _resolve_http_app() -> Any | None:
    return None

# --- db_sql2019_ping must be defined before registration ---

# Place after get_instance_config
def db_sql2019_ping(instance: int = 1) -> dict[str, Any]:
    # Basic connectivity probe.
    conn = get_connection(instance=instance)
    try:
        cur = conn.cursor()
        _execute_safe(cur, "SELECT 1 AS ok")
        row = cur.fetchone()
        inst_cfg = get_instance_config(instance)
        return {
            "status": "ok",
            "database": inst_cfg.get("db_name"),
            "server": inst_cfg.get("db_server"),
            "result": int(row[0]) if row else 1,
            "timestamp": _now_utc_iso(),
        }
    finally:
        conn.close()


def db_sql2019_list_databases(instance: int = 1, page: int = 1, page_size: int = DEFAULT_TOOL_PAGE_SIZE) -> dict[str, Any]:
    """List online databases visible to the current login."""
    validate_instance(instance)
    conn = get_connection("master", instance=instance)
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
        items = [row[0] for row in cur.fetchall()]
        return _paginate_tool_result(items, page=page, page_size=page_size)
    finally:
        conn.close()


def db_sql2019_list_tables(
    instance: int = 1,
    database_name: str | None = None,
    schema_name: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """List tables for a database/schema."""
    validate_instance(instance)
    db_name = database_name or get_instance_config(instance)["db_name"]
    db_name_str = _normalize_db_name(db_name)
    conn = get_connection(db_name_str, instance=instance)
    try:
        cur = conn.cursor()
        if database_name:
            _execute_safe(cur, f"USE [{database_name}]")
        if schema_name:
            _execute_safe(
                cur,
                """
                SELECT t.TABLE_SCHEMA, t.TABLE_NAME, p.create_date, p.modify_date
                FROM INFORMATION_SCHEMA.TABLES t
                JOIN sys.tables p ON t.TABLE_NAME = p.name AND t.TABLE_SCHEMA = SCHEMA_NAME(p.schema_id)
                WHERE t.TABLE_TYPE = 'BASE TABLE' AND t.TABLE_SCHEMA = ?
                ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME
                """,
                [schema_name],
            )
        else:
            _execute_safe(
                cur,
                """
                SELECT t.TABLE_SCHEMA, t.TABLE_NAME, p.create_date, p.modify_date
                FROM INFORMATION_SCHEMA.TABLES t
                JOIN sys.tables p ON t.TABLE_NAME = p.name AND t.TABLE_SCHEMA = SCHEMA_NAME(p.schema_id)
                WHERE t.TABLE_TYPE = 'BASE TABLE'
                ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME
                """,
            )
        rows = cur.fetchall()
        items = [
            {
                "schema_name": row[0],
                "table_name": row[1],
                "create_date": row[2].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if row[2] else None,
                "modify_date": row[3].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if row[3] else None,
            }
            for row in rows
            if _is_table_allowed(str(row[0] or "dbo"), str(row[1] or ""))
        ]
        return _paginate_tool_result(items, page=page, page_size=page_size)
    finally:
        conn.close()


def db_sql2019_get_schema(
    instance: int = 1,
    database_name: str | None = None,
    table_name: str | None = None,
    schema_name: str = "dbo",
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Get column metadata for a table."""
    if not table_name:
        raise ValueError("table_name is required")
    validate_instance(instance)
    _enforce_table_scope_for_ident(schema_name, table_name)
    db_name = database_name or get_instance_config(instance)["db_name"]
    db_name_str = _normalize_db_name(db_name)
    conn = get_connection(db_name_str, instance=instance)
    try:
        cur = conn.cursor()
        if database_name:
            _execute_safe(cur, f"USE [{database_name}]")
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
        result = {
            "database": db_name,
            "schema": schema_name,
            "table": table_name,
            "columns": columns,
        }
        return _paginate_tool_result(result, page=page, page_size=page_size)
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
    instance: int,
    database_name: str | None,
    sql: str,
    params_json: str | None = None,
    max_rows: int | None = None,
    enforce_readonly: bool = True,
    tool_name: str = "db_sql2019_run_query",
    prompt_context: str | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    validate_instance(instance)
    if enforce_readonly and not SETTINGS.allow_write:
        _require_readonly(sql)
    _enforce_table_scope_for_sql(sql)
    
    db_name = database_name or get_instance_config(instance)["db_name"]

    db_name_str = _normalize_db_name(db_name)
    # Ensure database_name is str for audit record (never None)
    audit_db_name = db_name_str if db_name_str is not None else ""
    _write_query_audit_record(
        tool_name=tool_name,
        database_name=audit_db_name,
        sql=sql,
        params_json=params_json,
        prompt_context=prompt_context,
    )

    params = _parse_params_json(params_json)
    row_cap = max_rows if isinstance(max_rows, int) and max_rows > 0 else SETTINGS.max_rows

    conn = get_connection(db_name_str, instance=instance)
    try:
        cur = conn.cursor()
        _execute_safe(cur, sql, params)
        try:
            rows = _fetch_limited(cur, row_cap)
            return _rows_to_dicts(cur, rows)
        except pyodbc.ProgrammingError:
            # For DDL (CREATE/ALTER/DROP), fetching results raises ProgrammingError: No results. Previous SQL was not a query.
            if tool_name in {"db_sql2019_create_object", "db_sql2019_alter_object", "db_sql2019_drop_object"}:
                return {"status": "success", "message": "DDL executed successfully."}
            raise
    finally:
        conn.close()


def db_sql2019_execute_query(
    instance: int = 1,
    database_name: str | None = None,
    sql: str | None = None,
    params_json: str | None = None,
    max_rows: int | None = None,
    prompt_context: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Legacy-compatible query executor (read-only unless write mode is enabled)."""
    if not sql:
        raise ValueError("sql is required")
    rows = _run_query_internal(
        instance=instance,
        database_name=database_name,
        sql=sql,
        params_json=params_json,
        max_rows=max_rows,
        enforce_readonly=True,
        tool_name="db_sql2019_execute_query",
        prompt_context=prompt_context,
    )
    return _paginate_tool_result(rows, page=page, page_size=page_size)


def db_sql2019_run_query(
    instance: int = 1,
    arg1: str | None = None,
    arg2: str | None = None,
    params_json: str | None = None,
    max_rows: int | None = None,
    prompt_context: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Execute SQL; supports both legacy (db, sql) and new (sql only) signatures."""
    if arg1 is None:
         raise ValueError("At least one argument (sql) is required")
         
    if arg2 is None:
        database_name = None
        sql = arg1
    else:
        database_name = arg1
        sql = arg2

    rows = _run_query_internal(
        instance=instance,
        database_name=database_name,
        sql=sql,
        params_json=params_json,
        max_rows=max_rows,
        enforce_readonly=True,
        tool_name="db_sql2019_run_query",
        prompt_context=prompt_context,
    )
    return _paginate_tool_result(rows, page=page, page_size=page_size)


def db_sql2019_list_objects(
    instance: int = 1,
    database_name: str | None = None,
    object_type: str = "TABLE",
    object_name: str | None = None,
    schema: str | None = None,
    order_by: str | None = None,
    limit: int = 50,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Unified object listing for database/schema/table/view/index/function/procedure/trigger."""
    validate_instance(instance)
    db_name = database_name or get_instance_config(instance)["db_name"]
    db_name_str = _normalize_db_name(db_name)
    conn = get_connection(db_name_str, instance=instance)
    try:
        cur = conn.cursor()
        object_type_norm = object_type.strip().upper()
        requested_page, requested_page_size = _normalize_tool_pagination(page, page_size)
        max_items = max(1, limit)

        def _build_table_scope_sql(schema_col: str, table_col: str) -> tuple[str, list[Any]]:
            if not SETTINGS.table_scope_enforced:
                return "", []

            if not _TABLE_SCOPE_PATTERNS:
                return " AND 1 = 0", []

            clauses: list[str] = []
            params_local: list[Any] = []
            for pattern in _TABLE_SCOPE_PATTERNS:
                pattern_schema, pattern_table = pattern.split(".", 1)
                if pattern_schema == "*" and pattern_table == "*":
                    return "", []
                if pattern_schema == "*":
                    clauses.append(f"LOWER({table_col}) = ?")
                    params_local.append(pattern_table)
                elif pattern_table == "*":
                    clauses.append(f"LOWER({schema_col}) = ?")
                    params_local.append(pattern_schema)
                else:
                    clauses.append(f"(LOWER({schema_col}) = ? AND LOWER({table_col}) = ?)")
                    params_local.extend([pattern_schema, pattern_table])

            if not clauses:
                return " AND 1 = 0", []
            return " AND (" + " OR ".join(clauses) + ")", params_local

        def _paginate_query(
            count_sql: str,
            count_params: list[Any],
            data_sql: str,
            data_params: list[Any],
            row_mapper,
        ) -> dict[str, Any]:
            _execute_safe(cur, count_sql, count_params)
            count_row = cur.fetchone()
            total_count = int(count_row[0]) if count_row and count_row[0] is not None else 0
            capped_total = min(total_count, max_items)
            total_pages = max(1, (capped_total + requested_page_size - 1) // requested_page_size)
            safe_page = min(requested_page, total_pages)
            offset = (safe_page - 1) * requested_page_size

            if capped_total == 0 or offset >= capped_total:
                return {
                    "items": [],
                    "pagination": {
                        "page": safe_page,
                        "page_size": requested_page_size,
                        "total_items": capped_total,
                        "total_pages": total_pages,
                    },
                }

            fetch_size = min(requested_page_size, capped_total - offset)
            paged_sql = data_sql + " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
            _execute_safe(cur, paged_sql, data_params + [offset, fetch_size])
            rows = cur.fetchall()
            return {
                "items": row_mapper(rows),
                "pagination": {
                    "page": safe_page,
                    "page_size": requested_page_size,
                    "total_items": capped_total,
                    "total_pages": total_pages,
                },
            }

        if object_type_norm in {"DATABASE", "DATABASES"}:
            count_sql = """
                SELECT COUNT(*)
                FROM sys.databases
                WHERE state_desc = 'ONLINE'
            """
            data_sql = """
                SELECT name
                FROM sys.databases
                WHERE state_desc = 'ONLINE'
                ORDER BY name
            """
            return _paginate_query(
                count_sql=count_sql,
                count_params=[],
                data_sql=data_sql,
                data_params=[],
                row_mapper=lambda rows: [row[0] for row in rows],
            )

        if object_type_norm in {"SCHEMA", "SCHEMAS"}:
            count_sql = "SELECT COUNT(*) FROM sys.schemas"
            data_sql = "SELECT name FROM sys.schemas ORDER BY name"
            return _paginate_query(
                count_sql=count_sql,
                count_params=[],
                data_sql=data_sql,
                data_params=[],
                row_mapper=lambda rows: [row[0] for row in rows],
            )

        if object_type_norm == "TABLE":
            join_clause = "JOIN sys.tables p ON t.TABLE_NAME = p.name AND t.TABLE_SCHEMA = SCHEMA_NAME(p.schema_id)"
            where_sql = "WHERE t.TABLE_TYPE = ?"
            params: list[Any] = ["BASE TABLE"]
            if schema:
                where_sql += " AND t.TABLE_SCHEMA = ?"
                params.append(schema)
            if object_name:
                where_sql += " AND t.TABLE_NAME LIKE ?"
                params.append(object_name)
            scope_sql, scope_params = _build_table_scope_sql("t.TABLE_SCHEMA", "t.TABLE_NAME")
            where_sql += scope_sql
            query_params = params + scope_params

            count_sql = f"SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES t {join_clause} " + where_sql
            data_sql = (
                f"SELECT t.TABLE_SCHEMA, t.TABLE_NAME, p.create_date, p.modify_date "
                f"FROM INFORMATION_SCHEMA.TABLES t {join_clause} "
                + where_sql
                + " ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME"
            )
            def row_mapper(rows):
                return [
                    {
                        "schema_name": row[0],
                        "table_name": row[1],
                        "create_date": row[2].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if row[2] else None,
                        "modify_date": row[3].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if row[3] else None,
                    }
                    for row in rows
                ]
            return _paginate_query(
                count_sql=count_sql,
                count_params=query_params,
                data_sql=data_sql,
                data_params=query_params,
                row_mapper=row_mapper,
            )
        elif object_type_norm == "VIEW":
            join_clause = "JOIN sys.views p ON t.TABLE_NAME = p.name AND t.TABLE_SCHEMA = SCHEMA_NAME(p.schema_id)"
            where_sql = "WHERE t.TABLE_TYPE = ?"
            params: list[Any] = ["VIEW"]
            if schema:
                where_sql += " AND t.TABLE_SCHEMA = ?"
                params.append(schema)
            if object_name:
                where_sql += " AND t.TABLE_NAME LIKE ?"
                params.append(object_name)
            scope_sql, scope_params = _build_table_scope_sql("t.TABLE_SCHEMA", "t.TABLE_NAME")
            where_sql += scope_sql
            query_params = params + scope_params

            count_sql = f"SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES t {join_clause} " + where_sql
            data_sql = (
                f"SELECT t.TABLE_SCHEMA, t.TABLE_NAME, p.create_date, p.modify_date "
                f"FROM INFORMATION_SCHEMA.TABLES t {join_clause} "
                + where_sql
                + " ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME"
            )
            def row_mapper(rows):
                return [
                    {
                        "schema_name": row[0],
                        "table_name": row[1],
                        "create_date": row[2].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if row[2] else None,
                        "modify_date": row[3].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if row[3] else None,
                    }
                    for row in rows
                ]
            return _paginate_query(
                count_sql=count_sql,
                count_params=query_params,
                data_sql=data_sql,
                data_params=query_params,
                row_mapper=row_mapper,
            )

        if object_type_norm == "INDEX":
            where_sql = """
            WHERE i.name IS NOT NULL
            """
            params: list[Any] = []
            if schema:
                where_sql += " AND s.name = ?"
                params.append(schema)
            if object_name:
                where_sql += " AND i.name LIKE ?"
                params.append(object_name)

            scope_sql, scope_params = _build_table_scope_sql("s.name", "t.name")
            where_sql += scope_sql
            params.extend(scope_params)

            count_sql = """
            SELECT COUNT(*)
            FROM sys.indexes i
            JOIN sys.tables t ON i.object_id = t.object_id
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            """ + where_sql

            data_sql = """
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                i.name AS index_name,
                i.type_desc AS index_type,
                i.is_disabled
            FROM sys.indexes i
            JOIN sys.tables t ON i.object_id = t.object_id
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            """ + where_sql + " ORDER BY s.name, t.name, i.name"
            return _paginate_query(
                count_sql=count_sql,
                count_params=params,
                data_sql=data_sql,
                data_params=params,
                row_mapper=lambda rows: _rows_to_dicts(cur, rows),
            )

        if object_type_norm in {"FUNCTION", "PROCEDURE", "TRIGGER"}:
            code = {"FUNCTION": "FN", "PROCEDURE": "P", "TRIGGER": "TR"}[object_type_norm]
            where_sql = """
            WHERE o.type = ?
            """
            params = [code]
            if schema:
                where_sql += " AND s.name = ?"
                params.append(schema)
            if object_name:
                where_sql += " AND o.name LIKE ?"
                params.append(object_name)

            count_sql = """
            SELECT COUNT(*)
            FROM sys.objects o
            JOIN sys.schemas s ON o.schema_id = s.schema_id
            """ + where_sql

            data_sql = """
            SELECT s.name AS schema_name, o.name AS object_name, o.type_desc
            FROM sys.objects o
            JOIN sys.schemas s ON o.schema_id = s.schema_id
            """ + where_sql + " ORDER BY s.name, o.name"
            return _paginate_query(
                count_sql=count_sql,
                count_params=params,
                data_sql=data_sql,
                data_params=params,
                row_mapper=lambda rows: _rows_to_dicts(cur, rows),
            )

        raise ValueError(f"Unsupported object_type: {object_type}")
    finally:
        conn.close()


def _get_index_fragmentation_data(
    instance: int,
    database_name: str | None,
    schema: str | None = None,
    min_fragmentation: float = 10.0,
    min_page_count: int = 100,
    limit: int = 50,
) -> list[dict[str, Any]]:
    validate_instance(instance)
    db_name = database_name or get_instance_config(instance)["db_name"]
    db_name_str = _normalize_db_name(db_name)
    conn = get_connection(db_name_str, instance=instance)
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


def db_sql2019_get_index_fragmentation(
    instance: int = 1,
    database_name: str | None = None,
    schema: str | None = None,
    min_fragmentation: float = 10.0,
    min_page_count: int = 100,
    limit: int = 50,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Return index fragmentation rows from dm_db_index_physical_stats."""
    items = _get_index_fragmentation_data(
        instance=instance,
        database_name=database_name,
        schema=schema,
        min_fragmentation=min_fragmentation,
        min_page_count=min_page_count,
        limit=limit,
    )
    return _paginate_tool_result(items, page=page, page_size=page_size)


def db_sql2019_analyze_index_health(
    instance: int = 1,
    database_name: str | None = None,
    schema: str | None = None,
    min_fragmentation: float = 10.0,
    min_page_count: int = 100,
    limit: int = 50,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """High-level index health summary."""
    items = _get_index_fragmentation_data(
        instance=instance,
        database_name=database_name,
        schema=schema,
        min_fragmentation=min_fragmentation,
        min_page_count=min_page_count,
        limit=limit,
    )

    severe = [r for r in items if (r.get("avg_fragmentation_in_percent") or 0) >= 30]
    medium = [r for r in items if 10 <= (r.get("avg_fragmentation_in_percent") or 0) < 30]

    db_name = database_name or get_instance_config(instance)["db_name"]
    result = {
        "database": db_name,
        "schema": schema,
        "fragmented_indexes": items,
        "summary": {
            "severe": len(severe),
            "medium": len(medium),
            "total": len(items),
        },
    }
    return _paginate_tool_result(result, page=page, page_size=page_size)


def db_sql2019_analyze_table_health(
    instance: int = 1,
    database_name: str | None = None,
    schema: str | None = None,
    table_name: str | None = None,
    view: Literal["summary", "standard", "full"] = "standard",
    fields: str | None = None,
    token_budget: int | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Table-level storage/index/stats/constraint analysis."""
    if not schema or not table_name:
        raise ValueError("schema and table_name are required")
    logger.info(
        "table_health.start instance=%s database=%s schema=%s table=%s view=%s",
        instance,
        database_name,
        schema,
        table_name,
        view,
    )
    validate_instance(instance)
    _enforce_table_scope_for_ident(schema, table_name)
    db_name = database_name or get_instance_config(instance)["db_name"]
    db_name_str = _normalize_db_name(db_name)
    conn = get_connection(db_name_str, instance=instance)
    try:
        cur = conn.cursor()
        # Table info
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

        # Column metadata
        _execute_safe(
            cur,
            """
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH, COLUMN_DEFAULT, NUMERIC_PRECISION, NUMERIC_SCALE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
            """,
            [schema, table_name],
        )
        columns = _rows_to_dicts(cur, cur.fetchall())

        # Indexes
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

        # Constraints (PK, unique, check, default)
        _execute_safe(
            cur,
            """
            SELECT tc.CONSTRAINT_NAME, tc.CONSTRAINT_TYPE, kcu.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
              ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA AND tc.TABLE_NAME = kcu.TABLE_NAME
            WHERE tc.TABLE_SCHEMA = ? AND tc.TABLE_NAME = ?
            ORDER BY tc.CONSTRAINT_TYPE, tc.CONSTRAINT_NAME
            """,
            [schema, table_name],
        )
        constraints = _rows_to_dicts(cur, cur.fetchall())

        # Foreign keys
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

        # Object dependencies
        _execute_safe(
            cur,
            """
            SELECT referencing_schema_name, referencing_entity_name, referencing_class_desc, is_caller_dependent
            FROM sys.dm_sql_referencing_entities (?, 'OBJECT')
            UNION ALL
            SELECT referenced_schema_name, referenced_entity_name, referenced_class_desc, NULL
            FROM sys.dm_sql_referenced_entities (?, 'OBJECT')
            """,
            [f"{schema}.{table_name}", f"{schema}.{table_name}"],
        )
        dependencies = _rows_to_dicts(cur, cur.fetchall())

        # Statistics sample
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

        # FK index checks
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

        # Additional tuning recommendations (datatype, wide columns, etc.)
        for col in columns:
            if col.get("DATA_TYPE", "").upper() in ("NVARCHAR", "VARCHAR") and (col.get("CHARACTER_MAXIMUM_LENGTH") is not None and col["CHARACTER_MAXIMUM_LENGTH"] > 255):
                recommendations.append({
                    "severity": "Low",
                    "recommendation": f"Column '{col['COLUMN_NAME']}' is wide ({col['CHARACTER_MAXIMUM_LENGTH']} chars). Consider if max length can be reduced for performance."
                })
            if col.get("DATA_TYPE", "").upper() == "INT" and col.get("IS_NULLABLE", "NO") == "NO":
                recommendations.append({
                    "severity": "Info",
                    "recommendation": f"Column '{col['COLUMN_NAME']}' is INT and NOT NULL. If values are small, consider using SMALLINT or TINYINT to save space."
                })

        result = {
            "table_info": table_info,
            "columns": columns,
            "indexes": indexes,
            "constraints": constraints,
            "foreign_keys": foreign_keys,
            "dependencies": dependencies,
            "statistics_sample": statistics_sample,
            "health_analysis": {
                "constraint_issues": constraint_issues,
                "index_issues": [],
            },
            "recommendations": recommendations,
        }
        shaped = _apply_table_health_view(result, view)
        budgeted = _apply_token_budget(shaped, token_budget)
        projected = _apply_field_projection(budgeted, fields)
        output = _paginate_tool_result(projected, page=page, page_size=page_size)
        logger.info(
            "table_health.success instance=%s database=%s schema=%s table=%s recommendations=%s",
            instance,
            db_name_str,
            schema,
            table_name,
            len(recommendations),
        )
        return output
    except Exception:
        logger.exception(
            "table_health.error instance=%s database=%s schema=%s table=%s",
            instance,
            db_name_str,
            schema,
            table_name,
        )
        raise
    finally:
        conn.close()


def db_sql2019_db_stats(instance: int = 1, database: str | None = None) -> dict[str, Any]:
    """Database object counts."""
    validate_instance(instance)
    db_name = database or get_instance_config(instance)["db_name"]
    db_name_str = _normalize_db_name(db_name)
    conn = get_connection(db_name_str, instance=instance)
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


def db_sql2019_server_info_mcp(
    instance: int = 1,
    server: Any = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Get SQL Server and MCP runtime information."""
    validate_instance(instance)
    conn = get_connection("master", instance=instance)
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
        inst_cfg = get_instance_config(instance)
        return {
            "server_version": row[0],
            "server_name": row[1],
            "database": row[2],
            "user": row[3],
            "server_version_short": row[4],
            "server_edition": row[5],
            "server_addr": inst_cfg.get("db_server"),
            "server_port": inst_cfg.get("db_port"),
            "mcp_transport": SETTINGS.transport,
            "mcp_max_rows": SETTINGS.max_rows,
            "mcp_allow_write": SETTINGS.allow_write,
            "mcp_server_name": server.name if server else MCP_SERVER_NAME,
            "http_user_agent": headers.get("user-agent", "") if headers else "",
        }
    finally:
        conn.close()


def _fetch_relationships(cur: pyodbc.Cursor, database: str) -> list[dict[str, Any]]:
    sql = """
    SELECT
        fk.name AS constraint_name,
        OBJECT_SCHEMA_NAME(fk.parent_object_id) AS parent_schema,
        OBJECT_NAME(fk.parent_object_id) AS parent_table,
        pc.name AS parent_column,
        OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS referenced_schema,
        OBJECT_NAME(fk.referenced_object_id) AS referenced_table,
        rc.name AS referenced_column
    FROM sys.foreign_keys AS fk
    INNER JOIN sys.foreign_key_columns AS fkc ON fk.object_id = fkc.constraint_object_id
    INNER JOIN sys.columns AS pc ON fkc.parent_object_id = pc.object_id AND fkc.parent_column_id = pc.column_id
    INNER JOIN sys.columns AS rc ON fkc.referenced_object_id = rc.object_id AND fkc.referenced_column_id = rc.column_id
    """
    _execute_safe(cur, sql)
    return _rows_to_dicts(cur, cur.fetchall())


def _analyze_erd_issues(entities: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    issues: dict[str, list[dict[str, Any]]] = {
        "entities": [],
        "attributes": [],
        "relationships": [],
        "identifiers": [],
        "normalization": [],
    }

    for entity in entities:
        table_name = entity.get("name")
        schema_name = entity.get("schema")
        cols = entity.get("columns", [])

        if not any(c.get("is_primary_key") for c in cols):
            issues["identifiers"].append(
                {
                    "entity": f"{schema_name}.{table_name}",
                    "issue": "Missing primary key",
                    "severity": "High",
                    "impact": "Entity identity cannot be guaranteed, impacting data integrity and join performance.",
                }
            )

        if len(cols) > 30:
            issues["normalization"].append(
                {
                    "entity": f"{schema_name}.{table_name}",
                    "issue": "Large number of attributes",
                    "severity": "Medium",
                    "impact": "Possible violation of normalization; consider splitting into multiple entities.",
                }
            )

    referenced_tables = {(r.get("referenced_schema"), r.get("referenced_table")) for r in relationships}
    all_modeled = {(e.get("schema"), e.get("name")) for e in entities}

    for schema, table in referenced_tables:
        if (schema, table) not in all_modeled:
            issues["relationships"].append(
                {
                    "issue": f"External reference to {schema}.{table}",
                    "severity": "Low",
                    "impact": "Relationship points to a table not included in the model scope.",
                }
            )

    return issues


def _render_data_model_html(model: dict[str, Any], issues: dict[str, list[dict[str, Any]]]) -> str:
    database_name = escape(str(model.get("database", "Unknown database")))
    summary = model.get("summary", {}) if isinstance(model.get("summary"), dict) else {}
    entities = model.get("entities", []) if isinstance(model.get("entities"), list) else []
    relationships = model.get("relationships", []) if isinstance(model.get("relationships"), list) else []
    entity_cards = _render_entity_cards_html(entities)
    relationships_html = _render_relationships_html(relationships)
    issue_total = sum(len(group) for group in issues.values())
    html = f"""
    <html>
    <head>
        <title>Logical Data Model - {database_name}</title>
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; margin: 0; background: #f4f7fb; color: #1f2937; }}
            .page {{ max-width: 1440px; margin: 0 auto; padding: 32px 24px 48px; }}
            .hero {{ background: linear-gradient(135deg, #0f172a, #1d4ed8); color: white; border-radius: 18px; padding: 28px; box-shadow: 0 18px 48px rgba(15, 23, 42, 0.18); }}
            .hero h1 {{ margin: 0 0 8px; font-size: 32px; }}
            .hero p {{ margin: 0; color: rgba(255,255,255,0.84); }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin: 24px 0; }}
            .stat {{ background: white; border-radius: 14px; padding: 18px; box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08); }}
            .stat .label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; }}
            .stat .value {{ font-size: 28px; font-weight: 700; margin-top: 8px; }}
            .section {{ margin-top: 28px; }}
            .section h2 {{ margin: 0 0 14px; font-size: 22px; }}
            .entity-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
            .entity-card, .panel {{ background: white; border-radius: 14px; box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08); overflow: hidden; }}
            .entity-head {{ padding: 16px 18px; border-bottom: 1px solid #e5e7eb; background: #eff6ff; }}
            .entity-title {{ font-size: 18px; font-weight: 700; margin: 0; }}
            .entity-subtitle {{ color: #475569; font-size: 12px; margin-top: 4px; }}
            .entity-body {{ max-height: 320px; overflow: auto; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: left; vertical-align: top; }}
            th {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; background: #f8fafc; }}
            .pill {{ display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; background: #dbeafe; color: #1d4ed8; }}
            .issue {{ color: #b91c1c; }}
            .muted {{ color: #64748b; }}
            .empty {{ padding: 18px; background: white; border-radius: 14px; color: #64748b; box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08); }}
        </style>
    </head>
    <body>
        <div class="page">
            <div class="hero">
                <h1>Logical Data Model</h1>
                <p>Database <strong>{database_name}</strong> with rendered entities, column metadata, and detected foreign-key relationships.</p>
            </div>
            <div class="stats">
                <div class="stat"><div class="label">Entities</div><div class="value">{len(entities)}</div></div>
                <div class="stat"><div class="label">Relationships</div><div class="value">{len(relationships)}</div></div>
                <div class="stat"><div class="label">Issues</div><div class="value">{issue_total}</div></div>
                <div class="stat"><div class="label">Summary</div><div class="value">{escape(str(summary.get('total_issues', issue_total)))}</div></div>
            </div>
            <div class="section">
                <h2>Relationships</h2>
                {relationships_html}
            </div>
            <div class="section">
                <h2>Entities</h2>
                {entity_cards}
            </div>
            <div class="section">
                <h2>Issues</h2>
                {_render_issue_list_html(issues)}
            </div>
        </div>
    </body>
    </html>
    """
    return html


def _render_performance_dashboard_html(report: dict[str, Any]) -> str:
    def fmt_num(value: Any, digits: int = 2) -> str:
        if isinstance(value, (int, float)):
            return f"{value:,.{digits}f}" if isinstance(value, float) else f"{value:,}"
        return "N/A"

    kpis = report.get("kpis", {}) if isinstance(report, dict) else {}
    top_queries = report.get("top_slow_queries", []) if isinstance(report, dict) else []
    top_fragments = report.get("top_fragmented_indexes", []) if isinstance(report, dict) else []

    query_rows = []
    for row in top_queries:
        if not isinstance(row, dict):
            continue
        query_rows.append(
            "<tr>"
            f"<td>{escape(str(row.get('query_id', '')))}</td>"
            f"<td>{escape(fmt_num(row.get('metric_value'), 2))}</td>"
            f"<td>{escape(str(row.get('count_executions', '')))}</td>"
            f"<td>{escape(str(row.get('last_execution_time', '')))}</td>"
            "</tr>"
        )
    if not query_rows:
        query_rows.append("<tr><td colspan='4' class='muted'>No slow query data available.</td></tr>")

    frag_rows = []
    for row in top_fragments:
        if not isinstance(row, dict):
            continue
        frag_rows.append(
            "<tr>"
            f"<td>{escape(str(row.get('schema_name', '')))}</td>"
            f"<td>{escape(str(row.get('table_name', '')))}</td>"
            f"<td>{escape(str(row.get('index_name', '')))}</td>"
            f"<td>{escape(fmt_num(row.get('avg_fragmentation_in_percent'), 2))}</td>"
            f"<td>{escape(str(row.get('page_count', '')))}</td>"
            "</tr>"
        )
    if not frag_rows:
        frag_rows.append("<tr><td colspan='5' class='muted'>No fragmentation data available.</td></tr>")

    return f"""
    <html>
    <head>
        <title>SQL Server Performance Dashboard</title>
        <meta http-equiv="refresh" content="30">
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; margin: 0; background: #eef2ff; color: #1f2937; }}
            .page {{ max-width: 1400px; margin: 0 auto; padding: 28px 24px 48px; }}
            .hero {{ background: linear-gradient(135deg, #111827, #2563eb); color: white; border-radius: 18px; padding: 24px; box-shadow: 0 18px 48px rgba(15, 23, 42, 0.18); }}
            .hero h1 {{ margin: 0 0 6px; }}
            .hero p {{ margin: 4px 0 0; color: rgba(255,255,255,0.88); }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin: 24px 0; }}
            .card, .panel {{ background: white; border-radius: 16px; box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08); }}
            .card {{ padding: 18px; }}
            .label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; }}
            .value {{ font-size: 28px; font-weight: 700; margin-top: 8px; }}
            .panel {{ overflow: hidden; margin-top: 20px; }}
            .panel-head {{ padding: 16px 18px; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; gap: 12px; }}
            .panel-title {{ font-size: 20px; font-weight: 700; }}
            .muted {{ color: #64748b; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
            th {{ background: #f8fafc; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; }}
            .small {{ font-size: 13px; color: #475569; }}
        </style>
    </head>
    <body>
        <div class="page">
            <div class="hero">
                <h1>SQL Server Performance Dashboard</h1>
                <p>Database {escape(str(report.get('database', '')))} on instance {escape(str(report.get('instance', '')))} ({escape(str(report.get('server', '')))}).</p>
                <p class="small">Generated at {escape(str(report.get('timestamp', '')))} | Query Store enabled: {escape(str(report.get('query_store_enabled', 'unknown')))}</p>
            </div>

            <div class="stats">
                <div class="card"><div class="label">Avg Query Duration Metric</div><div class="value">{escape(fmt_num(kpis.get('avg_query_duration_metric'), 2))}</div></div>
                <div class="card"><div class="label">Max Query Duration Metric</div><div class="value">{escape(fmt_num(kpis.get('max_query_duration_metric'), 2))}</div></div>
                <div class="card"><div class="label">Avg Fragmentation %</div><div class="value">{escape(fmt_num(kpis.get('fragmentation_avg_percent'), 2))}</div></div>
                <div class="card"><div class="label">Data Size MB</div><div class="value">{escape(fmt_num(kpis.get('data_size_mb'), 0))}</div></div>
                <div class="card"><div class="label">Open Transactions</div><div class="value">{escape(fmt_num(kpis.get('open_transactions'), 0))}</div></div>
                <div class="card"><div class="label">DB Users</div><div class="value">{escape(fmt_num(kpis.get('user_count'), 0))}</div></div>
            </div>

            <div class="panel">
                <div class="panel-head">
                    <div class="panel-title">Top Slow Queries</div>
                    <div class="muted">Showing top 5 by duration metric</div>
                </div>
                <table>
                    <thead>
                        <tr><th>Query ID</th><th>Duration Metric</th><th>Executions</th><th>Last Execution</th></tr>
                    </thead>
                    <tbody>{''.join(query_rows)}</tbody>
                </table>
            </div>

            <div class="panel">
                <div class="panel-head">
                    <div class="panel-title">Top Fragmented Indexes</div>
                    <div class="muted">Showing top 5 fragmentation rows</div>
                </div>
                <table>
                    <thead>
                        <tr><th>Schema</th><th>Table</th><th>Index</th><th>Fragmentation %</th><th>Pages</th></tr>
                    </thead>
                    <tbody>{''.join(frag_rows)}</tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """


def _render_entity_cards_html(entities: list[dict[str, Any]]) -> str:
    if not entities:
        return "<div class='empty'>No entities were found for this scope.</div>"

    cards: list[str] = []
    for entity in entities:
        schema_name = escape(str(entity.get("schema", "dbo")))
        table_name = escape(str(entity.get("name", "unknown")))
        columns = entity.get("columns", []) if isinstance(entity.get("columns"), list) else []
        rows: list[str] = []
        for column in columns:
            if not isinstance(column, dict):
                continue
            column_name = escape(str(column.get("COLUMN_NAME", column.get("name", ""))))
            data_type = escape(str(column.get("DATA_TYPE", column.get("type", ""))))
            nullable = escape(str(column.get("IS_NULLABLE", column.get("nullable", ""))))
            rows.append(
                f"<tr><td><strong>{column_name}</strong></td><td>{data_type}</td><td>{nullable}</td></tr>"
            )
        body = "".join(rows) if rows else "<tr><td colspan='3' class='muted'>No column metadata available.</td></tr>"
        cards.append(
            f"""
            <div class="entity-card">
                <div class="entity-head">
                    <p class="entity-title">{table_name}</p>
                    <div class="entity-subtitle">Schema: <span class="pill">{schema_name}</span></div>
                </div>
                <div class="entity-body">
                    <table>
                        <thead><tr><th>Column</th><th>Type</th><th>Nullable</th></tr></thead>
                        <tbody>{body}</tbody>
                    </table>
                </div>
            </div>
            """
        )
    return f"<div class='entity-grid'>{''.join(cards)}</div>"


def _render_relationships_html(relationships: list[dict[str, Any]]) -> str:
    if not relationships:
        return "<div class='empty'>No foreign-key relationships were discovered for this scope.</div>"

    rows: list[str] = []
    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue
        parent = f"{relationship.get('parent_schema', 'dbo')}.{relationship.get('parent_table', '')}.{relationship.get('parent_column', '')}"
        referenced = f"{relationship.get('referenced_schema', 'dbo')}.{relationship.get('referenced_table', '')}.{relationship.get('referenced_column', '')}"
        constraint_name = escape(str(relationship.get("constraint_name", "")))
        rows.append(
            f"<tr><td>{constraint_name}</td><td>{escape(parent)}</td><td>{escape(referenced)}</td></tr>"
        )

    return (
        "<div class='panel'><table><thead><tr><th>Constraint</th><th>From</th><th>To</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _render_issue_list_html(issues: dict[str, list[dict[str, Any]]]) -> str:
    items = []
    for category, list_obj in issues.items():
        for issue in list_obj:
            items.append(f"<li class='issue'><b>[{escape(category.upper())}]</b> {escape(str(issue.get('issue', 'Issue detected')))} in {escape(str(issue.get('entity', 'model')))}</li>")
    if not items:
        return "<p>No issues found.</p>"
    return "<ul>" + "".join(items) + "</ul>"


def _analyze_logical_data_model_internal(
    instance: int,
    database_name: str | None,
    schema: str | None = None,
) -> dict[str, Any]:
    validate_instance(instance)
    db_name = database_name or get_instance_config(instance)["db_name"]
    db_name_str = str(db_name) if not isinstance(db_name, str) else db_name
    conn = get_connection(db_name_str, instance=instance)
    try:
        cur = conn.cursor()
        
        # Fetch entities (tables)
        where_sql = ""
        params = []
        if schema:
            where_sql = "WHERE s.name = ?"
            params.append(schema)
            
        _execute_safe(
            cur,
            f"""
            SELECT s.name AS schema_name, t.name AS table_name
            FROM sys.tables t
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            {where_sql}
            """,
            params,
        )
        tables = cur.fetchall()
        
        entities = []
        for t_schema, t_name in tables:
             _execute_safe(
                 cur,
                 """
                 SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                 FROM INFORMATION_SCHEMA.COLUMNS
                 WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
                 """,
                 [t_schema, t_name],
             )
             cols = _rows_to_dicts(cur, cur.fetchall())
             entities.append({
                 "schema": t_schema,
                 "name": t_name,
                 "columns": cols
             })
             
        relationships = _fetch_relationships(cur, str(db_name) if not isinstance(db_name, str) else db_name)
        issues = _analyze_erd_issues(entities, relationships)
        
        return {
            "database": db_name,
            "entities": entities,
            "relationships": relationships,
            "issues": issues,
            "summary": {
                "entity_count": len(entities),
                "relationship_count": len(relationships),
                "total_issues": sum(len(v) for v in issues.values())
            }
        }
    finally:
        conn.close()


def db_sql2019_show_top_queries(
    instance: int = 1,
    database_name: str | None = None,
    metric: Literal["cpu", "io", "execution_count", "duration"] = "cpu",
    limit: int = 10,
    view: Literal["summary", "standard", "full"] = "standard",
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Performance analysis using Query Store or dm_exec_query_stats."""
    validate_instance(instance)
    db_name = database_name or get_instance_config(instance)["db_name"]
    db_name_str = str(db_name) if not isinstance(db_name, str) else db_name
    conn = get_connection(db_name_str, instance=instance)
    try:
        cur = conn.cursor()
        
        # Check if Query Store is enabled
        _execute_safe(cur, "SELECT actual_state_desc FROM sys.database_query_store_options")
        qs_row = cur.fetchone()
        qs_enabled = qs_row[0] != "OFF" if qs_row else False
        
        if qs_enabled:
            # Query Store metrics
            metric_cols = {
                "cpu": "avg_cpu_time",
                "io": "avg_logical_io_reads",
                "execution_count": "count_executions",
                "duration": "avg_duration"
            }
            sort_col = metric_cols.get(metric, "avg_cpu_time")
            
            sql = f"""
            SELECT TOP (?)
                q.query_id,
                qt.query_sql_text,
                rs.{sort_col} AS metric_value,
                rs.count_executions,
                CAST(rs.last_execution_time AS nvarchar(40)) AS last_execution_time
            FROM sys.query_store_query q
            JOIN sys.query_store_query_text qt ON q.query_text_id = qt.query_text_id
            JOIN sys.query_store_plan p ON q.query_id = p.query_id
            JOIN sys.query_store_runtime_stats rs ON p.plan_id = rs.plan_id
            ORDER BY rs.{sort_col} DESC
            """
            _execute_safe(cur, sql, [limit])
        else:
            # DMV fallback
            metric_cols = {
                "cpu": "total_worker_time / execution_count",
                "io": "total_logical_reads / execution_count",
                "execution_count": "execution_count",
                "duration": "total_elapsed_time / execution_count"
            }
            sort_col = metric_cols.get(metric, "total_worker_time / execution_count")
            
            sql = f"""
            SELECT TOP (?)
                NULL AS query_id,
                st.text AS query_sql_text,
                {sort_col} AS metric_value,
                count.execution_count,
                CAST(count.last_execution_time AS nvarchar(40)) AS last_execution_time
            FROM sys.dm_exec_query_stats count
            CROSS APPLY sys.dm_exec_sql_text(count.sql_handle) st
            ORDER BY metric_value DESC
            """
            _execute_safe(cur, sql, [limit])
            
        rows = _rows_to_dicts(cur, cur.fetchall())
        result = {
            "database": db_name,
            "query_store_enabled": qs_enabled,
            "queries": rows,
            "metric": metric
        }
        shaped = _apply_top_queries_view(result, view)
        return _paginate_tool_result(shaped, page=page, page_size=page_size)
    finally:
        conn.close()


def db_sql2019_check_fragmentation(
    instance: int = 1,
    database_name: str | None = None,
    schema_name: str | None = None,
    table_name: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Check fragmentation for a specific table or all tables in a schema."""
    items = _get_index_fragmentation_data(
        instance=instance,
        database_name=str(database_name) if database_name is not None and not isinstance(database_name, str) else database_name,
        schema=schema_name,
    )
    if table_name:
        items = [i for i in items if i.get("table_name", "").lower() == table_name.lower()]
    return _paginate_tool_result(items, page=page, page_size=page_size)


def db_sql2019_db_sec_perf_metrics(
    instance: int = 1,
    database_name: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Database security and basic performance metrics."""
    validate_instance(instance)
    db_name = database_name or get_instance_config(instance)["db_name"]
    db_name_str = str(db_name) if not isinstance(db_name, str) else db_name
    conn = get_connection(db_name_str, instance=instance)
    try:
        cur = conn.cursor()
        
        metrics = {}
        # User count
        _execute_safe(cur, "SELECT COUNT(*) FROM sys.database_principals WHERE type IN ('S', 'U', 'G')")
        user_count_row = cur.fetchone()
        metrics["user_count"] = user_count_row[0] if user_count_row else 0
        
        # Open transactions
        _execute_safe(cur, "SELECT COUNT(*) FROM sys.dm_tran_database_transactions WHERE database_id = DB_ID()")
        open_tx_row = cur.fetchone()
        metrics["open_transactions"] = open_tx_row[0] if open_tx_row else 0
        
        # Data file size
        _execute_safe(cur, "SELECT SUM(size) * 8 / 1024 FROM sys.database_files WHERE type = 0")
        data_size_row = cur.fetchone()
        metrics["data_size_mb"] = data_size_row[0] if data_size_row else 0
        
        return _paginate_tool_result(metrics, page=page, page_size=page_size)
    finally:
        conn.close()


def db_sql2019_explain_query(
    instance: int = 1,
    database_name: str | None = None,
    sql: str | None = None,
) -> dict[str, Any]:
    """Execution plan analysis (SHOWPLAN_ALL)."""
    if not sql:
        raise ValueError("sql is required")
    validate_instance(instance)
    _require_readonly(sql)
    _enforce_table_scope_for_sql(sql)
    
    db_name = database_name or get_instance_config(instance)["db_name"]
    db_name_str = str(db_name) if not isinstance(db_name, str) else db_name
    conn = get_connection(db_name_str, instance=instance)
    try:
        cur = conn.cursor()
        _execute_safe(cur, "SET SHOWPLAN_ALL ON")
        try:
            _execute_safe(cur, sql)
            plan_rows = _rows_to_dicts(cur, cur.fetchall())
        finally:
            _execute_safe(cur, "SET SHOWPLAN_ALL OFF")
            
        return {"database": db_name, "plan": plan_rows}
    finally:
        conn.close()


def db_sql2019_analyze_logical_data_model(
    instance: int = 1,
    database_name: str | None = None,
    schema: str | None = None,
    view: Literal["summary", "standard", "full"] = "standard",
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Analyze database schema for logical data modeling issues."""
    result = _analyze_logical_data_model_internal(instance, str(database_name) if database_name is not None and not isinstance(database_name, str) else database_name, schema)
    shaped = _apply_logical_model_view(result, view)
    return _paginate_tool_result(shaped, page=page, page_size=page_size)


def db_sql2019_open_logical_model(
    instance: int = 1,
    database_name: str | None = None,
    schema: str | None = None,
    return_dict: bool = False,
) -> str | dict[str, Any]:
    """Generate a logical model report.

    When return_dict is False (default), returns the rendered HTML string for backward compatibility.
    When return_dict is True, returns metadata including erd_url, report_id, and summary.
    """
    result = _analyze_logical_data_model_internal(instance, str(database_name) if database_name is not None and not isinstance(database_name, str) else database_name, schema)
    html = _render_data_model_html(result, result.get("issues", {}))
    
    # Generate UUID and store report
    report_id = uuid.uuid4().hex
    with _REPORT_STORAGE_LOCK:
        _REPORT_STORAGE[report_id] = {
            "html": html,
            "database": database_name or get_instance_config(instance)["db_name"],
            "schema": schema or "all",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "instance": instance,
        }
    _persist_report_html(report_id, html)

    if return_dict:
        # Return dict with URL and metadata
        return {
            "message": f"ERD webpage generated for database '{database_name or get_instance_config(instance)['db_name']}'.",
            "database": database_name or get_instance_config(instance)["db_name"],
            "erd_url": f"{_public_base_url()}/data-model-analysis?id={report_id}",
            "report_id": report_id,
            "summary": result.get("summary", {}),
            "url_hint": "Set MCP_PUBLIC_BASE_URL when the server runs behind Docker port mapping or a reverse proxy.",
        }

    return html


def db_sql2019_generate_ddl(
    instance: int = 1,
    database_name: str | None = None,
    schema_name: str = "dbo",
    table_name: str | None = None,
) -> str:
    """Generate T-SQL CREATE TABLE script."""
    if not table_name:
        raise ValueError("table_name is required")
    validate_instance(instance)
    _enforce_table_scope_for_ident(schema_name, table_name)
    db_name = database_name or get_instance_config(instance)["db_name"]
    db_name_str = str(db_name) if not isinstance(db_name, str) else db_name
    conn = get_connection(db_name_str, instance=instance)
    try:
        cur = conn.cursor()
        
        def _render_type(row: Any) -> str:
            t = str(row[1]).upper()
            if t in ("VARCHAR", "NVARCHAR", "VARBINARY", "CHAR", "NCHAR"):
                length = int(row[3]) if row[3] is not None else -1
                return f"{t}({'MAX' if length == -1 else length})"
            if t in ("DECIMAL", "NUMERIC"):
                return f"{t}({row[4]}, {row[5]})"
            return t

        _execute_safe(
            cur,
            """
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH,
                   NUMERIC_PRECISION, NUMERIC_SCALE, COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
            """,
            [schema_name, table_name],
        )
        rows = cur.fetchall()
        if not rows:
            raise ValueError(f"Table not found: {schema_name}.{table_name}")

        lines = [f"CREATE TABLE [{schema_name}]. [{table_name}] ("]
        col_lines = []
        for r in rows:
            line = f"    [{r[0]}] {_render_type(r)}"
            if str(r[2]).upper() == "NO":
                line += " NOT NULL"
            if r[6]:
                line += f" DEFAULT {r[6]}"
            col_lines.append(line)
        lines.append(",\n".join(col_lines))
        lines.append(");")
        return "\n".join(lines)
    finally:
        conn.close()


def db_sql2019_create_db_user(
    instance: int = 1,
    username: str | None = None,
    password: str | None = None,
    database_name: str | None = None,
) -> dict[str, Any]:
    """Create a database user."""
    _ensure_write_enabled()
    if not username or not password:
        raise ValueError("username and password are required")
    validate_instance(instance)
    db_name = database_name or get_instance_config(instance)["db_name"]
    db_name_str = str(db_name) if not isinstance(db_name, str) else db_name
    conn = get_connection(db_name_str, instance=instance)
    try:
        cur = conn.cursor()
        # SQL Server does not allow parameterized identifiers or DDL keywords, so we must inline safely.
        # Escape single quotes in password and username
        safe_username = str(username).replace("'", "''")
        safe_password = str(password).replace("'", "''")
        sql = f"CREATE USER [{safe_username}] WITH PASSWORD = '{safe_password}'"
        _execute_safe(cur, sql)
        return {"status": "success", "username": username, "database": db_name}
    finally:
        conn.close()


def db_sql2019_drop_db_user(
    instance: int = 1,
    username: str | None = None,
    database_name: str | None = None,
) -> dict[str, Any]:
    """Drop a database user."""
    _ensure_write_enabled()
    if not username:
        raise ValueError("username is required")
    validate_instance(instance)
    db_name = database_name or get_instance_config(instance)["db_name"]
    db_name_str = str(db_name) if not isinstance(db_name, str) else db_name
    conn = get_connection(db_name_str, instance=instance)
    try:
        cur = conn.cursor()
        try:
            _execute_safe(cur, f"DROP USER [{username}]")
            return {"status": "success", "username": username, "database": db_name}
        except pyodbc.ProgrammingError as e:
            # If user does not exist, treat as success for idempotency
            if "Cannot drop the user" in str(e) and "does not exist" in str(e):
                return {"status": "not_found", "username": username, "database": db_name}
            raise
    finally:
        conn.close()


def db_sql2019_kill_session(instance: int = 1, session_id: int | None = None) -> dict[str, Any]:
    """Kill a database session."""
    _ensure_write_enabled()
    if session_id is None:
        raise ValueError("session_id is required")
    validate_instance(instance)
    conn = get_connection("master", instance=instance)
    try:
        cur = conn.cursor()
        try:
            _execute_safe(cur, f"KILL {int(session_id)}")
            return {"status": "success", "session_id": session_id}
        except pyodbc.ProgrammingError as e:
            # If session does not exist, treat as success for idempotency
            if "is not valid" in str(e):
                return {"status": "not_found", "session_id": session_id}
            raise
    finally:
        conn.close()


def db_sql2019_create_object(
    instance: int = 1,
    database_name: str | None = None,
    sql: str | None = None,
) -> dict[str, Any]:
    """Execute CREATE statement."""
    _ensure_write_enabled()
    if not sql:
        raise ValueError("sql is required")
    validate_instance(instance)
    db_name = database_name or get_instance_config(instance)["db_name"]
    _run_query_internal(
        instance=instance,
        database_name=str(db_name) if not isinstance(db_name, str) else db_name,
        sql=sql,
        enforce_readonly=False,
        tool_name="db_sql2019_create_object",
    )
    return {"status": "success", "database": db_name}


def db_sql2019_alter_object(
    instance: int = 1,
    database_name: str | None = None,
    sql: str | None = None,
) -> dict[str, Any]:
    """Execute ALTER statement."""
    _ensure_write_enabled()
    if not sql:
        raise ValueError("sql is required")
    validate_instance(instance)
    db_name = database_name or get_instance_config(instance)["db_name"]
    _run_query_internal(
        instance=instance,
        database_name=str(db_name) if not isinstance(db_name, str) else db_name,
        sql=sql,
        enforce_readonly=False,
        tool_name="db_sql2019_alter_object",
    )
    return {"status": "success", "database": db_name}


def db_sql2019_drop_object(
    instance: int = 1,
    database_name: str | None = None,
    sql: str | None = None,
) -> dict[str, Any]:
    """Execute DROP statement."""
    _ensure_write_enabled()
    if not sql:
        raise ValueError("sql is required")
    validate_instance(instance)
    db_name = database_name or get_instance_config(instance)["db_name"]
    _run_query_internal(
        instance=instance,
        database_name=str(db_name) if not isinstance(db_name, str) else db_name,
        sql=sql,
        enforce_readonly=False,
        tool_name="db_sql2019_drop_object",
    )
    return {"status": "success", "database": db_name}


def _register_dual_instance_tools():
    """Systematically register all tools for both db_01 and db_02 instances."""
    tool_map = {
        "ping": db_sql2019_ping,
        "list_databases": db_sql2019_list_databases,
        "list_tables": db_sql2019_list_tables,
        "get_schema": db_sql2019_get_schema,
        "execute_query": db_sql2019_execute_query,
        "run_query": db_sql2019_run_query,
        "list_objects": db_sql2019_list_objects,
        "index_fragmentation": db_sql2019_get_index_fragmentation,
        "index_health": db_sql2019_analyze_index_health,
        "table_health": db_sql2019_analyze_table_health,
        "db_stats": db_sql2019_db_stats,
        "server_info_mcp": db_sql2019_server_info_mcp,
        "show_top_queries": db_sql2019_show_top_queries,
        "check_fragmentation": db_sql2019_check_fragmentation,
        "db_sec_perf_metrics": db_sql2019_db_sec_perf_metrics,
        "explain_query": db_sql2019_explain_query,
        "analyze_logical_data_model": db_sql2019_analyze_logical_data_model,
        "open_logical_model": db_sql2019_open_logical_model,
        "generate_ddl": db_sql2019_generate_ddl,
        "create_db_user": db_sql2019_create_db_user,
        "drop_db_user": db_sql2019_drop_db_user,
        "kill_session": db_sql2019_kill_session,
        "create_object": db_sql2019_create_object,
        "alter_object": db_sql2019_alter_object,
        "drop_object": db_sql2019_drop_object,
    }

    for instance in [1, 2]:
        prefix = "db_01_" if instance == 1 else "db_02_"
        for name, func in tool_map.items():
            tool_name = f"{prefix}{name}"
            
            # Use a closure to capture function and instance correctly
            def make_wrapper(f, inst, registered_tool_name: str):
                @wraps(f)
                def wrapper(*args, **kwargs):
                    # Remove instance from kwargs if it was passed by MCP (it shouldn't be, but just in case)
                    kwargs.pop("instance", None)
                    kwargs["instance"] = inst
                    invocation_id = uuid.uuid4().hex
                    start = time.perf_counter()
                    context = {
                        "instance": inst,
                        "database_name": kwargs.get("database_name") or kwargs.get("database"),
                        "schema": kwargs.get("schema") or kwargs.get("schema_name"),
                        "table_name": kwargs.get("table_name"),
                        "args_keys": sorted(list(kwargs.keys())),
                    }
                    function_name = f.__name__
                    _log_tool_start(registered_tool_name, function_name, invocation_id, context)
                    try:
                        result = f(*args, **kwargs)
                        elapsed_ms = int((time.perf_counter() - start) * 1000)
                        _log_tool_success(registered_tool_name, function_name, invocation_id, elapsed_ms, result)
                        return result
                    except Exception as exc:
                        elapsed_ms = int((time.perf_counter() - start) * 1000)
                        _log_tool_error(registered_tool_name, function_name, invocation_id, elapsed_ms, exc)
                        raise
                return wrapper
            
            wrapped = make_wrapper(func, instance, tool_name)
            mcp.tool(name=tool_name)(wrapped)

            # Backward-compatible aliases for clients that call by function-style names.
            # Example: db_sql2019_analyze_table_health / db_01_sql2019_analyze_table_health
            func_name = getattr(func, "__name__", "")
            alias_name_set: set[str] = set()
            if func_name.startswith("db_sql2019_"):
                suffix = func_name.removeprefix("db_sql2019_")
                # Per-instance function-style alias.
                alias_name_set.add(f"{prefix}sql2019_{suffix}")
                # Unprefixed function-style alias routes to instance 1 for compatibility.
                if instance == 1:
                    alias_name_set.add(func_name)

            # Per-instance map-key-style alias (e.g. db_01_sql2019_table_health).
            alias_name_set.add(f"{prefix}sql2019_{name}")
            # Unprefixed map-key-style alias routes to instance 1 for compatibility.
            if instance == 1:
                alias_name_set.add(f"db_sql2019_{name}")
                # Typo-compatible aliases observed in some clients (db_db2019_*).
                alias_name_set.add(f"db_db2019_{name}")
                if func_name.startswith("db_sql2019_"):
                    alias_name_set.add(func_name.replace("db_sql2019_", "db_db2019_", 1))

            for alias_name in sorted(alias_name_set):
                alias_wrapped = make_wrapper(func, instance, alias_name)
                mcp.tool(name=alias_name)(alias_wrapped)


_register_dual_instance_tools()


# === Web UI Endpoints ===

def _generate_sessions_monitor_html() -> str:
    """Generate HTML for the sessions monitoring dashboard."""
    return _generate_sessions_monitor_html_for_instance(1)


def _fetch_sessions_monitor_snapshot(instance: int) -> dict[str, Any]:
    validate_instance(instance)
    inst_cfg = get_instance_config(instance)
    conn = get_connection("master", instance=instance)
    try:
        cur = conn.cursor()
        _execute_safe(
            cur,
            """
            SELECT
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS active_sessions,
                SUM(CASE WHEN status = 'sleeping' THEN 1 ELSE 0 END) AS idle_sessions,
                COUNT(*) AS total_sessions
            FROM sys.dm_exec_sessions
            WHERE is_user_process = 1
            """,
        )
        summary_row = cur.fetchone()
        _execute_safe(
            cur,
            """
            SELECT TOP (15)
                s.session_id,
                s.login_name,
                s.host_name,
                s.program_name,
                s.status,
                DB_NAME(r.database_id) AS database_name,
                COALESCE(r.command, '') AS command,
                COALESCE(r.cpu_time, s.cpu_time, 0) AS cpu_time_ms,
                COALESCE(r.total_elapsed_time, 0) AS elapsed_time_ms,
                LEFT(REPLACE(REPLACE(COALESCE(t.text, ''), CHAR(13), ' '), CHAR(10), ' '), 220) AS sql_text
            FROM sys.dm_exec_sessions AS s
            LEFT JOIN sys.dm_exec_requests AS r ON s.session_id = r.session_id
            OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) AS t
            WHERE s.is_user_process = 1
            ORDER BY
                CASE WHEN r.session_id IS NULL THEN 1 ELSE 0 END,
                COALESCE(r.total_elapsed_time, 0) DESC,
                COALESCE(r.cpu_time, s.cpu_time, 0) DESC
            """,
        )
        top_sessions = _rows_to_dicts(cur, cur.fetchall())
        return {
            "instance": instance,
            "database": inst_cfg.get("db_name"),
            "server": inst_cfg.get("db_server"),
            "active_sessions": int(summary_row[0] or 0) if summary_row else 0,
            "idle_sessions": int(summary_row[1] or 0) if summary_row else 0,
            "total_sessions": int(summary_row[2] or 0) if summary_row else 0,
            "top_sessions": top_sessions,
            "available_instances": sorted(SETTINGS.db_instances.keys()),
            "generated_at": _now_utc_iso(),
        }
    finally:
        conn.close()


def _render_session_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<tr><td colspan='8' class='muted'>No user sessions were found.</td></tr>"

    rendered_rows: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rendered_rows.append(
            "<tr>"
            f"<td>{escape(str(row.get('session_id', '')))}</td>"
            f"<td>{escape(str(row.get('login_name', '')))}</td>"
            f"<td>{escape(str(row.get('host_name', '')))}</td>"
            f"<td>{escape(str(row.get('status', '')))}</td>"
            f"<td>{escape(str(row.get('database_name') or ''))}</td>"
            f"<td>{escape(str(row.get('command', '')))}</td>"
            f"<td>{escape(str(row.get('elapsed_time_ms', 0)))}</td>"
            f"<td>{escape(str(row.get('sql_text', '')))}</td>"
            "</tr>"
        )
    return "".join(rendered_rows)


def _generate_sessions_monitor_html_for_instance(instance: int) -> str:
    snapshot = _fetch_sessions_monitor_snapshot(instance)
    links = []
    for instance_id in snapshot.get("available_instances", []):
        active_class = "instance-link active" if instance_id == instance else "instance-link"
        links.append(f"<a class='{active_class}' href='/sessions-monitor?instance={instance_id}'>Instance {instance_id}</a>")
    switcher = "".join(links)
    return f"""
    <html>
    <head>
        <title>SQL Server Sessions Monitor</title>
        <meta http-equiv="refresh" content="15">
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; margin: 0; background: #eef2ff; color: #1f2937; }}
            .page {{ max-width: 1400px; margin: 0 auto; padding: 28px 24px 48px; }}
            .hero {{ background: linear-gradient(135deg, #0f172a, #1d4ed8); color: white; border-radius: 18px; padding: 24px; box-shadow: 0 18px 48px rgba(15, 23, 42, 0.18); }}
            .hero h1 {{ margin: 0 0 6px; }}
            .hero p {{ margin: 4px 0 0; color: rgba(255,255,255,0.86); }}
            .switcher {{ margin-top: 16px; display: flex; gap: 10px; flex-wrap: wrap; }}
            .instance-link {{ display: inline-block; padding: 8px 14px; border-radius: 999px; text-decoration: none; color: white; background: rgba(255,255,255,0.18); }}
            .instance-link.active {{ background: white; color: #1d4ed8; font-weight: 700; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin: 24px 0; }}
            .card, .table-panel {{ background: white; border-radius: 16px; box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08); }}
            .card {{ padding: 18px; }}
            .label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; }}
            .value {{ font-size: 28px; font-weight: 700; margin-top: 8px; }}
            .table-panel {{ overflow: hidden; }}
            .panel-head {{ padding: 16px 18px; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; gap: 12px; }}
            .panel-title {{ font-size: 20px; font-weight: 700; }}
            .muted {{ color: #64748b; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
            th {{ background: #f8fafc; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; }}
            code {{ font-family: Consolas, monospace; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="page">
            <div class="hero">
                <h1>SQL Server Sessions Monitor</h1>
                <p>Instance {snapshot['instance']} on {escape(str(snapshot['server']))} watching database {escape(str(snapshot['database']))}.</p>
                <div class="switcher">{switcher}</div>
            </div>
            <div class="stats">
                <div class="card"><div class="label">Active Sessions</div><div class="value">{snapshot['active_sessions']}</div></div>
                <div class="card"><div class="label">Idle Sessions</div><div class="value">{snapshot['idle_sessions']}</div></div>
                <div class="card"><div class="label">Total Sessions</div><div class="value">{snapshot['total_sessions']}</div></div>
                <div class="card"><div class="label">Generated At</div><div class="value" style="font-size:16px">{escape(str(snapshot['generated_at']))}</div></div>
            </div>
            <div class="table-panel">
                <div class="panel-head">
                    <div class="panel-title">Top Sessions</div>
                    <div class="muted">Auto-refreshes every 15 seconds</div>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Session</th><th>Login</th><th>Host</th><th>Status</th><th>Database</th><th>Command</th><th>Elapsed ms</th><th>SQL</th>
                        </tr>
                    </thead>
                    <tbody>{_render_session_rows(snapshot['top_sessions'])}</tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """


# ============================================================================
# Generative Dashboard Tools (FastMCP 3.2.0+ with GenerativeUI)
# ============================================================================
# These tools dynamically generate Prefab UI dashboards using LLM-written code.
# The LLM sees examples of Prefab components and generates code in real-time.
# This allows rich, interactive dashboards without pre-built HTML.

def db_sql2019_generate_sessions_dashboard(instance: int = 1) -> dict[str, Any]:
    """
    Generate a dynamic Prefab UI dashboard for real-time session monitoring.
    
    The LLM writes Python code using Prefab components (charts, cards, tables)
    to visualize active sessions, their status, and query performance metrics.
    The dashboard updates dynamically as the user's analysis progresses.
    
    Returns a Prefab app definition that the browser renders in real-time as tokens are generated.
    """
    try:
        if not GENERATIVE_UI_AVAILABLE:
            return {"status": "error", "message": "GenerativeUI not available. Install with: pip install fastmcp[apps]"}
        
        # Fetch current sessions metadata for context
        inst_cfg = get_instance_config(instance)
        conn = get_connection(instance=instance)
        try:
            cur = conn.cursor()
            # Lightweight query for session counts
            _execute_safe(cur, """
                SELECT COUNT(*) as active_sessions
                FROM sys.dm_exec_sessions 
                WHERE session_id > 50
            """)
            row = cur.fetchone()
            active_sessions = row[0] if row else 0
        finally:
            conn.close()
        
        # Return context for the LLM to build the dashboard
        return {
            "status": "ready",
            "tool_name": "generate_prefab_ui",
            "instructions": """
Generate a Prefab Python UI dashboard for SQL Server session monitoring.

Use these Prefab components:
- Column, Row, Heading, Text, Card, CardContent, Badge
- from prefab_ui.components.charts import BarChart, LineChart, ChartSeries

Include:
1. Header with database name and instance info
2. Session stats cards (Active, Idle, Total)
3. A chart showing session duration distribution
4. A table listing top sessions with status

Example structure:
    with Column(gap=6, css_class="p-6"):
        Heading(f"Session Monitor - {database_name}")
        with Row(gap=4):
            # Stat cards here
        # Chart and table here
            """,
            "data": {
                "database": inst_cfg.get("db_name"),
                "server": inst_cfg.get("db_server"),
                "active_sessions": active_sessions,
                "instance": instance,
                "timestamp": _now_utc_iso()
            }
        }
    except Exception as e:
        logger.error(f"Error in db_sql2019_generate_sessions_dashboard: {e}")
        return {"status": "error", "message": str(e)}


def db_sql2019_generate_model_diagram(database_name: str, instance: int = 1) -> dict[str, Any]:
    """
    Generate a dynamic Prefab UI diagram for the logical data model.
    
    The LLM analyzes the database schema and writes Python code using Prefab
    to visualize entity relationships, constraints, and health metrics.
    
    Returns a Prefab app definition with an interactive schema visualization.
    """
    try:
        if not GENERATIVE_UI_AVAILABLE:
            return {"status": "error", "message": "GenerativeUI not available. Install with: pip install fastmcp[apps]"}
        
        # Get schema info for the LLM to reference
        inst_cfg = get_instance_config(instance)
        conn = get_connection(instance=instance)
        db_ident = _quote_sql_ident(database_name)
        try:
            cur = conn.cursor()
            # Count tables and relationships
            _execute_safe(cur, f"""
                SELECT COUNT(*) as table_count
                FROM {db_ident}.INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
            """)
            tables_row = cur.fetchone()
            table_count = tables_row[0] if tables_row else 0
            
            _execute_safe(cur, f"""
                SELECT COUNT(*) as fk_count
                FROM {db_ident}.INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                WHERE CONSTRAINT_TYPE = 'FOREIGN KEY'
            """)
            fk_row = cur.fetchone()
            fk_count = fk_row[0] if fk_row else 0
        finally:
            conn.close()
        
        return {
            "status": "ready",
            "tool_name": "generate_prefab_ui",
            "instructions": """
Generate a Prefab Python UI dashboard for the logical data model.

Use these Prefab components:
- Column, Row, Heading, Text, Badge, Card, CardContent
- from prefab_ui.components.charts import BarChart, ChartSeries
- Heading levels, color-coded badges for constraints

Include:
1. Title with database name
2. Summary badges (Table Count, FK Count, Health Score)
3. A chart showing table size distribution
4. Key constraints and normalization insights
5. Recommendations for schema improvements

Example structure:
    with Column(gap=6, css_class="p-8"):
        Heading(f"Data Model - {database_name}")
        with Row(gap=4):
            # Summary badges
        # Charts and insights
            """,
            "data": {
                "database": database_name,
                "server": inst_cfg.get("db_server"),
                "table_count": table_count,
                "foreign_key_count": fk_count,
                "instance": instance,
                "timestamp": _now_utc_iso()
            }
        }
    except Exception as e:
        logger.error(f"Error in db_sql2019_generate_model_diagram: {e}")
        return {"status": "error", "message": str(e)}


def db_sql2019_generate_performance_dashboard(database_name: str, instance: int = 1) -> dict[str, Any]:
    """
    Generate a dynamic Prefab UI dashboard for performance metrics.
    
    The LLM writes Python code to visualize query performance, index fragmentation,
    CPU usage, and other key performance indicators in an interactive dashboard.
    
    Returns a Prefab app definition with performance visualizations.
    """
    try:
        validate_instance(instance)
        db_name = database_name or get_instance_config(instance)["db_name"]
        db_name_str = _normalize_db_name(db_name)
        inst_cfg = get_instance_config(instance)

        top_q = db_sql2019_show_top_queries(
            instance=instance,
            database_name=db_name_str,
            metric="duration",
            limit=10,
            view="standard",
            page=1,
            page_size=50,
        )
        frag = db_sql2019_check_fragmentation(
            instance=instance,
            database_name=db_name_str,
            page=1,
            page_size=50,
        )
        sec_perf = db_sql2019_db_sec_perf_metrics(instance=instance, database_name=db_name_str)

        queries = top_q.get("queries", []) if isinstance(top_q, dict) else []
        metric_values = [
            q.get("metric_value", 0)
            for q in queries
            if isinstance(q, dict) and isinstance(q.get("metric_value", 0), (int, float))
        ]
        avg_query_metric = (sum(metric_values) / len(metric_values)) if metric_values else None
        max_query_metric = max(metric_values) if metric_values else None

        frag_items = frag.get("items", []) if isinstance(frag, dict) else []
        frag_vals = [
            r.get("avg_fragmentation_in_percent", 0)
            for r in frag_items
            if isinstance(r, dict) and isinstance(r.get("avg_fragmentation_in_percent", 0), (int, float))
        ]
        avg_frag = (sum(frag_vals) / len(frag_vals)) if frag_vals else 0.0

        report_payload = {
            "database": db_name,
            "instance": instance,
            "server": inst_cfg.get("db_server"),
            "timestamp": _now_utc_iso(),
            "query_store_enabled": top_q.get("query_store_enabled") if isinstance(top_q, dict) else None,
            "kpis": {
                "avg_query_duration_metric": round(avg_query_metric, 2) if isinstance(avg_query_metric, (int, float)) else None,
                "max_query_duration_metric": max_query_metric,
                "fragmentation_avg_percent": round(avg_frag, 2),
                "fragmentation_high_count_ge_30": len([v for v in frag_vals if v >= 30]),
                "fragmentation_medium_count_10_29": len([v for v in frag_vals if 10 <= v < 30]),
                "data_size_mb": sec_perf.get("data_size_mb") if isinstance(sec_perf, dict) else None,
                "open_transactions": sec_perf.get("open_transactions") if isinstance(sec_perf, dict) else None,
                "user_count": sec_perf.get("user_count") if isinstance(sec_perf, dict) else None,
            },
            "top_slow_queries": [
                {
                    "query_id": q.get("query_id"),
                    "metric_value": q.get("metric_value"),
                    "count_executions": q.get("count_executions"),
                    "last_execution_time": q.get("last_execution_time"),
                }
                for q in queries[:5]
                if isinstance(q, dict)
            ],
            "top_fragmented_indexes": [
                {
                    "schema_name": r.get("schema_name"),
                    "table_name": r.get("table_name"),
                    "index_name": r.get("index_name"),
                    "avg_fragmentation_in_percent": r.get("avg_fragmentation_in_percent"),
                    "page_count": r.get("page_count"),
                }
                for r in frag_items[:5]
                if isinstance(r, dict)
            ],
        }

        html = _render_performance_dashboard_html(report_payload)
        report_id = uuid.uuid4().hex
        with _REPORT_STORAGE_LOCK:
            _REPORT_STORAGE[report_id] = {
                "html": html,
                "database": db_name,
                "instance": instance,
                "timestamp": report_payload["timestamp"],
                "report_type": "performance-dashboard",
            }
        _persist_report_html(report_id, html)

        return {
            "status": "success",
            "message": f"Performance dashboard webpage generated for database '{db_name}'.",
            "database": db_name,
            "instance": instance,
            "performance_dashboard_url": f"{_public_base_url()}/performance-dashboard?id={report_id}",
            "report_id": report_id,
            "kpis": report_payload["kpis"],
            "url_hint": "Set MCP_PUBLIC_BASE_URL when the server runs behind Docker port mapping or a reverse proxy.",
        }
    except Exception as e:
        logger.error(f"Error in db_sql2019_generate_performance_dashboard: {e}")
        return {"status": "error", "message": str(e)}


def _register_generative_dashboard_tools() -> None:
    tool_map = {
        "generate_sessions_dashboard": db_sql2019_generate_sessions_dashboard,
        "generate_model_diagram": db_sql2019_generate_model_diagram,
        "generate_performance_dashboard": db_sql2019_generate_performance_dashboard,
    }

    for instance in [1, 2]:
        prefix = "db_01_" if instance == 1 else "db_02_"
        for name, func in tool_map.items():
            tool_name = f"{prefix}{name}"

            def make_wrapper(f, inst, registered_tool_name: str):
                @wraps(f)
                def wrapper(*args, **kwargs):
                    kwargs.pop("instance", None)
                    kwargs["instance"] = inst
                    invocation_id = uuid.uuid4().hex
                    start = time.perf_counter()
                    context = {
                        "instance": inst,
                        "database_name": kwargs.get("database_name") or kwargs.get("database"),
                        "schema": kwargs.get("schema") or kwargs.get("schema_name"),
                        "table_name": kwargs.get("table_name"),
                        "args_keys": sorted(list(kwargs.keys())),
                    }
                    function_name = f.__name__
                    _log_tool_start(registered_tool_name, function_name, invocation_id, context)
                    try:
                        result = f(*args, **kwargs)
                        elapsed_ms = int((time.perf_counter() - start) * 1000)
                        _log_tool_success(registered_tool_name, function_name, invocation_id, elapsed_ms, result)
                        return result
                    except Exception as exc:
                        elapsed_ms = int((time.perf_counter() - start) * 1000)
                        _log_tool_error(registered_tool_name, function_name, invocation_id, elapsed_ms, exc)
                        raise
                return wrapper

            wrapped = make_wrapper(func, instance, tool_name)
            mcp.tool(name=tool_name)(wrapped)

            func_name = getattr(func, "__name__", "")
            alias_name_set: set[str] = set()
            if func_name.startswith("db_sql2019_"):
                suffix = func_name.removeprefix("db_sql2019_")
                alias_name_set.add(f"{prefix}sql2019_{suffix}")
                if instance == 1:
                    alias_name_set.add(func_name)

            alias_name_set.add(f"{prefix}sql2019_{name}")
            if instance == 1:
                alias_name_set.add(f"db_sql2019_{name}")
                alias_name_set.add(f"db_db2019_{name}")
                if func_name.startswith("db_sql2019_"):
                    alias_name_set.add(func_name.replace("db_sql2019_", "db_db2019_", 1))

            for alias_name in sorted(alias_name_set):
                alias_wrapped = make_wrapper(func, instance, alias_name)
                mcp.tool(name=alias_name)(alias_wrapped)


_register_generative_dashboard_tools()


try:
    from starlette.responses import HTMLResponse, JSONResponse

    @mcp.custom_route("/data-model-analysis", methods=["GET"], name="data_model_analysis")
    async def data_model_analysis_handler(request):
        """Handler for /data-model-analysis endpoint."""
        report_id = request.query_params.get("id")
        if not report_id:
            return JSONResponse({"error": "Missing 'id' parameter"}, status_code=400)

        html = _get_report_html(report_id)

        if html is None:
            return JSONResponse({"error": f"Report '{report_id}' not found"}, status_code=404)

        return HTMLResponse(content=html, status_code=200)

    @mcp.custom_route("/performance-dashboard", methods=["GET"], name="performance_dashboard")
    async def performance_dashboard_handler(request):
        """Handler for /performance-dashboard endpoint."""
        report_id = request.query_params.get("id")
        if not report_id:
            return JSONResponse({"error": "Missing 'id' parameter"}, status_code=400)

        html = _get_report_html(report_id)
        if html is None:
            return JSONResponse({"error": f"Report '{report_id}' not found"}, status_code=404)

        return HTMLResponse(content=html, status_code=200)

    @mcp.custom_route("/sessions-monitor", methods=["GET"], name="sessions_monitor")
    async def sessions_monitor_handler(request):
        """Handler for /sessions-monitor endpoint."""
        raw_instance = request.query_params.get("instance", "1")
        try:
            instance = int(raw_instance)
            html = _generate_sessions_monitor_html_for_instance(instance)
            return HTMLResponse(content=html, status_code=200)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except Exception as exc:
            logger.exception("Failed to render sessions monitor for instance=%s", raw_instance)
            return JSONResponse({"error": str(exc)}, status_code=500)

except Exception as e:
    logger.exception("Failed to add web UI routes: %s", e)
    raise


if __name__ == "__main__":
    mcp.run()
