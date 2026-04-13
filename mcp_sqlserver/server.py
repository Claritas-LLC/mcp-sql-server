# --- Helper for normalizing db_name consistently ---
def _normalize_db_name(db_name: str | int | None) -> str | None:
    if db_name is None:
        return None
    if isinstance(db_name, str):
        return db_name
    return str(db_name)
import queue
import psutil
import logging
from logging.handlers import RotatingFileHandler
import os
import pathlib
import re
import json
import time
import base64
import hashlib
import hmac
import uuid
import sys
import functools
import asyncio
from datetime import datetime, timezone
from threading import Lock
from contextvars import ContextVar
from typing import Any, Sequence, Literal, Annotated
from html import escape
from urllib.parse import quote
from functools import lru_cache, wraps
import pyodbc
from fastmcp import FastMCP, Context
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

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

import psutil
import logging
from logging.handlers import RotatingFileHandler
import os
import pathlib
import re
import json
import time
import base64
import hashlib
import hmac
import uuid
import sys
import functools
import asyncio
from datetime import datetime, timezone
from threading import Lock
from contextvars import ContextVar
from typing import Any, Sequence, Literal, Annotated
from html import escape
from urllib.parse import quote
from functools import lru_cache, wraps
import pyodbc
from fastmcp import FastMCP, Context

logger = logging.getLogger("mcp_sqlserver")

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
        self.server_instructions = kwargs.get('server_instructions', '')
        self.server_version = kwargs.get('server_version', '')
        self.list_page_size = kwargs.get('list_page_size', None)
        self.tool_search_enabled = kwargs.get('tool_search_enabled', False)
        self.tool_search_strategy = kwargs.get('tool_search_strategy', 'regex')
        self.tool_search_max_results = kwargs.get('tool_search_max_results', None)
        self.tool_search_always_visible = kwargs.get('tool_search_always_visible', '')
        self.tool_search_tool_name = kwargs.get('tool_search_tool_name', 'search_tools')
        self.tool_call_tool_name = kwargs.get('tool_call_tool_name', 'call_tool')
        self.transform_layers_enabled = kwargs.get('transform_layers_enabled', True)
        self.transform_layer_order = kwargs.get(
            'transform_layer_order',
            'visibility,namespace,tool_transformation,resources_as_tools,prompts_as_tools,code_mode',
        )
        self.transform_visibility_enabled = kwargs.get('transform_visibility_enabled', False)
        self.transform_visibility_allowlist = kwargs.get('transform_visibility_allowlist', '')
        self.transform_visibility_denylist = kwargs.get('transform_visibility_denylist', '')
        self.transform_namespace_enabled = kwargs.get('transform_namespace_enabled', False)
        self.transform_namespace_prefix = kwargs.get('transform_namespace_prefix', '')
        self.transform_tool_transformation_enabled = kwargs.get('transform_tool_transformation_enabled', False)
        self.transform_tool_name_map = kwargs.get('transform_tool_name_map', '{}')
        self.transform_tool_description_map = kwargs.get('transform_tool_description_map', '{}')
        self.transform_resources_as_tools_enabled = kwargs.get('transform_resources_as_tools_enabled', False)
        self.transform_prompts_as_tools_enabled = kwargs.get('transform_prompts_as_tools_enabled', False)
        self.transform_code_mode_enabled = kwargs.get('transform_code_mode_enabled', False)
        self.transform_code_mode_policy = kwargs.get('transform_code_mode_policy', 'safe')

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
from logging.handlers import RotatingFileHandler

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
_AUDIT_LOG_HANDLER_PATH: str | None = None
_AUDIT_LOG_HANDLER_INIT_LOCK = Lock()

def _get_audit_handler():
    global _AUDIT_LOG_HANDLER, _AUDIT_LOG_HANDLER_PATH
    configured_path = (getattr(SETTINGS, "audit_log_file", "") or "").strip() or _audit_log_file
    if _AUDIT_LOG_HANDLER is not None and _AUDIT_LOG_HANDLER_PATH == configured_path:
        return _AUDIT_LOG_HANDLER
    with _AUDIT_LOG_HANDLER_INIT_LOCK:
        configured_path = (getattr(SETTINGS, "audit_log_file", "") or "").strip() or _audit_log_file
        if _AUDIT_LOG_HANDLER is not None and _AUDIT_LOG_HANDLER_PATH == configured_path:
            return _AUDIT_LOG_HANDLER
        if _AUDIT_LOG_HANDLER is not None:
            try:
                _AUDIT_LOG_HANDLER.close()
            except Exception:
                pass
            _AUDIT_LOG_HANDLER = None

        log_path = configured_path
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
        _AUDIT_LOG_HANDLER_PATH = log_path
        return handler


# --- Simple Connection Pool Implementation ---
import queue

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
        get = lambda k, default=None: os.getenv(prefix + k, default)
        # Fallback for instance 1: support legacy DB_*
        if idx == 1:
            get = lambda k, default=None: os.getenv(prefix + k, os.getenv("DB_" + k, default))
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
        server_instructions=_env("MCP_SERVER_INSTRUCTIONS", "").strip(),
        server_version=_env("MCP_SERVER_VERSION", "").strip(),
        list_page_size=_env_optional_int("MCP_LIST_PAGE_SIZE"),
        tool_search_enabled=_env_bool("MCP_TOOL_SEARCH_ENABLED", False),
        tool_search_strategy=_env("MCP_TOOL_SEARCH_STRATEGY", "regex").strip().lower(),
        tool_search_max_results=_env_optional_int("MCP_TOOL_SEARCH_MAX_RESULTS"),
        tool_search_always_visible=_env("MCP_TOOL_SEARCH_ALWAYS_VISIBLE", "").strip(),
        tool_search_tool_name=_env("MCP_TOOL_SEARCH_TOOL_NAME", "search_tools").strip(),
        tool_call_tool_name=_env("MCP_TOOL_CALL_TOOL_NAME", "call_tool").strip(),
        transform_layers_enabled=_env_bool("MCP_TRANSFORM_LAYERS_ENABLED", True),
        transform_layer_order=_env(
            "MCP_TRANSFORM_LAYER_ORDER",
            "visibility,namespace,tool_transformation,resources_as_tools,prompts_as_tools,code_mode",
        ).strip().lower(),
        transform_visibility_enabled=_env_bool("MCP_TRANSFORM_VISIBILITY_ENABLED", False),
        transform_visibility_allowlist=_env("MCP_TRANSFORM_VISIBILITY_ALLOWLIST", "").strip(),
        transform_visibility_denylist=_env("MCP_TRANSFORM_VISIBILITY_DENYLIST", "").strip(),
        transform_namespace_enabled=_env_bool("MCP_TRANSFORM_NAMESPACE_ENABLED", False),
        transform_namespace_prefix=_env("MCP_TRANSFORM_NAMESPACE_PREFIX", "").strip(),
        transform_tool_transformation_enabled=_env_bool("MCP_TRANSFORM_TOOL_TRANSFORMATION_ENABLED", False),
        transform_tool_name_map=_env("MCP_TRANSFORM_TOOL_NAME_MAP", "{}").strip(),
        transform_tool_description_map=_env("MCP_TRANSFORM_TOOL_DESCRIPTION_MAP", "{}").strip(),
        transform_resources_as_tools_enabled=_env_bool("MCP_TRANSFORM_RESOURCES_AS_TOOLS_ENABLED", False),
        transform_prompts_as_tools_enabled=_env_bool("MCP_TRANSFORM_PROMPTS_AS_TOOLS_ENABLED", False),
        transform_code_mode_enabled=_env_bool("MCP_TRANSFORM_CODE_MODE_ENABLED", False),
        transform_code_mode_policy=_env("MCP_TRANSFORM_CODE_MODE_POLICY", "safe").strip().lower(),
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
    )




from typing import Union

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
                cur.execute("SELECT 1")
            except Exception:
                # Connection is dead, replace
                conn.close()
                conn = pyodbc.connect(_connection_string(database, instance), timeout=max(1, SETTINGS.statement_timeout_ms // 1000))
                conn.autocommit = True
        except queue.Empty:
            # Pool exhausted, create new connection (not pooled)
            conn = pyodbc.connect(_connection_string(database, instance), timeout=max(1, SETTINGS.statement_timeout_ms // 1000))
            conn.autocommit = True

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



# FastMCP app initialization
MCP_SERVER_NAME = os.getenv("MCP_SERVER_NAME", "SQL Server MCP Server")


def build_mcp_constructor_config() -> dict[str, Any]:
    config: dict[str, Any] = {"name": MCP_SERVER_NAME}
    if SETTINGS.server_instructions:
        config["instructions"] = SETTINGS.server_instructions
    if SETTINGS.server_version:
        config["version"] = SETTINGS.server_version
    if SETTINGS.list_page_size is not None:
        config["list_page_size"] = SETTINGS.list_page_size
    return config


mcp = FastMCP(**build_mcp_constructor_config())

try:
    import fastmcp
    print(f"\n=== MCP Server Banner ===\n{MCP_SERVER_NAME} | FastMCP version: {fastmcp.__version__}\n========================\n")
except Exception:
    print(f"\n=== MCP Server Banner ===\n{MCP_SERVER_NAME} | FastMCP version: unknown\n========================\n")


_TOOL_SEARCH_TRANSFORM_APPLIED = False
_HEALTH_ROUTE_REGISTERED = False
_PROVIDER_TRANSFORM_LAYERS_APPLIED = False
_DASHBOARD_ROUTES_REGISTERED = False
_LOGICAL_MODEL_REPORTS_LOCK = Lock()
_LOGICAL_MODEL_REPORTS: dict[str, tuple[float, str]] = {}
_LOGICAL_MODEL_REPORT_TTL_SECONDS = max(60, int(os.getenv("MCP_LOGICAL_MODEL_REPORT_TTL_SECONDS", "3600")))
_LOGICAL_MODEL_REPORT_MAX_ITEMS = max(1, int(os.getenv("MCP_LOGICAL_MODEL_REPORT_MAX_ITEMS", "100")))


def _parse_csv_values(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [item.strip() for item in str(raw_value).split(",") if item.strip()]


def _parse_json_mapping(raw_value: str | None, env_name: str) -> dict[str, str]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except Exception as exc:
        logger.warning("Invalid JSON mapping for %s: %s", env_name, exc)
        return {}
    if not isinstance(parsed, dict):
        logger.warning("Invalid JSON mapping for %s: expected object.", env_name)
        return {}
    cleaned: dict[str, str] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        key_clean = key.strip()
        value_clean = value.strip()
        if key_clean and value_clean:
            cleaned[key_clean] = value_clean
    return cleaned


def _instantiate_transform(
    module_name: str,
    class_candidates: Sequence[str],
    kwargs: dict[str, Any],
    layer_name: str,
) -> Any | None:
    try:
        module = __import__(module_name, fromlist=["*"])
    except Exception as exc:
        logger.warning("%s transform unavailable: %s", layer_name, exc)
        return None

    transform_class = None
    for class_name in class_candidates:
        transform_class = getattr(module, class_name, None)
        if transform_class is not None:
            break

    if transform_class is None:
        logger.warning(
            "%s transform unavailable: none of %s found in %s",
            layer_name,
            ", ".join(class_candidates),
            module_name,
        )
        return None

    try:
        return transform_class(**kwargs)
    except TypeError:
        # Graceful fallback for runtimes with narrower constructor signatures.
        try:
            return transform_class()
        except Exception as exc:
            logger.warning("Failed to instantiate %s transform: %s", layer_name, exc)
            return None
    except Exception as exc:
        logger.warning("Failed to instantiate %s transform: %s", layer_name, exc)
        return None


def _configure_visibility_transform() -> Any | None:
    if not bool(getattr(SETTINGS, "transform_visibility_enabled", False)):
        return None
    allowlist = _parse_csv_values(getattr(SETTINGS, "transform_visibility_allowlist", ""))
    denylist = _parse_csv_values(getattr(SETTINGS, "transform_visibility_denylist", ""))
    kwargs: dict[str, Any] = {}
    if allowlist and denylist:
        logger.warning(
            "Visibility transform: both MCP_TRANSFORM_VISIBILITY_ALLOWLIST and "
            "MCP_TRANSFORM_VISIBILITY_DENYLIST are set. Using allowlist only (enabled=True, names=allowlist)."
        )
        kwargs["enabled"] = True
        kwargs["names"] = set(allowlist)
    elif allowlist:
        kwargs["enabled"] = True
        kwargs["names"] = set(allowlist)
    elif denylist:
        kwargs["enabled"] = False
        kwargs["names"] = set(denylist)
    else:
        kwargs["enabled"] = True
        kwargs["match_all"] = True
    return _instantiate_transform(
        "fastmcp.server.transforms.visibility",
        ["Visibility"],
        kwargs,
        "Visibility",
    )


def _configure_namespace_transform() -> Any | None:
    if not bool(getattr(SETTINGS, "transform_namespace_enabled", False)):
        return None
    kwargs: dict[str, Any] = {}
    namespace_prefix = str(getattr(SETTINGS, "transform_namespace_prefix", "") or "").strip()
    if namespace_prefix:
        kwargs["prefix"] = namespace_prefix
    return _instantiate_transform(
        "fastmcp.server.transforms.namespace",
        ["Namespace"],
        kwargs,
        "Namespace",
    )


def _configure_tool_transformation_transform() -> Any | None:
    if not bool(getattr(SETTINGS, "transform_tool_transformation_enabled", False)):
        return None
    name_map = _parse_json_mapping(
        getattr(SETTINGS, "transform_tool_name_map", "{}"),
        "MCP_TRANSFORM_TOOL_NAME_MAP",
    )
    description_map = _parse_json_mapping(
        getattr(SETTINGS, "transform_tool_description_map", "{}"),
        "MCP_TRANSFORM_TOOL_DESCRIPTION_MAP",
    )
    all_tool_names = set(name_map) | set(description_map)
    if not all_tool_names:
        logger.warning(
            "ToolTransformation transform enabled but MCP_TRANSFORM_TOOL_NAME_MAP and "
            "MCP_TRANSFORM_TOOL_DESCRIPTION_MAP are both empty. Skipping."
        )
        return None
    try:
        from fastmcp.server.transforms.tool_transform import ToolTransform, ToolTransformConfig

        transforms_dict: dict[str, Any] = {}
        for tool_name in all_tool_names:
            config_kwargs: dict[str, str] = {}
            if tool_name in name_map:
                config_kwargs["name"] = name_map[tool_name]
            if tool_name in description_map:
                config_kwargs["description"] = description_map[tool_name]
            transforms_dict[tool_name] = ToolTransformConfig(**config_kwargs)
        return ToolTransform(transforms=transforms_dict)
    except Exception as exc:
        logger.warning("ToolTransformation transform unavailable: %s", exc)
        return None


def _configure_resources_as_tools_transform() -> Any | None:
    if not bool(getattr(SETTINGS, "transform_resources_as_tools_enabled", False)):
        return None
    try:
        from fastmcp.server.transforms.resources_as_tools import ResourcesAsTools

        return ResourcesAsTools(mcp)
    except Exception as exc:
        logger.warning("ResourcesAsTools transform unavailable: %s", exc)
        return None


def _configure_prompts_as_tools_transform() -> Any | None:
    if not bool(getattr(SETTINGS, "transform_prompts_as_tools_enabled", False)):
        return None
    try:
        from fastmcp.server.transforms.prompts_as_tools import PromptsAsTools

        return PromptsAsTools(mcp)
    except Exception as exc:
        logger.warning("PromptsAsTools transform unavailable: %s", exc)
        return None


def _configure_code_mode_transform() -> Any | None:
    if not bool(getattr(SETTINGS, "transform_code_mode_enabled", False)):
        return None
    kwargs: dict[str, Any] = {}
    policy = str(getattr(SETTINGS, "transform_code_mode_policy", "safe") or "safe").strip().lower()
    if policy:
        kwargs["policy"] = policy
    return _instantiate_transform(
        "fastmcp.server.transforms.code_mode",
        ["CodeModeTransform", "CodeMode"],
        kwargs,
        "CodeMode",
    )


def _build_provider_transform_layers(settings: Settings | None = None) -> list[dict[str, Any]]:
    effective_settings = settings or SETTINGS
    if not bool(getattr(effective_settings, "transform_layers_enabled", True)):
        return []

    default_order = [
        "visibility",
        "namespace",
        "tool_transformation",
        "resources_as_tools",
        "prompts_as_tools",
        "code_mode",
    ]
    raw_order = _parse_csv_values(getattr(effective_settings, "transform_layer_order", ""))
    known = set(default_order)
    ordered = [item for item in raw_order if item in known]
    unknown = [item for item in raw_order if item not in known]
    if unknown:
        logger.warning(
            "Unknown transform layer names in MCP_TRANSFORM_LAYER_ORDER will be ignored: %s",
            ", ".join(unknown),
        )
    for item in default_order:
        if item not in ordered:
            ordered.append(item)

    layer_specs: dict[str, tuple[bool, Any]] = {
        "visibility": (bool(getattr(effective_settings, "transform_visibility_enabled", False)), _configure_visibility_transform),
        "namespace": (bool(getattr(effective_settings, "transform_namespace_enabled", False)), _configure_namespace_transform),
        "tool_transformation": (
            bool(getattr(effective_settings, "transform_tool_transformation_enabled", False)),
            _configure_tool_transformation_transform,
        ),
        "resources_as_tools": (
            bool(getattr(effective_settings, "transform_resources_as_tools_enabled", False)),
            _configure_resources_as_tools_transform,
        ),
        "prompts_as_tools": (
            bool(getattr(effective_settings, "transform_prompts_as_tools_enabled", False)),
            _configure_prompts_as_tools_transform,
        ),
        "code_mode": (bool(getattr(effective_settings, "transform_code_mode_enabled", False)), _configure_code_mode_transform),
    }

    layers: list[dict[str, Any]] = []
    for name in ordered:
        enabled, factory = layer_specs[name]
        layers.append({"name": name, "enabled": enabled, "factory": factory})
    return layers


def _apply_provider_transform_layers(layers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    global _PROVIDER_TRANSFORM_LAYERS_APPLIED

    if _PROVIDER_TRANSFORM_LAYERS_APPLIED:
        return {"applied": [], "skipped": [], "already_applied": True}

    transform_layers = layers if layers is not None else _build_provider_transform_layers()
    add_transform = getattr(mcp, "add_transform", None)
    if not callable(add_transform):
        logger.warning("Provider transform layering skipped: FastMCP runtime has no add_transform method.")
        return {"applied": [], "skipped": [layer.get("name", "unknown") for layer in transform_layers], "already_applied": False}

    applied: list[str] = []
    skipped: list[str] = []
    for layer in transform_layers:
        layer_name = str(layer.get("name", "unknown"))
        if not bool(layer.get("enabled", False)):
            skipped.append(layer_name)
            continue
        factory = layer.get("factory")
        if not callable(factory):
            skipped.append(layer_name)
            logger.warning("Provider transform layer %s skipped: factory unavailable.", layer_name)
            continue
        transform = factory()
        if transform is None:
            skipped.append(layer_name)
            continue
        try:
            add_transform(transform)
            applied.append(layer_name)
        except Exception as exc:
            skipped.append(layer_name)
            logger.warning("Provider transform layer %s failed to apply: %s", layer_name, exc)

    _PROVIDER_TRANSFORM_LAYERS_APPLIED = True
    logger.info(
        "Provider transform layering resolved. Applied: [%s]. Skipped: [%s].",
        ", ".join(applied) if applied else "none",
        ", ".join(skipped) if skipped else "none",
        extra={
            "applied_layers": applied,
            "skipped_layers": skipped,
        },
    )
    return {"applied": applied, "skipped": skipped, "already_applied": False}


def _configure_tool_search_transform() -> None:
    global _TOOL_SEARCH_TRANSFORM_APPLIED

    if _TOOL_SEARCH_TRANSFORM_APPLIED:
        return

    if not bool(getattr(SETTINGS, "tool_search_enabled", False)):
        logger.info("Tool search transform disabled by MCP_TOOL_SEARCH_ENABLED.")
        return

    strategy = str(getattr(SETTINGS, "tool_search_strategy", "regex") or "regex").strip().lower()
    if strategy not in {"regex", "bm25"}:
        raise RuntimeError("MCP_TOOL_SEARCH_STRATEGY must be 'regex' or 'bm25'.")

    kwargs: dict[str, Any] = {}
    max_results = getattr(SETTINGS, "tool_search_max_results", None)
    if max_results is not None:
        kwargs["max_results"] = max_results

    always_visible_raw = str(getattr(SETTINGS, "tool_search_always_visible", "") or "")
    always_visible = [name.strip() for name in always_visible_raw.split(",") if name.strip()]
    if always_visible:
        kwargs["always_visible"] = always_visible

    search_tool_name = str(getattr(SETTINGS, "tool_search_tool_name", "") or "").strip()
    call_tool_name = str(getattr(SETTINGS, "tool_call_tool_name", "") or "").strip()
    if search_tool_name:
        kwargs["search_tool_name"] = search_tool_name
    if call_tool_name:
        kwargs["call_tool_name"] = call_tool_name

    try:
        if strategy == "bm25":
            from fastmcp.server.transforms.search import BM25SearchTransform as SearchTransform
        else:
            from fastmcp.server.transforms.search import RegexSearchTransform as SearchTransform
    except Exception as exc:
        logger.warning(
            "Tool search transform requested but unavailable in current FastMCP runtime: %s",
            exc,
        )
        return

    try:
        transform = SearchTransform(**kwargs)
        add_transform = getattr(mcp, "add_transform", None)
        if callable(add_transform):
            add_transform(transform)
            _TOOL_SEARCH_TRANSFORM_APPLIED = True
            logger.info("Tool search transform applied.", extra={"strategy": strategy})
            return

        logger.warning("Tool search transform could not be applied: FastMCP runtime has no add_transform method.")
    except Exception as exc:
        logger.warning("Failed to apply tool search transform: %s", exc)


def _register_health_route() -> None:
    global _HEALTH_ROUTE_REGISTERED
    if _HEALTH_ROUTE_REGISTERED:
        return

    custom_route: Any = getattr(mcp, "custom_route", None)
    if not callable(custom_route):
        logger.warning("Health route registration skipped: FastMCP runtime has no custom_route API.")
        return

    async def _health_route(_request: Any) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "service": MCP_SERVER_NAME,
                "transport": str(getattr(SETTINGS, "transport", "http") or "http").lower(),
            }
        )

    route_decorator: Any = custom_route(path="/health", methods=["GET"], name="health")
    route_decorator(_health_route)

    _HEALTH_ROUTE_REGISTERED = True


def _resolve_public_base_url() -> str:
    configured = str(getattr(SETTINGS, "public_base_url", "") or "").strip()
    if configured:
        return configured.rstrip("/")
    host = str(getattr(SETTINGS, "host", "localhost") or "localhost").strip()
    if host in {"0.0.0.0", "::"}:
        host = "localhost"
    port = int(getattr(SETTINGS, "port", 8000) or 8000)
    return f"http://{host}:{port}"


def _parse_instance_from_request(request: Any, default: int = 1) -> int:
    raw = str(getattr(request, "query_params", {}).get("instance", "") or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except Exception as exc:
        raise ValueError("instance must be an integer (1 or 2).") from exc
    if value not in {1, 2}:
        raise ValueError("instance must be 1 or 2.")
    return value


def _collect_session_monitor_stats(instance: int = 1) -> dict[str, Any]:
    if instance not in SETTINGS.db_instances:
        return {
            "status": "unavailable",
            "reason": f"Instance {instance} is not configured.",
            "timestamp": _now_utc_iso(),
        }

    conn = get_connection("master", instance=instance)
    try:
        cur = conn.cursor()
        _execute_safe(
            cur,
            """
            SELECT
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS active_sessions,
                SUM(CASE WHEN status <> 'running' THEN 1 ELSE 0 END) AS idle_sessions,
                COUNT(*) AS total_sessions
            FROM sys.dm_exec_sessions
            WHERE is_user_process = 1 AND session_id <> @@SPID
            """,
        )
        row = cur.fetchone()
        active = int(row[0]) if row and row[0] is not None else 0
        idle = int(row[1]) if row and row[1] is not None else 0
        total = int(row[2]) if row and row[2] is not None else 0
        return {
            "status": "ok",
            "instance": instance,
            "active_sessions": active,
            "idle_sessions": idle,
            "total_sessions": total,
            "timestamp": _now_utc_iso(),
        }
    finally:
        conn.close()


def _prune_logical_model_reports() -> None:
    now = time.time()
    with _LOGICAL_MODEL_REPORTS_LOCK:
        expired_ids = [
            report_id
            for report_id, (created_at, _html) in _LOGICAL_MODEL_REPORTS.items()
            if (now - created_at) > _LOGICAL_MODEL_REPORT_TTL_SECONDS
        ]
        for report_id in expired_ids:
            _LOGICAL_MODEL_REPORTS.pop(report_id, None)

        if len(_LOGICAL_MODEL_REPORTS) <= _LOGICAL_MODEL_REPORT_MAX_ITEMS:
            return

        # Keep newest reports when max capacity is exceeded.
        sorted_reports = sorted(_LOGICAL_MODEL_REPORTS.items(), key=lambda item: item[1][0], reverse=True)
        keep_ids = {report_id for report_id, _ in sorted_reports[:_LOGICAL_MODEL_REPORT_MAX_ITEMS]}
        for report_id in list(_LOGICAL_MODEL_REPORTS.keys()):
            if report_id not in keep_ids:
                _LOGICAL_MODEL_REPORTS.pop(report_id, None)


def _logical_model_report_stats() -> dict[str, Any]:
    _prune_logical_model_reports()
    now = time.time()
    with _LOGICAL_MODEL_REPORTS_LOCK:
        timestamps = [created_at for created_at, _html in _LOGICAL_MODEL_REPORTS.values()]

    if not timestamps:
        return {
            "count": 0,
            "oldest_age_seconds": 0,
            "newest_age_seconds": 0,
            "ttl_seconds": _LOGICAL_MODEL_REPORT_TTL_SECONDS,
            "max_items": _LOGICAL_MODEL_REPORT_MAX_ITEMS,
        }

    oldest = min(timestamps)
    newest = max(timestamps)
    return {
        "count": len(timestamps),
        "oldest_age_seconds": int(max(0.0, now - oldest)),
        "newest_age_seconds": int(max(0.0, now - newest)),
        "ttl_seconds": _LOGICAL_MODEL_REPORT_TTL_SECONDS,
        "max_items": _LOGICAL_MODEL_REPORT_MAX_ITEMS,
    }


def _register_dashboard_routes() -> None:
    global _DASHBOARD_ROUTES_REGISTERED
    if _DASHBOARD_ROUTES_REGISTERED:
        return

    custom_route: Any = getattr(mcp, "custom_route", None)
    if not callable(custom_route):
        logger.warning("Dashboard route registration skipped: FastMCP runtime has no custom_route API.")
        return

    sessions_monitor_html = """
    <html>
    <head>
      <title>SQL Session Monitor</title>
      <style>
        body { font-family: Arial, sans-serif; margin: 24px; }
        .card { border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
        .muted { color: #666; }
      </style>
    </head>
    <body>
      <h1>Session Monitor</h1>
      <p class="muted">Auto-refresh every 5 seconds.</p>
      <div class="card">
        Instance:
        <select id="instance" onchange="refresh()">
          <option value="1">Instance 1</option>
          <option value="2">Instance 2</option>
        </select>
      </div>
      <div class="card">Active sessions: <b id="active">-</b></div>
      <div class="card">Idle sessions: <b id="idle">-</b></div>
      <div class="card">Total sessions: <b id="total">-</b></div>
      <div class="card">Status: <b id="status">-</b></div>
      <div class="card muted">Last updated: <span id="updated">-</span></div>
      <script>
        const params = new URLSearchParams(window.location.search);
        const initialInstance = params.get('instance');
        if (initialInstance === '1' || initialInstance === '2') {
          document.getElementById('instance').value = initialInstance;
        }
        async function refresh() {
          const instance = document.getElementById('instance').value;
          const next = new URL(window.location.href);
          next.searchParams.set('instance', instance);
          window.history.replaceState({}, '', next.toString());
          try {
            const res = await fetch('/sessions-monitor/data?instance=' + encodeURIComponent(instance));
            const data = await res.json();
            document.getElementById('active').textContent = data.active_sessions ?? '-';
            document.getElementById('idle').textContent = data.idle_sessions ?? '-';
            document.getElementById('total').textContent = data.total_sessions ?? '-';
            document.getElementById('status').textContent = data.status ?? '-';
            document.getElementById('updated').textContent = data.timestamp ?? '-';
          } catch (e) {
            document.getElementById('updated').textContent = 'Error loading data';
          }
        }
        refresh();
        setInterval(refresh, 5000);
      </script>
    </body>
    </html>
    """

    async def _sessions_monitor_page(_request: Any) -> HTMLResponse:
        return HTMLResponse(sessions_monitor_html)

    async def _sessions_monitor_data(request: Any) -> JSONResponse:
        try:
            instance = _parse_instance_from_request(request, default=1)
        except ValueError as exc:
            return JSONResponse({"status": "error", "reason": str(exc)}, status_code=400)
        return JSONResponse(_collect_session_monitor_stats(instance=instance))

    async def _data_model_analysis_page(request: Any) -> HTMLResponse:
        _prune_logical_model_reports()
        report_id = str(getattr(request, "query_params", {}).get("id", "") or "").strip()
        if not report_id:
            form_html = """
            <html>
            <head><title>Logical Data Model</title></head>
            <body style="font-family: Arial, sans-serif; margin: 24px;">
              <h1>Generate Logical Data Model</h1>
              <form method="get" action="/data-model-analysis/generate">
                <label>Instance:
                  <select name="instance">
                    <option value="1">Instance 1</option>
                    <option value="2">Instance 2</option>
                  </select>
                </label>
                <br/><br/>
                <label>Database name: <input type="text" name="database_name" /></label>
                <br/><br/>
                <label>Schema (optional): <input type="text" name="schema" /></label>
                <br/><br/>
                <button type="submit">Generate Report</button>
              </form>
            </body>
            </html>
            """
            return HTMLResponse(form_html)
        with _LOGICAL_MODEL_REPORTS_LOCK:
            item = _LOGICAL_MODEL_REPORTS.get(report_id)
        html = item[1] if item else None
        if not html:
            return HTMLResponse(
                "<html><body><h2>Report not found</h2><p>Use open logical model tool for instance 1 or 2, or generate from /data-model-analysis.</p></body></html>",
                status_code=404,
            )
        return HTMLResponse(html)

    async def _data_model_analysis_generate(request: Any) -> JSONResponse | RedirectResponse:
        try:
            instance = _parse_instance_from_request(request, default=1)
        except ValueError as exc:
            return JSONResponse({"status": "error", "reason": str(exc)}, status_code=400)

        database_name = str(getattr(request, "query_params", {}).get("database_name", "") or "").strip() or None
        schema = str(getattr(request, "query_params", {}).get("schema", "") or "").strip() or None

        try:
            report_url = _db_sql2019_open_logical_model_internal(
                instance=instance,
                database_name=database_name,
                schema=schema,
            )
            return RedirectResponse(url=report_url, status_code=302)
        except Exception as exc:
            return JSONResponse({"status": "error", "reason": str(exc)}, status_code=500)

    async def _data_model_analysis_stats(_request: Any) -> JSONResponse:
        return JSONResponse(_logical_model_report_stats())

    custom_route(path="/sessions-monitor", methods=["GET"], name="sessions-monitor")(_sessions_monitor_page)
    custom_route(path="/sessions-monitor/data", methods=["GET"], name="sessions-monitor-data")(_sessions_monitor_data)
    custom_route(path="/data-model-analysis", methods=["GET"], name="data-model-analysis")(_data_model_analysis_page)
    custom_route(path="/data-model-analysis/generate", methods=["GET"], name="data-model-analysis-generate")(_data_model_analysis_generate)
    custom_route(path="/data-model-analysis/stats", methods=["GET"], name="data-model-analysis-stats")(_data_model_analysis_stats)
    _DASHBOARD_ROUTES_REGISTERED = True

def _resolve_http_app() -> Any | None:
    transport = str(getattr(SETTINGS, "transport", "http") or "http").lower()
    if transport != "http":
        return None

    _register_health_route()
    _register_dashboard_routes()

    http_app_factory = getattr(mcp, "http_app", None)
    if not callable(http_app_factory):
        logger.warning("HTTP app resolution skipped: FastMCP runtime has no http_app API.")
        return None

    try:
        return http_app_factory(path="/mcp", transport="http")
    except TypeError:
        return http_app_factory(path="/mcp")




@mcp.tool(name="db_01_ping", description="Basic connectivity probe for database instance 1.")
def db_01_ping() -> dict[str, Any]:
    return _db_sql2019_ping_internal(instance=1)

@mcp.tool(name="db_02_ping", description="Basic connectivity probe for database instance 2.")
def db_02_ping() -> dict[str, Any]:
    return _db_sql2019_ping_internal(instance=2)


# Place after get_instance_config
def _db_sql2019_ping_internal(instance: int = 1) -> dict[str, Any]:
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



@mcp.tool(name="db_01_list_databases", description="List online databases visible to the current login for instance 1.")
def db_01_list_databases(
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE
) -> dict[str, Any]:
    return _db_sql2019_list_databases_internal(instance=1, page=page, page_size=page_size)

@mcp.tool(name="db_02_list_databases", description="List online databases visible to the current login for instance 2.")
def db_02_list_databases(
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE
) -> dict[str, Any]:
    return _db_sql2019_list_databases_internal(instance=2, page=page, page_size=page_size)

def _db_sql2019_list_databases_internal(instance: int = 1, page: int = 1, page_size: int = DEFAULT_TOOL_PAGE_SIZE) -> dict[str, Any]:
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


@mcp.tool(name="db_01_list_tables", description="List tables for a database/schema for instance 1.")
def db_01_list_tables(
    database_name: str | None = None,
    schema_name: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_list_tables_internal(
        instance=1,
        database_name=database_name,
        schema_name=schema_name,
        page=page,
        page_size=page_size,
    )

@mcp.tool(name="db_02_list_tables", description="List tables for a database/schema for instance 2.")
def db_02_list_tables(
    database_name: str | None = None,
    schema_name: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_list_tables_internal(
        instance=2,
        database_name=database_name,
        schema_name=schema_name,
        page=page,
        page_size=page_size,
    )


def _db_sql2019_list_tables_internal(
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
    params: list[Any] | dict[str, Any] | None = None,
    params_json: str | None = None,
    max_rows: int | None = None,
    enforce_readonly: bool = True,
    tool_name: str = "db_sql2019_run_query",
    prompt_context: str | None = None,
) -> list[dict[str, Any]]:
    validate_instance(instance)
    if enforce_readonly and not SETTINGS.allow_write:
        _require_readonly(sql)
    _enforce_table_scope_for_sql(sql)
    
    db_name = database_name or get_instance_config(instance)["db_name"]

    db_name_str = _normalize_db_name(db_name)
    # Ensure database_name is str for audit record (never None)
    audit_db_name = db_name_str if db_name_str is not None else ""
    if params is not None:
        if isinstance(params, dict):
            resolved_params: list[Any] | None = [params]
        elif isinstance(params, list):
            resolved_params = params
        else:
            raise ValueError("params must be a list or object")
    else:
        resolved_params = _parse_params_json(params_json)

    audit_params_json: str | None = None
    if resolved_params is not None:
        audit_params_json = json.dumps(resolved_params, default=str)

    _write_query_audit_record(
        tool_name=tool_name,
        database_name=audit_db_name,
        sql=sql,
        params_json=audit_params_json,
        prompt_context=prompt_context,
    )

    row_cap = max_rows if isinstance(max_rows, int) and max_rows > 0 else SETTINGS.max_rows

    conn = get_connection(db_name_str, instance=instance)
    try:
        cur = conn.cursor()
        _execute_safe(cur, sql, resolved_params)
        rows = _fetch_limited(cur, row_cap)
        return _rows_to_dicts(cur, rows)
    finally:
        conn.close()


def _db_sql2019_execute_query_internal(
    instance: int = 1,
    database_name: str | None = None,
    sql: str | None = None,
    params: list[Any] | dict[str, Any] | None = None,
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
        params=params,
        params_json=params_json,
        max_rows=max_rows,
        enforce_readonly=True,
        tool_name="db_sql2019_execute_query",
        prompt_context=prompt_context,
    )
    return _paginate_tool_result(rows, page=page, page_size=page_size)


@mcp.tool(name="db_01_execute_query", description="Execute a read-only SQL query for instance 1.")
def db_01_execute_query(
    database_name: str | None = None,
    sql: str | None = None,
    params_json: str | None = None,
    max_rows: int | None = None,
    prompt_context: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_execute_query_internal(
        instance=1,
        database_name=database_name,
        sql=sql,
        params_json=params_json,
        max_rows=max_rows,
        prompt_context=prompt_context,
        page=page,
        page_size=page_size,
    )

@mcp.tool(name="db_02_execute_query", description="Execute a read-only SQL query for instance 2.")
def db_02_execute_query(
    database_name: str | None = None,
    sql: str | None = None,
    params_json: str | None = None,
    max_rows: int | None = None,
    prompt_context: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_execute_query_internal(
        instance=2,
        database_name=database_name,
        sql=sql,
        params_json=params_json,
        max_rows=max_rows,
        prompt_context=prompt_context,
        page=page,
        page_size=page_size,
    )


@mcp.tool(name="db_01_run_query", description="Execute SQL query (read-only) for instance 1.")
def db_01_run_query(
    database_name: str | None = None,
    sql: str | None = None,
    params_json: str | None = None,
    max_rows: int | None = None,
    prompt_context: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    # The function signature was updated to align with db_sql2019_execute_query's new signature.
    # For backward compatibility with legacy arg1/arg2 usage, we map to database_name and sql.
    return _db_sql2019_run_query_internal(
        instance=1,
        arg1=database_name,
        arg2=sql,
        params_json=params_json,
        max_rows=max_rows,
        prompt_context=prompt_context,
        page=page,
        page_size=page_size,
    )

@mcp.tool(name="db_02_run_query", description="Execute SQL query (read-only) for instance 2.")
def db_02_run_query(
    database_name: str | None = None,
    sql: str | None = None,
    params_json: str | None = None,
    max_rows: int | None = None,
    prompt_context: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    # The function signature was updated to align with db_sql2019_execute_query's new signature.
    # For backward compatibility with legacy arg1/arg2 usage, we map to database_name and sql.
    return _db_sql2019_run_query_internal(
        instance=2,
        arg1=database_name,
        arg2=sql,
        params_json=params_json,
        max_rows=max_rows,
        prompt_context=prompt_context,
        page=page,
        page_size=page_size,
    )


def _db_sql2019_run_query_internal(
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


@mcp.tool(name="db_01_list_objects", description="List objects (tables, views, etc.) for instance 1.")
def db_01_list_objects(
    database_name: str | None = None,
    object_type: str = "TABLE",
    object_name: str | None = None,
    schema: str | None = None,
    order_by: str | None = None,
    limit: int = 50,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_list_objects_internal(
        instance=1,
        database_name=database_name,
        object_type=object_type,
        object_name=object_name,
        schema=schema,
        order_by=order_by,
        limit=limit,
        page=page,
        page_size=page_size,
    )

@mcp.tool(name="db_02_list_objects", description="List objects (tables, views, etc.) for instance 2.")
def db_02_list_objects(
    database_name: str | None = None,
    object_type: str = "TABLE",
    object_name: str | None = None,
    schema: str | None = None,
    order_by: str | None = None,
    limit: int = 50,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_list_objects_internal(
        instance=2,
        database_name=database_name,
        object_type=object_type,
        object_name=object_name,
        schema=schema,
        order_by=order_by,
        limit=limit,
        page=page,
        page_size=page_size,
    )


def _db_sql2019_list_objects_internal(
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
    recommendations: list[dict[str, Any]] = []
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
        sql = f"""
        SELECT TOP (?)
            s.name AS schema_name,
            t.name AS table_name,
            i.name AS index_name,
            ips.avg_fragmentation_in_percent,
            ips.page_count,
            i.type_desc AS index_type
        FROM sys.dm_db_index_physical_stats(DB_ID('{db_name}'), NULL, NULL, NULL, 'SAMPLED') ips
        JOIN [{db_name}].sys.indexes i
            ON ips.object_id = i.object_id AND ips.index_id = i.index_id
        JOIN [{db_name}].sys.tables t ON i.object_id = t.object_id
        JOIN [{db_name}].sys.schemas s ON t.schema_id = s.schema_id
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


def _db_sql2019_analyze_table_health_internal(
    database_name: str,
    table_name: str,
    instance: int = 1,
    schema: str | None = None,
    view: Literal["summary", "standard", "full"] = "standard",
    fields: str | None = None,
    token_budget: int | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Table-level storage/index/stats/constraint analysis."""
    if not table_name:
        raise ValueError("table_name is required")
    if not schema:
        schema = "dbo"  # Default to dbo schema if not provided
    validate_instance(instance)
    _enforce_table_scope_for_ident(schema, table_name)
    db_name = _normalize_db_name(database_name) if database_name else get_instance_config(instance)["db_name"]
    db_name_str = _normalize_db_name(db_name)
    conn = get_connection(db_name_str, instance=instance)
    recommendations: list[dict[str, Any]] = []
    try:
        cur = conn.cursor()
        # Table info
        _execute_safe(
            cur,
            f"""
            SELECT
                t.name AS TableName,
                s.name AS SchemaName,
                SUM(p.rows) AS RowCounts,
                SUM(a.total_pages) * 8 AS TotalSpaceKB,
                SUM(a.used_pages) * 8 AS UsedSpaceKB,
                (SUM(a.total_pages) - SUM(a.used_pages)) * 8 AS UnusedSpaceKB
            FROM [{db_name}].sys.tables t
            JOIN [{db_name}].sys.schemas s ON t.schema_id = s.schema_id
            JOIN [{db_name}].sys.indexes i ON t.object_id = i.object_id
            JOIN [{db_name}].sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
            JOIN [{db_name}].sys.allocation_units a ON p.partition_id = a.container_id
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
            f"""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH, COLUMN_DEFAULT, NUMERIC_PRECISION, NUMERIC_SCALE
            FROM [{db_name}].INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
            """,
            [schema, table_name],
        )
        columns = _rows_to_dicts(cur, cur.fetchall())

        # Indexes
        _execute_safe(
            cur,
            f"""
            SELECT i.name AS IndexName, i.type_desc AS IndexType,
                   CAST(SUM(a.used_pages) * 8.0 / 1024 AS DECIMAL(18, 4)) AS IndexSizeMB,
                   i.is_disabled
            FROM [{db_name}].sys.indexes i
            JOIN [{db_name}].sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
            JOIN [{db_name}].sys.allocation_units a ON p.partition_id = a.container_id
            JOIN [{db_name}].sys.tables t ON i.object_id = t.object_id
            JOIN [{db_name}].sys.schemas s ON t.schema_id = s.schema_id
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
            f"""
            SELECT tc.CONSTRAINT_NAME, tc.CONSTRAINT_TYPE, kcu.COLUMN_NAME
            FROM [{db_name}].INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            LEFT JOIN [{db_name}].INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
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
            f"""
            SELECT
                fk.name AS FK_Name,
                OBJECT_NAME(fk.parent_object_id) AS ParentTable,
                pc.name AS ParentColumn,
                OBJECT_NAME(fk.referenced_object_id) AS ReferencedTable,
                rc.name AS ReferencedColumn
            FROM [{db_name}].sys.foreign_keys fk
            JOIN [{db_name}].sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
            JOIN [{db_name}].sys.columns pc ON fkc.parent_object_id = pc.object_id AND fkc.parent_column_id = pc.column_id
            JOIN [{db_name}].sys.columns rc ON fkc.referenced_object_id = rc.object_id AND fkc.referenced_column_id = rc.column_id
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
            f"""
            SELECT TOP 25
                c.name AS ColumnName,
                st.name AS StatsName,
                sp.last_updated,
                sp.rows,
                sp.rows_sampled,
                sp.modification_counter
            FROM [{db_name}].sys.stats st
            JOIN [{db_name}].sys.stats_columns sc ON st.object_id = sc.object_id AND st.stats_id = sc.stats_id
            JOIN [{db_name}].sys.columns c ON sc.object_id = c.object_id AND sc.column_id = c.column_id
            OUTER APPLY [{db_name}].sys.dm_db_stats_properties(st.object_id, st.stats_id) sp
            JOIN [{db_name}].sys.tables t ON st.object_id = t.object_id
            JOIN [{db_name}].sys.schemas s ON t.schema_id = s.schema_id
            WHERE s.name = ? AND t.name = ?
            ORDER BY st.name
            """,
            [schema, table_name],
        )
        statistics_sample = _rows_to_dicts(cur, cur.fetchall())

        # Fragmentation checks
        # Ensure db_name is always a string for _get_index_fragmentation_data
        norm_db_name = _normalize_db_name(db_name)
        fragmentation_data = _get_index_fragmentation_data(
            instance=instance, database_name=norm_db_name, schema=schema, min_fragmentation=5.0
        )
        index_issues: list[dict[str, Any]] = []
        for frag in fragmentation_data:
            if frag.get("table_name") == table_name:
                frag_percent = frag.get("avg_fragmentation_in_percent", 0.0) or 0.0
                index_name = frag.get("index_name")
                issue = {
                    "type": "Index Fragmentation",
                    "index_name": index_name,
                    "fragmentation_percent": frag_percent,
                }
                if frag_percent > 30.0:
                    issue["severity"] = "High"
                    issue["message"] = f"Index '{index_name}' is highly fragmented ({frag_percent:.2f}%) and should be rebuilt."
                    recommendations.append(
                        {
                            "severity": "High",
                            "recommendation": f"Rebuild index '{index_name}' to improve performance.",
                            "action": f"ALTER INDEX '{index_name}' ON [{schema}].[{table_name}] REBUILD;",
                        }
                    )
                elif frag_percent > 10.0:
                    issue["severity"] = "Medium"
                    issue["message"] = f"Index '{index_name}' is moderately fragmented ({frag_percent:.2f}%). Consider reorganizing."
                    recommendations.append(
                        {
                            "severity": "Medium",
                            "recommendation": f"Reorganize index '{index_name}' to improve performance.",
                            "action": f"ALTER INDEX '{index_name}' ON [{schema}].[{table_name}] REORGANIZE;",
                        }
                    )
                index_issues.append(issue)

        # Stale statistics checks
        for stat in statistics_sample:
            mod_counter = stat.get("modification_counter", 0) or 0
            stats_name = stat.get("StatsName")
            # row_count will be set below for column checks
            if table_info.get("RowCounts", 0) > 500 and mod_counter > (table_info.get("RowCounts", 0) * 0.1):  # 10% change
                recommendations.append(
                    {
                        "severity": "Medium",
                        "recommendation": f"Statistics '{stats_name}' are stale (approx. {mod_counter} modifications). Update statistics to improve query performance.",
                        "action": f"UPDATE STATISTICS [{schema}].[{table_name}] ('{stats_name}');",
                    }
                )

        # Unused index checks
        _execute_safe(
            cur,
            f"""
            SELECT i.name AS index_name, us.user_seeks, us.user_scans, us.user_lookups, us.user_updates
            FROM [{db_name}].sys.indexes i
            LEFT JOIN [{db_name}].sys.dm_db_index_usage_stats us
              ON us.database_id = DB_ID('{db_name}') AND us.object_id = i.object_id AND us.index_id = i.index_id
            WHERE i.object_id = OBJECT_ID(?)
              AND i.type_desc != 'HEAP'
            """,
            [f"[{db_name}].[{schema}].[{table_name}]"]
        )
        index_usage = _rows_to_dicts(cur, cur.fetchall())
        for usage in index_usage:
            if (usage.get("user_seeks", 0) or 0) == 0 and (usage.get("user_scans", 0) or 0) == 0 and (usage.get("user_lookups", 0) or 0) == 0:
                index_name = usage.get("index_name")
                user_updates = usage.get("user_updates", 0) or 0
                recommendations.append(
                    {
                        "severity": "Low",
                        "recommendation": f"Index '{index_name}' is not being used for reads but is being maintained ({user_updates} updates). Consider dropping this index.",
                        "action": f"DROP INDEX '{index_name}' ON [{schema}].[{table_name}];",
                    }
                )

        # Column cardinality and data type checks
        row_count = table_info.get("RowCounts", 0)
        for col in columns:
            # High cardinality, not indexed
            _execute_safe(cur, f"SELECT COUNT(DISTINCT {_quoted_ident(col['COLUMN_NAME'])}) FROM [{db_name}].[{schema}].[{table_name}]")
            row = cur.fetchone()
            distinct_count = row[0] if row is not None else 0
            if row_count > 0 and (distinct_count / row_count) > 0.8:
                # Check if part of any index
                _execute_safe(cur, f"""
                    SELECT COUNT(*)
                    FROM [{db_name}].sys.index_columns ic
                    JOIN [{db_name}].sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                    WHERE ic.object_id = OBJECT_ID(?)
                      AND c.name = ?
                """, [f"[{db_name}].[{schema}].[{table_name}]", col['COLUMN_NAME']])
                row2 = cur.fetchone()
                in_index_count = row2[0] if row2 is not None else 0
                if in_index_count == 0:
                    recommendations.append(
                        {
                            "severity": "Medium",
                            "recommendation": f"Column '{col['COLUMN_NAME']}' has high cardinality and is not indexed. Consider creating an index to improve performance.",
                            "action": f"CREATE INDEX IX_{table_name}_{col['COLUMN_NAME']} ON [{schema}].[{table_name}] ('{col['COLUMN_NAME']}');",
                        }
                    )

            # Data type checks
            if col.get("DATA_TYPE", "").upper() in ("NVARCHAR", "VARCHAR") and (col.get("CHARACTER_MAXIMUM_LENGTH") is not None and col["CHARACTER_MAXIMUM_LENGTH"] > 255):
                recommendations.append({
                    "severity": "Low",
                    "recommendation": f"Column '{col['COLUMN_NAME']}' is wide ({col['CHARACTER_MAXIMUM_LENGTH']} chars). Consider if max length can be reduced for performance."
                })
            if col.get("DATA_TYPE", "").upper() == "INT" and col.get("IS_NULLABLE", "NO") == "NO":
                _execute_safe(cur, f"SELECT MAX([{col['COLUMN_NAME']}]) FROM [{db_name}].[{schema}].[{table_name}]")
                max_val_row = cur.fetchone()
                if max_val_row and max_val_row[0] is not None:
                    max_val = max_val_row[0]
                    if max_val < 32767:
                        recommendations.append({
                            "severity": "Info",
                            "recommendation": f"Column '{col['COLUMN_NAME']}' is INT but max value is {max_val}. Consider using SMALLINT to save space."
                        })

        # FK index checks
        _execute_safe(
            cur,
            f"""
            SELECT
                fk.name AS fk_name,
                pc.name AS column_name,
                CASE WHEN ix.index_id IS NULL THEN 1 ELSE 0 END AS missing_index
            FROM [{db_name}].sys.foreign_keys fk
            JOIN [{db_name}].sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
            JOIN [{db_name}].sys.columns pc ON fkc.parent_object_id = pc.object_id AND fkc.parent_column_id = pc.column_id
            LEFT JOIN [{db_name}].sys.index_columns ic
              ON ic.object_id = fkc.parent_object_id AND ic.column_id = fkc.parent_column_id AND ic.key_ordinal = 1
            LEFT JOIN [{db_name}].sys.indexes ix
              ON ix.object_id = ic.object_id AND ix.index_id = ic.index_id
            WHERE OBJECT_SCHEMA_NAME(fk.parent_object_id) = ?
              AND OBJECT_NAME(fk.parent_object_id) = ?
            """,
            [schema, table_name],
        )
        fk_index_checks = _rows_to_dicts(cur, cur.fetchall())

        constraint_issues: list[dict[str, Any]] = []
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

        # Missing index checks
        _execute_safe(
            cur,
            f"""
            SELECT
                mig.index_group_handle,
                mid.object_id,
                mid.database_id,
                mid.equality_columns,
                mid.inequality_columns,
                mid.included_columns,
                migs.unique_compiles,
                migs.user_seeks,
                migs.user_scans,
                migs.last_user_seek,
                migs.avg_total_user_cost,
                migs.avg_user_impact
            FROM [{db_name}].sys.dm_db_missing_index_groups mig
            INNER JOIN [{db_name}].sys.dm_db_missing_index_details mid ON mig.index_handle = mid.index_handle
            INNER JOIN [{db_name}].sys.dm_db_missing_index_group_stats migs ON mig.index_group_handle = migs.group_handle
            WHERE mid.object_id = OBJECT_ID(N'[{db_name}].[{schema}].[{table_name}]')
            ORDER BY migs.avg_total_user_cost * migs.avg_user_impact DESC;
            """,
        )
        missing_indexes = _rows_to_dicts(cur, cur.fetchall())

        for mi in missing_indexes:
            columns_str = ""
            if mi["equality_columns"]:
                columns_str += mi["equality_columns"]
            if mi["inequality_columns"]:
                if columns_str:
                    columns_str += ", "
                columns_str += mi["inequality_columns"]
            
            include_str = ""
            if mi["included_columns"]:
                include_str = f" INCLUDE ({mi['included_columns']})"

            if columns_str:
                recommendations.append({
                    "severity": "High",
                    "recommendation": (
                        f"Consider creating a missing index on columns ({columns_str}){include_str} "
                        f"for an estimated impact of {mi['avg_user_impact']:.2f}."
                    ),
                    "action": f"CREATE INDEX IX_Missing_{table_name}_{mi['index_group_handle']} "
                              f"ON [{schema}].[{table_name}] ({columns_str}){include_str};"
                })

        # Redundant index checks
        _execute_safe(
            cur,
            f"""
            SELECT
                RedundantIndex.name AS RedundantIndexName,
                CoveringIndex.name AS CoveringIndexName
            FROM
                [{db_name}].sys.indexes AS RedundantIndex
            INNER JOIN
                [{db_name}].sys.tables AS t ON RedundantIndex.object_id = t.object_id
            INNER JOIN
                [{db_name}].sys.schemas AS s ON t.schema_id = s.schema_id
            INNER JOIN
                [{db_name}].sys.indexes AS CoveringIndex ON RedundantIndex.object_id = CoveringIndex.object_id
            WHERE
                t.object_id = OBJECT_ID(N'[{db_name}].[{schema}].[{table_name}]')
                AND RedundantIndex.index_id > 1 -- Only non-clustered indexes
                AND CoveringIndex.index_id > 0 -- Clustered or non-clustered
                AND RedundantIndex.index_id <> CoveringIndex.index_id
                AND s.name = ?
                AND t.name = ?
                -- Check if RedundantIndex's key columns are a leading subset of CoveringIndex's key columns
                AND NOT EXISTS (
                    -- Check if there is any key column in RedundantIndex that is NOT a matching leading key column in CoveringIndex
                    SELECT 1
                    FROM [{db_name}].sys.index_columns AS ric
                    WHERE
                        ric.object_id = RedundantIndex.object_id
                        AND ric.index_id = RedundantIndex.index_id
                        AND ric.is_included_column = 0 -- Only key columns
                        AND NOT EXISTS (
                            SELECT 1
                            FROM [{db_name}].sys.index_columns AS cic
                            WHERE
                                cic.object_id = CoveringIndex.object_id
                                AND cic.index_id = CoveringIndex.index_id
                                AND cic.is_included_column = 0 -- Only key columns
                                AND cic.column_id = ric.column_id
                                AND cic.key_ordinal = ric.key_ordinal
                        )
                )
                -- Additionally, ensure that the number of key columns in RedundantIndex is less than or equal to CoveringIndex
                AND (
                    SELECT COUNT(*)
                    FROM [{db_name}].sys.index_columns AS ric
                    WHERE
                        ric.object_id = RedundantIndex.object_id
                        AND ric.index_id = RedundantIndex.index_id
                        AND ric.is_included_column = 0
                ) <= (
                    SELECT COUNT(*)
                    FROM [{db_name}].sys.index_columns AS cic
                    WHERE
                        cic.object_id = CoveringIndex.object_id
                        AND cic.index_id = CoveringIndex.index_id
                        AND cic.is_included_column = 0
                )
                -- Check if all included columns of RedundantIndex are also included in CoveringIndex (either as key or included)
                AND NOT EXISTS (
                    SELECT 1
                    FROM
                        [{db_name}].sys.index_columns AS ic_redundant_included
                    WHERE
                        ic_redundant_included.object_id = RedundantIndex.object_id
                        AND ic_redundant_included.index_id = RedundantIndex.index_id
                        AND ic_redundant_included.is_included_column = 1
                        AND NOT EXISTS (
                            SELECT 1
                            FROM
                                [{db_name}].sys.index_columns AS ic_covering_all
                            WHERE
                                ic_covering_all.object_id = CoveringIndex.object_id
                                AND ic_covering_all.index_id = CoveringIndex.index_id
                                AND ic_covering_all.column_id = ic_redundant_included.column_id
                                AND (ic_covering_all.is_included_column = 1 OR ic_covering_all.key_ordinal > 0)
                        )
                )
            ;""",
            [schema, table_name],
        )
        redundant_indexes = _rows_to_dicts(cur, cur.fetchall())

        for ri in redundant_indexes:
            recommendations.append({
                "severity": "Medium",
                "recommendation": f"Index '{ri["RedundantIndexName"]}' might be redundant as its columns are covered by index '{ri["CoveringIndexName"]}'. Consider dropping '{ri["RedundantIndexName"]}'.",
                "action": f"DROP INDEX [{ri["RedundantIndexName"]}] ON [{schema}].[{table_name}];"
            })

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
                "index_issues": index_issues,
            },
            "recommendations": recommendations,
        }
        shaped = _apply_table_health_view(result, view)
        budgeted = _apply_token_budget(shaped, token_budget)
        projected = _apply_field_projection(budgeted, fields)
        return _paginate_tool_result(projected, page=page, page_size=page_size)
    finally:
        conn.close()


@mcp.tool(name="db_01_sql2019_analyze_table_health", description="Table-level storage/index/stats/constraint analysis for instance 1.")
def db_01_sql2019_analyze_table_health(
    database_name: str,
    table_name: str,
    schema: str | None = None,
    view: Literal["summary", "standard", "full"] = "standard",
    fields: str | None = None,
    token_budget: int | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_analyze_table_health_internal(
        database_name=database_name,
        table_name=table_name,
        instance=1,
        schema=schema,
        view=view,
        fields=fields,
        token_budget=token_budget,
        page=page,
        page_size=page_size,
    )

@mcp.tool(name="db_02_sql2019_analyze_table_health", description="Table-level storage/index/stats/constraint analysis for instance 2.")
def db_02_sql2019_analyze_table_health(
    database_name: str,
    table_name: str,
    schema: str | None = None,
    view: Literal["summary", "standard", "full"] = "standard",
    fields: str | None = None,
    token_budget: int | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_analyze_table_health_internal(
        database_name=database_name,
        table_name=table_name,
        instance=2,
        schema=schema,
        view=view,
        fields=fields,
        token_budget=token_budget,
        page=page,
        page_size=page_size,
    )


def _db_sql2019_db_stats_internal(instance: int = 1, database: str | None = None) -> dict[str, Any]:
    """Database object counts."""
    validate_instance(instance)
    db_name = database or get_instance_config(instance)["db_name"]
    db_name_str = _normalize_db_name(db_name)
    conn = get_connection(db_name_str, instance=instance)
    try:
        cur = conn.cursor()
        _execute_safe(
            cur,
            f"""
            SELECT
                DB_NAME() AS DatabaseName,
                (SELECT COUNT(*) FROM [{db_name}].sys.tables) AS TableCount,
                (SELECT COUNT(*) FROM [{db_name}].sys.views) AS ViewCount,
                (SELECT COUNT(*) FROM [{db_name}].sys.procedures) AS ProcedureCount,
                (SELECT COUNT(*) FROM [{db_name}].sys.indexes WHERE name IS NOT NULL) AS IndexCount,
                (SELECT COUNT(*) FROM [{db_name}].sys.schemas) AS SchemaCount
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


@mcp.tool(name="db_01_db_stats", description="Database object counts for instance 1.")
def db_01_db_stats(
    database: str | None = None,
) -> dict[str, Any]:
    return _db_sql2019_db_stats_internal(
        instance=1,
        database=database,
    )

@mcp.tool(name="db_02_db_stats", description="Database object counts for instance 2.")
def db_02_db_stats(
    database: str | None = None,
) -> dict[str, Any]:
    return _db_sql2019_db_stats_internal(
        instance=2,
        database=database,
    )


def _db_sql2019_server_info_mcp_internal(
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


@mcp.tool(name="db_01_server_info", description="Get SQL Server and MCP runtime information for instance 1.")
def db_01_server_info(
    server: Any = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    return _db_sql2019_server_info_mcp_internal(
        instance=1,
        server=server,
        headers=headers,
    )

@mcp.tool(name="db_02_server_info", description="Get SQL Server and MCP runtime information for instance 2.")
def db_02_server_info(
    server: Any = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    return _db_sql2019_server_info_mcp_internal(
        instance=2,
        server=server,
        headers=headers,
    )


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
    parent_tables = {(r.get("parent_schema"), r.get("parent_table")) for r in relationships}
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
    # Minimal HTML rendering logic for open_logical_model
    html = f"""
    <html>
    <head><style>body {{ font-family: sans-serif; }} .issue {{ color: red; }}</style></head>
    <body>
        <h1>Logical Data Model: {model.get('database')}</h1>
        <h2>Summary</h2>
        <ul>
            <li>Entities: {len(model.get('entities', []))}</li>
            <li>Relationships: {len(model.get('relationships', []))}</li>
        </ul>
        <h2>Issues</h2>
        {_render_issue_list_html(issues)}
    </body>
    </html>
    """
    return html


def _render_issue_list_html(issues: dict[str, list[dict[str, Any]]]) -> str:
    items = []
    for category, list_obj in issues.items():
        for issue in list_obj:
            items.append(f"<li class='issue'><b>[{category.upper()}]</b> {issue.get('issue')} in {issue.get('entity', 'model')}</li>")
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
            FROM [{db_name}].sys.tables t
            JOIN [{db_name}].sys.schemas s ON t.schema_id = s.schema_id
            {where_sql}
            """,
            params,
        )
        tables = cur.fetchall()
        
        entities = []
        for t_schema, t_name in tables:
             _execute_safe(
                 cur,
                 f"""
                 SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                 FROM [{db_name}].INFORMATION_SCHEMA.COLUMNS
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


def _db_sql2019_show_top_queries_internal(
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
        _execute_safe(cur, f"SELECT actual_state_desc FROM [{db_name}].sys.database_query_store_options")
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
                CAST(rs.last_execution_time AS DATETIME2) AS last_execution_time
            FROM [{db_name}].sys.query_store_query q
            JOIN [{db_name}].sys.query_store_query_text qt ON q.query_text_id = qt.query_text_id
            JOIN [{db_name}].sys.query_store_plan p ON q.query_id = p.query_id
            JOIN [{db_name}].sys.query_store_runtime_stats rs ON p.plan_id = rs.plan_id
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
                CAST(count.last_execution_time AS DATETIME2) AS last_execution_time
            FROM [{db_name}].sys.dm_exec_query_stats count
            CROSS APPLY [{db_name}].sys.dm_exec_sql_text(count.sql_handle) st
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


@mcp.tool(name="db_01_show_top_queries", description="Performance analysis using Query Store or dm_exec_query_stats for instance 1.")
def db_01_show_top_queries(
    database_name: str | None = None,
    metric: Literal["cpu", "io", "execution_count", "duration"] = "cpu",
    limit: int = 10,
    view: Literal["summary", "standard", "full"] = "standard",
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_show_top_queries_internal(
        instance=1,
        database_name=database_name,
        metric=metric,
        limit=limit,
        view=view,
        page=page,
        page_size=page_size,
    )

@mcp.tool(name="db_02_show_top_queries", description="Performance analysis using Query Store or dm_exec_query_stats for instance 2.")
def db_02_show_top_queries(
    database_name: str | None = None,
    metric: Literal["cpu", "io", "execution_count", "duration"] = "cpu",
    limit: int = 10,
    view: Literal["summary", "standard", "full"] = "standard",
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_show_top_queries_internal(
        instance=2,
        database_name=database_name,
        metric=metric,
        limit=limit,
        view=view,
        page=page,
        page_size=page_size,
    )




@mcp.tool(name="db_01_check_fragmentation", description="Check fragmentation for a specific table or all tables in a schema for instance 1.")
def db_01_check_fragmentation(
    database_name: str | None = None,
    schema_name: str | None = None,
    table_name: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_check_fragmentation_internal(
        instance=1,
        database_name=database_name,
        schema_name=schema_name,
        table_name=table_name,
        page=page,
        page_size=page_size,
    )

@mcp.tool(name="db_02_check_fragmentation", description="Check fragmentation for a specific table or all tables in a schema for instance 2.")
def db_02_check_fragmentation(
    database_name: str | None = None,
    schema_name: str | None = None,
    table_name: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_check_fragmentation_internal(
        instance=2,
        database_name=database_name,
        schema_name=schema_name,
        table_name=table_name,
        page=page,
        page_size=page_size,
    )


def _db_sql2019_check_fragmentation_internal(
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


@mcp.tool(name="db_01_db_sec_perf_metrics", description="Database security and basic performance metrics for instance 1.")
def db_01_db_sec_perf_metrics(
    database_name: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_db_sec_perf_metrics_internal(
        instance=1,
        database_name=database_name,
        page=page,
        page_size=page_size,
    )

@mcp.tool(name="db_02_db_sec_perf_metrics", description="Database security and basic performance metrics for instance 2.")
def db_02_db_sec_perf_metrics(
    database_name: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_db_sec_perf_metrics_internal(
        instance=2,
        database_name=database_name,
        page=page,
        page_size=page_size,
    )

def _db_sql2019_db_sec_perf_metrics_internal(
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
        _execute_safe(cur, f"SELECT COUNT(*) FROM [{db_name}].sys.database_principals WHERE type IN ('S', 'U', 'G')")
        user_count_row = cur.fetchone()
        metrics["user_count"] = user_count_row[0] if user_count_row else 0
        
        # Open transactions
        _execute_safe(cur, f"SELECT COUNT(*) FROM [{db_name}].sys.dm_tran_database_transactions WHERE database_id = DB_ID('{db_name}')")
        open_tx_row = cur.fetchone()
        metrics["open_transactions"] = open_tx_row[0] if open_tx_row else 0
        
        # Data file size
        _execute_safe(cur, f"SELECT SUM(size) * 8 / 1024 FROM [{db_name}].sys.database_files WHERE type = 0")
        data_size_row = cur.fetchone()
        metrics["data_size_mb"] = data_size_row[0] if data_size_row else 0
        
        return _paginate_tool_result(metrics, page=page, page_size=page_size)
    finally:
        conn.close()


@mcp.tool(name="db_01_explain_query", description="Execution plan analysis (SHOWPLAN_ALL) for instance 1.")
def db_01_explain_query(
    database_name: str | None = None,
    sql: str | None = None,
) -> dict[str, Any]:
    return _db_sql2019_explain_query_internal(
        instance=1,
        database_name=database_name,
        sql=sql,
    )

@mcp.tool(name="db_02_explain_query", description="Execution plan analysis (SHOWPLAN_ALL) for instance 2.")
def db_02_explain_query(
    database_name: str | None = None,
    sql: str | None = None,
) -> dict[str, Any]:
    return _db_sql2019_explain_query_internal(
        instance=2,
        database_name=database_name,
        sql=sql,
    )

def _db_sql2019_explain_query_internal(
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


@mcp.tool(name="db_01_analyze_logical_data_model", description="Analyze database schema for logical data modeling issues for instance 1.")
def db_01_analyze_logical_data_model(
    database_name: str | None = None,
    schema: str | None = None,
    view: Literal["summary", "standard", "full"] = "standard",
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_analyze_logical_data_model_internal(
        instance=1,
        database_name=database_name,
        schema=schema,
        view=view,
        page=page,
        page_size=page_size,
    )

@mcp.tool(name="db_02_analyze_logical_data_model", description="Analyze database schema for logical data modeling issues for instance 2.")
def db_02_analyze_logical_data_model(
    database_name: str | None = None,
    schema: str | None = None,
    view: Literal["summary", "standard", "full"] = "standard",
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    return _db_sql2019_analyze_logical_data_model_internal(
        instance=2,
        database_name=database_name,
        schema=schema,
        view=view,
        page=page,
        page_size=page_size,
    )

def _db_sql2019_analyze_logical_data_model_internal(
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


@mcp.tool(name="db_01_open_logical_model", description="Returns an HTML visualization of the logical data model for instance 1.")
def db_01_open_logical_model(
    database_name: str | None = None,
    schema: str | None = None,
) -> str:
    return _db_sql2019_open_logical_model_internal(
        instance=1,
        database_name=database_name,
        schema=schema,
    )

@mcp.tool(name="db_02_open_logical_model", description="Returns an HTML visualization of the logical data model for instance 2.")
def db_02_open_logical_model(
    database_name: str | None = None,
    schema: str | None = None,
) -> str:
    return _db_sql2019_open_logical_model_internal(
        instance=2,
        database_name=database_name,
        schema=schema,
    )

def _db_sql2019_open_logical_model_internal(
    instance: int = 1,
    database_name: str | None = None,
    schema: str | None = None,
) -> str:
    """Returns an HTML visualization of the logical data model."""
    _prune_logical_model_reports()
    result = _analyze_logical_data_model_internal(instance, str(database_name) if database_name is not None and not isinstance(database_name, str) else database_name, schema)
    html = _render_data_model_html(result, result.get("issues", {}))
    report_id = str(uuid.uuid4())
    with _LOGICAL_MODEL_REPORTS_LOCK:
        _LOGICAL_MODEL_REPORTS[report_id] = (time.time(), html)
    base_url = _resolve_public_base_url()
    return f"{base_url}/data-model-analysis?id={report_id}"


@mcp.tool(name="db_01_generate_ddl", description="Generate T-SQL CREATE TABLE script for instance 1.")
def db_01_generate_ddl(
    database_name: str | None = None,
    schema_name: str = "dbo",
    table_name: str | None = None,
) -> str:
    return _db_sql2019_generate_ddl_internal(
        instance=1,
        database_name=database_name,
        schema_name=schema_name,
        table_name=table_name,
    )

@mcp.tool(name="db_02_generate_ddl", description="Generate T-SQL CREATE TABLE script for instance 2.")
def db_02_generate_ddl(
    database_name: str | None = None,
    schema_name: str = "dbo",
    table_name: str | None = None,
) -> str:
    return _db_sql2019_generate_ddl_internal(
        instance=2,
        database_name=database_name,
        schema_name=schema_name,
        table_name=table_name,
    )

def _db_sql2019_generate_ddl_internal(
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
            f"""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH,
                   NUMERIC_PRECISION, NUMERIC_SCALE, COLUMN_DEFAULT
            FROM [{db_name}].INFORMATION_SCHEMA.COLUMNS
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


def db_sql2019_generate_ddl(
    instance: int = 1,
    database_name: str | None = None,
    object_name: str | None = None,
    object_type: str = "table",
) -> str:
    """Backward-compatible wrapper for legacy generate_ddl call signature."""
    if not object_name:
        raise ValueError("object_name is required")
    if object_type.strip().lower() not in {"table", "tables"}:
        raise ValueError("object_type must be 'table'")

    schema_name, table_name = _parse_schema_qualified_name(object_name)
    return _db_sql2019_generate_ddl_internal(
        instance=instance,
        database_name=database_name,
        schema_name=schema_name,
        table_name=table_name,
    )


@mcp.tool(name="db_01_create_db_user", description="Creates a new database user with a specified username for instance 1.")
def db_01_create_db_user(
    username: str | None = None,
) -> dict[str, Any]:
    return _db_sql2019_create_db_user_internal(
        instance=1,
        username=username,
    )

@mcp.tool(name="db_02_create_db_user", description="Creates a new database user with a specified username for instance 2.")
def db_02_create_db_user(
    username: str | None = None,
) -> dict[str, Any]:
    return _db_sql2019_create_db_user_internal(
        instance=2,
        username=username,
    )

def _db_sql2019_create_db_user_internal(
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
        _execute_safe(cur, f"CREATE USER [{username}] WITH PASSWORD = ?", [password])
        return {"status": "success", "username": username, "database": db_name}
    finally:
        conn.close()


@mcp.tool(name="db_01_drop_db_user", description="Drops a database user with a specified username for instance 1.")
def db_01_drop_db_user(
    username: str | None = None,
    database_name: str | None = None,
) -> dict[str, Any]:
    return _db_sql2019_drop_db_user_internal(
        instance=1,
        username=username,
        database_name=database_name,
    )

@mcp.tool(name="db_02_drop_db_user", description="Drops a database user with a specified username for instance 2.")
def db_02_drop_db_user(
    username: str | None = None,
    database_name: str | None = None,
) -> dict[str, Any]:
    return _db_sql2019_drop_db_user_internal(
        instance=2,
        username=username,
        database_name=database_name,
    )

def _db_sql2019_drop_db_user_internal(
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
        _execute_safe(cur, f"DROP USER [{username}]")
        return {"status": "success", "username": username, "database": db_name}
    finally:
        conn.close()


@mcp.tool(name="db_01_kill_session", description="Kill a database session for instance 1.")
def db_01_kill_session(
    session_id: int | None = None,
) -> dict[str, Any]:
    return _db_sql2019_kill_session_internal(
        instance=1,
        session_id=session_id,
    )

@mcp.tool(name="db_02_kill_session", description="Kill a database session for instance 2.")
def db_02_kill_session(
    session_id: int | None = None,
) -> dict[str, Any]:
    return _db_sql2019_kill_session_internal(
        instance=2,
        session_id=session_id,
    )

def _db_sql2019_kill_session_internal(instance: int = 1, session_id: int | None = None) -> dict[str, Any]:
    """Kill a database session."""
    _ensure_write_enabled()
    if session_id is None:
        raise ValueError("session_id is required")
    validate_instance(instance)
    conn = get_connection("master", instance=instance)
    try:
        cur = conn.cursor()
        _execute_safe(cur, f"KILL {int(session_id)}")
        return {"status": "success", "session_id": session_id}
    finally:
        conn.close()


@mcp.tool(name="db_01_create_object", description="Execute CREATE statement for instance 1.")
def db_01_create_object(
    database_name: str | None = None,
    sql: str | None = None,
) -> dict[str, Any]:
    return _db_sql2019_create_object_internal(
        instance=1,
        database_name=database_name,
        sql=sql,
    )

@mcp.tool(name="db_02_create_object", description="Execute CREATE statement for instance 2.")
def db_02_create_object(
    database_name: str | None = None,
    sql: str | None = None,
) -> dict[str, Any]:
    return _db_sql2019_create_object_internal(
        instance=2,
        database_name=database_name,
        sql=sql,
    )

def _db_sql2019_create_object_internal(
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


@mcp.tool(name="db_01_alter_object", description="Execute ALTER statement for instance 1.")
def db_01_alter_object(
    database_name: str | None = None,
    sql: str | None = None,
) -> dict[str, Any]:
    return _db_sql2019_alter_object_internal(
        instance=1,
        database_name=database_name,
        sql=sql,
    )

@mcp.tool(name="db_02_alter_object", description="Execute ALTER statement for instance 2.")
def db_02_alter_object(
    database_name: str | None = None,
    sql: str | None = None,
) -> dict[str, Any]:
    return _db_sql2019_alter_object_internal(
        instance=2,
        database_name=database_name,
        sql=sql,
    )

def _db_sql2019_alter_object_internal(
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


@mcp.tool(name="db_01_drop_object", description="Execute DROP statement for instance 1.")
def db_01_drop_object(
    database_name: str | None = None,
    sql: str | None = None,
) -> dict[str, Any]:
    return _db_sql2019_drop_object_internal(
        instance=1,
        database_name=database_name,
        sql=sql,
    )

@mcp.tool(name="db_02_drop_object", description="Execute DROP statement for instance 2.")
def db_02_drop_object(
    database_name: str | None = None,
    sql: str | None = None,
) -> dict[str, Any]:
    return _db_sql2019_drop_object_internal(
        instance=2,
        database_name=database_name,
        sql=sql,
    )

def _db_sql2019_drop_object_internal(
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




def _register_sql2019_instance_aliases() -> None:
    """
    Backward-compatible tool aliases:
    - db_01_* -> db_01_sql2019_*
    - db_02_* -> db_02_sql2019_*
    Also maps server_info -> server_info_mcp to match legacy prompts/docs.
    """
    tool_pattern = re.compile(r"^db_(0[12])_([a-z0-9_]+)$")

    for symbol_name, tool_fn in list(globals().items()):
        if not callable(tool_fn):
            continue

        match = tool_pattern.match(symbol_name)
        if not match:
            continue

        if "_sql2019_" in symbol_name:
            continue

        instance_id, suffix = match.groups()
        alias_suffix = "server_info_mcp" if suffix == "server_info" else suffix
        alias_name = f"db_{instance_id}_sql2019_{alias_suffix}"

        if alias_name in globals():
            continue

        globals()[alias_name] = tool_fn

        try:
            mcp.tool(
                name=alias_name,
                description=f"Compatibility alias for `{symbol_name}`.",
            )(tool_fn)
        except Exception as exc:
            logger.warning("Failed to register compatibility alias %s: %s", alias_name, exc)


_register_sql2019_instance_aliases()


def build_mcp_run_config() -> dict[str, Any]:
    transport = str(getattr(SETTINGS, "transport", "http") or "http").lower()
    config: dict[str, Any] = {"transport": transport}
    if transport == "http":
        config["host"] = getattr(SETTINGS, "host", None)
        config["port"] = getattr(SETTINGS, "port", None)
    return config


def configure_http_auth(settings: Settings | None = None) -> dict[str, Any]:
    effective_settings = settings or SETTINGS
    raw_auth_type = str(getattr(effective_settings, "auth_type", "") or "").strip().lower()
    auth_type = raw_auth_type or "none"

    supported_auth_types = {"none", "apikey", "oidc", "jwt", "azure-ad", "github", "google"}
    if auth_type not in supported_auth_types:
        raise ValueError(
            f"Unsupported FASTMCP_AUTH_TYPE: {raw_auth_type!r}. "
            "Supported values: none, apikey, oidc, jwt, azure-ad, github, google."
        )

    auth_enabled = auth_type != "none"
    if auth_type == "none":
        return {
            "auth_enabled": False,
            "auth_type": "none",
            "provider": None,
            "validation_mode": "disabled",
            "allow_query_token_auth": False,
        }

    if auth_type == "apikey":
        api_key = str(getattr(effective_settings, "api_key", "") or "").strip()
        if not api_key:
            raise RuntimeError("FASTMCP_AUTH_TYPE=apikey requires FASTMCP_API_KEY.")
        return {
            "auth_enabled": True,
            "auth_type": "apikey",
            "provider": "api_key",
            "validation_mode": "static_token_secure_compare",
            "allow_query_token_auth": bool(getattr(effective_settings, "allow_query_token_auth", False)),
        }

    return {
        "auth_enabled": True,
        "auth_type": auth_type,
        "provider": auth_type,
        "validation_mode": "provider_token_validation",
        "allow_query_token_auth": bool(getattr(effective_settings, "allow_query_token_auth", False)),
    }


def run_server_entrypoint() -> None:
    run_config = build_mcp_run_config()
    _apply_provider_transform_layers()
    _configure_tool_search_transform()

    if run_config.get("transport") == "http":
        auth_config = configure_http_auth(SETTINGS)
        _resolve_http_app()
        logger.info(
            "HTTP authentication configuration resolved",
            extra={
                "auth_enabled": auth_config["auth_enabled"],
                "auth_type": auth_config["auth_type"],
                "validation_mode": auth_config["validation_mode"],
                "allow_query_token_auth": auth_config["allow_query_token_auth"],
            },
        )

    mcp.run(**run_config)


if __name__ == "__main__":
    run_server_entrypoint()











