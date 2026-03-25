import logging
import os
import re
import json
import time
import base64
import hashlib
import hmac
import uuid
import sys
import functools
from datetime import datetime, timezone
from threading import Lock
from contextvars import ContextVar
from typing import Any, Sequence
from html import escape
from urllib.parse import quote
from functools import lru_cache
import pyodbc
from fastmcp import FastMCP

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

# --- Logging setup: honor MCP_LOG_LEVEL ---
_log_level = os.getenv("MCP_LOG_LEVEL", "INFO").upper()
_log_level_value = getattr(logging, _log_level, logging.INFO)
logging.basicConfig(level=_log_level_value)

# Helper to get instance config (module level)
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
        # Use db_user from instance config if available
        "db_user": (lambda: (get_instance_config().get("db_user") if "db_user" in get_instance_config() else ""))() if ("get_instance_config" in globals()) else "",
    }
    if SETTINGS.allow_raw_prompts and prompt_context:
        payload["prompt"] = prompt_context
        payload["raw_prompt_storage_enabled"] = True
    if SETTINGS.audit_log_include_params:
        payload["params_json"] = params_json

    line = json.dumps(payload, ensure_ascii=False, default=str)
    log_path = SETTINGS.audit_log_file
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    with _AUDIT_LOG_LOCK:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


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



def get_connection(database: str | None = None, instance: int = 1) -> pyodbc.Connection:
    validate_instance(instance)
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
mcp = FastMCP(name=MCP_SERVER_NAME)

try:
    import fastmcp
    print(f"\n=== MCP Server Banner ===\n{MCP_SERVER_NAME} | FastMCP version: {fastmcp.__version__}\n========================\n")
except Exception:
    print(f"\n=== MCP Server Banner ===\n{MCP_SERVER_NAME} | FastMCP version: unknown\n========================\n")


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
            from fastmcp.server.transforms.search import BM25SearchTransform as SearchTransform
        else:
            from fastmcp.server.transforms.search import RegexSearchTransform as SearchTransform
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

# Minimal _now_utc_iso helper
def _now_utc_iso():
    return datetime.now(timezone.utc).isoformat()

def validate_instance(instance: int) -> None:
    if instance not in SETTINGS.db_instances:
        raise ValueError(f"Invalid instance: {instance}. Available: {list(SETTINGS.db_instances.keys())}")

# --- Logging setup: honor MCP_LOG_LEVEL ---
_log_level = os.getenv("MCP_LOG_LEVEL", "INFO").upper()
_log_level_value = getattr(logging, _log_level, logging.INFO)
logging.basicConfig(level=_log_level_value)

# Helper to get instance config (module level)
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
        # Use db_user from instance config if available
        "db_user": (lambda: (get_instance_config().get("db_user") if "db_user" in get_instance_config() else ""))() if ("get_instance_config" in globals()) else "",
    }
    if SETTINGS.allow_raw_prompts and prompt_context:
        payload["prompt"] = prompt_context
        payload["raw_prompt_storage_enabled"] = True
    if SETTINGS.audit_log_include_params:
        payload["params_json"] = params_json

    line = json.dumps(payload, ensure_ascii=False, default=str)
    log_path = SETTINGS.audit_log_file
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    with _AUDIT_LOG_LOCK:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


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



def get_connection(database: str | None = None, instance: int = 1) -> pyodbc.Connection:
    validate_instance(instance)
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
mcp = FastMCP(name=MCP_SERVER_NAME)

try:
    import fastmcp
    print(f"\n=== MCP Server Banner ===\n{MCP_SERVER_NAME} | FastMCP version: {fastmcp.__version__}\n========================\n")
except Exception:
    print(f"\n=== MCP Server Banner ===\n{MCP_SERVER_NAME} | FastMCP version: unknown\n========================\n")


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
            from fastmcp.server.transforms.search import BM25SearchTransform as SearchTransform
        else:
            from fastmcp.server.transforms.search import RegexSearchTransform as SearchTransform
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

        
def db_sql2019_list_databases(page: int = 1, page_size: int = DEFAULT_TOOL_PAGE_SIZE, instance: int = 1) -> dict[str, Any]:
    # List online databases visible to the current login.
    conn = get_connection("master", instance=instance)
    try:
        cur = conn.cursor()
        _execute_safe(
            cur,
            "SELECT name FROM sys.databases WHERE state_desc = 'ONLINE' ORDER BY name"
        )
        items = [row[0] for row in cur.fetchall()]
        return _paginate_tool_result(items, page=page, page_size=page_size)
    finally:
        conn.close()



def db_sql2019_list_tables(
    database_name: str,
    schema_name: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
    instance: int = 1,
) -> dict[str, Any]:
    # List tables for a database/schema.
    conn = get_connection(database_name, instance=instance)
    try:
        cur = conn.cursor()
        if schema_name:
            _execute_safe(
                cur,
                "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_SCHEMA = ? ORDER BY TABLE_SCHEMA, TABLE_NAME",
                [schema_name],
            )
        else:
            _execute_safe(
                cur,
                "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_SCHEMA, TABLE_NAME",
            )
        rows = cur.fetchall()
        items = [
            {"TABLE_SCHEMA": row[0], "TABLE_NAME": row[1]}
            for row in rows
            if _is_table_allowed(str(row[0] or "dbo"), str(row[1] or ""))
        ]
        return _paginate_tool_result(items, page=page, page_size=page_size)
    finally:
        conn.close()



def db_sql2019_get_schema(
    database_name: str,
    table_name: str,
    schema_name: str = "dbo",
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
    instance: int = 1,
) -> dict[str, Any]:
    # Get column metadata for a table.
    _enforce_table_scope_for_ident(schema_name, table_name)
    conn = get_connection(database_name, instance=instance)
    try:
        cur = conn.cursor()
        _execute_safe(
            cur,
            "SELECT c.COLUMN_NAME, c.ORDINAL_POSITION, c.DATA_TYPE, c.IS_NULLABLE, c.CHARACTER_MAXIMUM_LENGTH, c.NUMERIC_PRECISION, c.NUMERIC_SCALE, c.COLUMN_DEFAULT FROM INFORMATION_SCHEMA.COLUMNS c WHERE c.TABLE_SCHEMA = ? AND c.TABLE_NAME = ? ORDER BY c.ORDINAL_POSITION",
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
            "database": database_name,
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
    database_name: str,
    sql: str,
    params_json: str | None = None,
    max_rows: int | None = None,
    enforce_readonly: bool = True,
    tool_name: str = "db_sql2019_run_query",
    prompt_context: str | None = None,
    instance: int = 1,
) -> list[dict[str, Any]]:
    if enforce_readonly and not SETTINGS.allow_write:
        _require_readonly(sql)
    _enforce_table_scope_for_sql(sql)
    _write_query_audit_record(
        tool_name=tool_name,
        database_name=database_name,
        sql=sql,
        params_json=params_json,
        prompt_context=prompt_context,
    )

    params = _parse_params_json(params_json)
    row_cap = max_rows if isinstance(max_rows, int) and max_rows > 0 else SETTINGS.max_rows

    conn = get_connection(database_name, instance=instance)
    try:
        cur = conn.cursor()
        _execute_safe(cur, sql, params)
        rows = _fetch_limited(cur, row_cap)
        return _rows_to_dicts(cur, rows)
    finally:
        conn.close()


def db_sql2019_execute_query(
    database_name: str,
    sql: str,
    params_json: str | None = None,
    max_rows: int | None = None,
    prompt_context: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
    instance: int = 1,
) -> dict[str, Any]:
    """Legacy-compatible query executor (read-only unless write mode is enabled)."""
    rows = _run_query_internal(
        database_name=database_name,
        sql=sql,
        params_json=params_json,
        max_rows=max_rows,
        enforce_readonly=True,
        tool_name="db_sql2019_execute_query",
        prompt_context=prompt_context,
        instance=instance,
    )
    return _paginate_tool_result(rows, page=page, page_size=page_size)


def db_sql2019_run_query(
    arg1: str,
    arg2: str | None = None,
    params_json: str | None = None,
    max_rows: int | None = None,
    prompt_context: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
    instance: int = 1,
) -> dict[str, Any]:
    """Execute SQL; supports both legacy (db, sql) and new (sql only) signatures."""
    if arg2 is None:
        database_name = str(get_instance_config(instance).get("db_name") or "master")
        sql = arg1
    else:
        database_name = arg1
        sql = arg2

    rows = _run_query_internal(
        database_name=database_name,
        sql=sql,
        params_json=params_json,
        max_rows=max_rows,
        enforce_readonly=True,
        tool_name="db_sql2019_run_query",
        prompt_context=prompt_context,
        instance=instance,
    )
    return _paginate_tool_result(rows, page=page, page_size=page_size)



def db_sql2019_list_objects(
    database_name: str,
    object_type: str = "TABLE",
    object_name: str | None = None,
    schema: str | None = None,
    order_by: str | None = None,
    limit: int = 50,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
    instance: int = 1,
) -> dict[str, Any]:
    """Unified object listing for database/schema/table/view/index/function/procedure/trigger."""
    conn = get_connection(database_name, instance=instance)
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

        if object_type_norm in {"TABLE", "VIEW"}:
            table_type = "BASE TABLE" if object_type_norm == "TABLE" else "VIEW"
            where_sql = "WHERE TABLE_TYPE = ?"
            params: list[Any] = [table_type]
            if schema:
                where_sql += " AND TABLE_SCHEMA = ?"
                params.append(schema)
            if object_name:
                where_sql += " AND TABLE_NAME LIKE ?"
                params.append(object_name)
            scope_sql, scope_params = _build_table_scope_sql("TABLE_SCHEMA", "TABLE_NAME")
            where_sql += scope_sql
            query_params = params + scope_params

            count_sql = "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES " + where_sql
            data_sql = (
                "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
                "FROM INFORMATION_SCHEMA.TABLES "
                + where_sql
                + " ORDER BY TABLE_SCHEMA, TABLE_NAME"
            )
            return _paginate_query(
                count_sql=count_sql,
                count_params=query_params,
                data_sql=data_sql,
                data_params=query_params,
                row_mapper=lambda rows: _rows_to_dicts(cur, rows),
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



def db_sql2019_get_index_fragmentation(
    database_name: str,
    schema: str | None = None,
    min_fragmentation: float = 10.0,
    min_page_count: int = 100,
    limit: int = 50,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Return index fragmentation rows from dm_db_index_physical_stats."""
    items = _get_index_fragmentation_data(
        database_name=database_name,
        schema=schema,
        min_fragmentation=min_fragmentation,
        min_page_count=min_page_count,
        limit=limit,
    )
    return _paginate_tool_result(items, page=page, page_size=page_size)



def db_sql2019_analyze_index_health(
    database_name: str,
    schema: str | None = None,
    min_fragmentation: float = 10.0,
    min_page_count: int = 100,
    limit: int = 50,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
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

    result = {
        "database": database_name,
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
    database_name: str,
    schema: str,
    table_name: str,
    view: str = "standard",
    fields: str | None = None,
    token_budget: int | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Table-level storage/index/stats/constraint analysis."""
    if view not in {"summary", "standard", "full"}:
        raise ValueError(f"Invalid view: {view}. Must be one of 'summary', 'standard', 'full'.")
    _enforce_table_scope_for_ident(schema, table_name)
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

        result = {
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
        shaped = _apply_table_health_view(result, view)
        budgeted = _apply_token_budget(shaped, token_budget)
        projected = _apply_field_projection(budgeted, fields)
        return _paginate_tool_result(projected, page=page, page_size=page_size)
    finally:
        conn.close()



def db_sql2019_db_stats(database: str | None = None, instance: int = 1) -> dict[str, Any]:
    """Database object counts."""
    db_name = str(database or get_instance_config(instance).get("db_name") or "master")
    conn = get_connection(db_name, instance=instance)
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
) -> dict[str, Any]:
    """Get SQL Server and MCP runtime information."""
    inst_cfg = get_instance_config(instance)
    logger.info(f"[DEBUG] db_sql2019_server_info_mcp: instance={instance}, server={inst_cfg.get('db_server')}, user={inst_cfg.get('db_user')}, db={inst_cfg.get('db_name')}")
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
        headers = {}
        return {
            "server_version": row[0],
            "server_name": row[1],
            "database": row[2],
            "user": row[3],
            "server_version_short": row[4],
            "server_edition": row[5],
            "server_addr": str(inst_cfg.get("db_server") or ""),
            "server_port": int(inst_cfg.get("db_port") or 1433),
            "mcp_transport": SETTINGS.transport,
            "mcp_max_rows": SETTINGS.max_rows,
            "mcp_allow_write": SETTINGS.allow_write,
            # Use MCP_SERVER_NAME from env/config, fallback to empty string if unset
            "mcp_server_name": os.getenv("MCP_SERVER_NAME", ""),
            "http_user_agent": headers.get("user-agent", ""),
        }
    finally:
        conn.close()


def _db_sql2019_show_top_queries_impl(
    database_name: str,
    view: str = "standard",
    fields: str | None = None,
    token_budget: int | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Query Store summary for high-cost queries."""
    if view not in {"summary", "standard", "full"}:
        raise ValueError(f"Invalid view: {view}. Must be one of 'summary', 'standard', 'full'.")
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
            shaped = _apply_top_queries_view(output, view)
            budgeted = _apply_token_budget(shaped, token_budget)
            projected = _apply_field_projection(budgeted, fields)
            return _paginate_tool_result(projected, page=page, page_size=page_size)

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
        shaped = _apply_top_queries_view(output, view)
        budgeted = _apply_token_budget(shaped, token_budget)
        projected = _apply_field_projection(budgeted, fields)
        return _paginate_tool_result(projected, page=page, page_size=page_size)
    finally:
        conn.close()

def db_sql2019_show_top_queries(
    database_name: str,
    view: str = "standard",
    fields: str | None = None,
    token_budget: int | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
    # progress parameter removed
) -> dict[str, Any]:
    """Query Store summary for high-cost queries."""
    if view not in {"summary", "standard", "full"}:
        raise ValueError(f"Invalid view: {view}. Must be one of 'summary', 'standard', 'full'.")
    # Run the implementation synchronously
    result = _db_sql2019_show_top_queries_impl(
        database_name,
        view,
        fields,
        token_budget,
        page,
        page_size,
    )
    return result


def db_sql2019_check_fragmentation(
    database_name: str,
    min_fragmentation: float = 10.0,
    min_page_count: int = 100,
    include_recommendations: bool = True,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
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

    return _paginate_tool_result(output, page=page, page_size=page_size)


def db_sql2019_db_sec_perf_metrics(
    profile: str = "oltp",
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
) -> dict[str, Any]:
    """Security and performance quick audit."""
    if profile not in {"oltp", "olap", "mixed"}:
        raise ValueError(f"Invalid profile: {profile}. Must be one of 'oltp', 'olap', 'mixed'.")
    conn = get_connection("master", instance=instance)
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

        result = {
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
        return _paginate_tool_result(result, page=page, page_size=page_size)
    finally:
        conn.close()


def db_sql2019_explain_query(
    sql: str,
    analyze: bool = False,
    output_format: str = "xml",
    prompt_context: str | None = None,
    instance: int = 1,
) -> dict[str, Any]:
    """Return estimated or actual XML execution plan."""
    if output_format.lower() != "xml":
        raise ValueError("Only XML output_format is currently supported.")
    if not SETTINGS.allow_write:
        _require_readonly(sql)
    _enforce_table_scope_for_sql(sql)
    db_name = str(get_instance_config(instance).get("db_name") or "master")

    _write_query_audit_record(
        tool_name="db_sql2019_explain_query",
        database_name=db_name,
        sql=sql,
        params_json=None,
        prompt_context=prompt_context,
    )

    conn = get_connection(db_name, instance=instance)
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


def db_sql2019_analyze_logical_data_model(
    database_name: str,
    schema: str = "dbo",
    include_views: bool = False,
    max_entities: int | None = None,
    include_attributes: bool = True,
    view: str = "standard",
    fields: str | None = None,
    token_budget: int | None = None,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
    instance: int = 1,
) -> dict[str, Any]:
    """Analyze schema entities and relationships."""
    if view not in {"summary", "standard", "full"}:
        raise ValueError(f"Invalid view: {view}. Must be one of 'summary', 'standard', 'full'.")
    result = _analyze_logical_data_model_internal(
        database_name=database_name,
        schema=schema,
        include_views=include_views,
        max_entities=max_entities,
        include_attributes=include_attributes,
        instance=instance,
    )
    shaped = _apply_logical_model_view(result, view)
    budgeted = _apply_token_budget(shaped, token_budget)
    projected = _apply_field_projection(budgeted, fields)
    return _paginate_tool_result(projected, page=page, page_size=page_size)


def _analyze_erd_issues(
    cur: pyodbc.Cursor,
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    schema: str,
) -> dict[str, Any]:
    """Analyze ERD for data modeling issues and return structured findings."""
    issues = {
        "entities": [],
        "attributes": [],
        "relationships": [],
        "identifiers": [],
        "normalization": [],
    }
    recommendations = {
        "entities": [],
        "attributes": [],
        "relationships": [],
        "identifiers": [],
        "normalization": [],
    }

    # Build FK lookup for quick access
    fk_map = {}
    for rel in relationships:
        key = f"{rel['from_schema']}.{rel['from_entity']}"
        if key not in fk_map:
            fk_map[key] = []
        fk_map[key].append(rel)

    for entity in entities:
        entity_name = entity["entity_name"]
        schema_name = entity["schema_name"]
        full_name = f"{schema_name}.{entity_name}"
        object_id = entity["object_id"]

        # Skip views from normalization checks
        is_view = entity.get("type", "U").strip() == "V"

        # 1. Check for missing primary key
        _execute_safe(
            cur,
            """
            SELECT COUNT(*) AS pk_count
            FROM sys.indexes i
            WHERE i.object_id = ? AND i.is_primary_key = 1
            """,
            [object_id],
        )
        pk_result = cur.fetchone()
        has_pk = pk_result[0] > 0 if pk_result else False

        if not has_pk and not is_view:
            issues["identifiers"].append({
                "severity": "high",
                "entity": full_name,
                "issue": "Missing primary key constraint",
                "description": f"Table '{entity_name}' does not have a primary key defined",
            })
            recommendations["identifiers"].append({
                "entity": full_name,
                "recommendation": f"Add primary key constraint to '{entity_name}'",
                "sql_fix": f"ALTER TABLE [{schema_name}].[{entity_name}] ADD CONSTRAINT PK_{entity_name} PRIMARY KEY (/* specify column(s) */);",
            })

        # 2. Check for FK columns without indexes
        if full_name in fk_map:
            for fk in fk_map[full_name]:
                _execute_safe(
                    cur,
                    """
                    SELECT COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS column_name
                    FROM sys.foreign_key_columns fkc
                    JOIN sys.foreign_keys fk ON fkc.constraint_object_id = fk.object_id
                    WHERE fk.name = ?
                    """,
                    [fk["name"]],
                )
                fk_cols = [row[0] for row in cur.fetchall()]

                for col_name in fk_cols:
                    _execute_safe(
                        cur,
                        """
                        SELECT COUNT(*) AS index_count
                        FROM sys.index_columns ic
                        JOIN sys.indexes i ON ic.object_id = i.object_id AND ic.index_id = i.index_id
                        JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                        WHERE ic.object_id = ? AND c.name = ? AND ic.index_column_id = 1
                        """,
                        [object_id, col_name],
                    )
                    idx_result = cur.fetchone()
                    has_index = idx_result[0] > 0 if idx_result else False

                    if not has_index:
                        issues["relationships"].append({
                            "severity": "medium",
                            "entity": full_name,
                            "column": col_name,
                            "issue": "Foreign key column without index",
                            "description": f"Column '{col_name}' in foreign key '{fk['name']}' is not indexed",
                        })
                        recommendations["relationships"].append({
                            "entity": full_name,
                            "column": col_name,
                            "recommendation": f"Create index on foreign key column '{col_name}'",
                            "sql_fix": f"CREATE INDEX IX_{entity_name}_{col_name} ON [{schema_name}].[{entity_name}] ([{col_name}]);",
                        })

        # 3. Check for potential missing FK constraints (columns ending with ID)
        if "attributes" in entity:
            for attr in entity["attributes"]:
                col_name = attr["name"]
                if col_name.endswith("ID") and col_name != f"{entity_name}ID":
                    # Check if this column has an FK
                    _execute_safe(
                        cur,
                        """
                        SELECT COUNT(*) AS fk_count
                        FROM sys.foreign_key_columns fkc
                        JOIN sys.columns c ON fkc.parent_object_id = c.object_id AND fkc.parent_column_id = c.column_id
                        WHERE fkc.parent_object_id = ? AND c.name = ?
                        """,
                        [object_id, col_name],
                    )
                    fk_result = cur.fetchone()
                    has_fk = fk_result[0] > 0 if fk_result else False

                    if not has_fk:
                        issues["relationships"].append({
                            "severity": "low",
                            "entity": full_name,
                            "column": col_name,
                            "issue": "Potential missing foreign key constraint",
                            "description": f"Column '{col_name}' follows FK naming convention but has no constraint",
                        })
                        potential_ref_table = col_name[:-2]  # Remove 'ID' suffix
                        recommendations["relationships"].append({
                            "entity": full_name,
                            "column": col_name,
                            "recommendation": f"Consider adding FK constraint for '{col_name}' if it references another table",
                            "sql_fix": f"-- Verify target table exists, then:\n-- ALTER TABLE [{schema_name}].[{entity_name}] ADD CONSTRAINT FK_{entity_name}_{potential_ref_table} FOREIGN KEY ([{col_name}]) REFERENCES [{schema_name}].[{potential_ref_table}](/* PK column */);",
                        })

        # 4. Check for datatype mismatches in FK relationships
        if full_name in fk_map:
            for fk in fk_map[full_name]:
                _execute_safe(
                    cur,
                    """
                    SELECT
                        c_parent.name AS parent_col,
                        ty_parent.name AS parent_type,
                        c_parent.max_length AS parent_max_length,
                        c_ref.name AS ref_col,
                        ty_ref.name AS ref_type,
                        c_ref.max_length AS ref_max_length
                    FROM sys.foreign_key_columns fkc
                    JOIN sys.columns c_parent ON fkc.parent_object_id = c_parent.object_id AND fkc.parent_column_id = c_parent.column_id
                    JOIN sys.types ty_parent ON c_parent.user_type_id = ty_parent.user_type_id
                    JOIN sys.columns c_ref ON fkc.referenced_object_id = c_ref.object_id AND fkc.referenced_column_id = c_ref.column_id
                    JOIN sys.types ty_ref ON c_ref.user_type_id = ty_ref.user_type_id
                    WHERE fkc.constraint_object_id = OBJECT_ID(?)
                    """,
                    [f"[{schema_name}].[{fk['name']}]"],
                )
                fk_cols_info = _rows_to_dicts(cur, cur.fetchall())

                for col_info in fk_cols_info:
                    if col_info["parent_type"] != col_info["ref_type"] or col_info["parent_max_length"] != col_info["ref_max_length"]:
                        issues["relationships"].append({
                            "severity": "high",
                            "entity": full_name,
                            "fk_name": fk["name"],
                            "issue": "Datatype mismatch in foreign key relationship",
                            "description": f"Column '{col_info['parent_col']}' ({col_info['parent_type']}) does not match referenced column '{col_info['ref_col']}' ({col_info['ref_type']})",
                        })
                        recommendations["relationships"].append({
                            "entity": full_name,
                            "fk_name": fk["name"],
                            "recommendation": f"Align datatypes: change '{col_info['parent_col']}' to match '{col_info['ref_col']}'",
                            "sql_fix": f"-- This may require dropping FK first:\n-- ALTER TABLE [{schema_name}].[{entity_name}] DROP CONSTRAINT [{fk['name']}];\n-- ALTER TABLE [{schema_name}].[{entity_name}] ALTER COLUMN [{col_info['parent_col']}] {col_info['ref_type']};\n-- Then recreate FK constraint",
                        })

        # 5. Check for normalization issues (wide tables)
        if "attributes" in entity and not is_view:
            col_count = len(entity["attributes"])
            if col_count > 50:
                issues["normalization"].append({
                    "severity": "medium",
                    "entity": full_name,
                    "issue": "Potentially denormalized table (wide table)",
                    "description": f"Table '{entity_name}' has {col_count} columns, which may indicate normalization issues",
                })
                recommendations["normalization"].append({
                    "entity": full_name,
                    "recommendation": f"Review table structure and consider vertical partitioning or normalization",
                    "guidance": "Consider splitting into multiple related tables based on functional dependencies",
                })

            # Check for repeating column groups (e.g., Phone1, Phone2, Phone3)
            col_names = [attr["name"] for attr in entity["attributes"]]
            patterns = {}
            for col_name in col_names:
                # Extract base name (remove trailing numbers)
                match = re.match(r"^(.+?)(\d+)$", col_name)
                if match:
                    base_name = match.group(1)
                    if base_name not in patterns:
                        patterns[base_name] = []
                    patterns[base_name].append(col_name)

            for base_name, cols in patterns.items():
                if len(cols) >= 3:
                    issues["normalization"].append({
                        "severity": "medium",
                        "entity": full_name,
                        "issue": "Repeating column group detected",
                        "description": f"Columns {', '.join(cols)} suggest a repeating group that should be normalized",
                    })
                    recommendations["normalization"].append({
                        "entity": full_name,
                        "recommendation": f"Create a separate related table for '{base_name}' values",
                        "guidance": f"Move repeating columns to a new table with FK back to '{entity_name}'",
                    })

    # Update issue counts
    issue_counts = {
        "entities": len(issues["entities"]),
        "attributes": len(issues["attributes"]),
        "relationships": len(issues["relationships"]),
        "identifiers": len(issues["identifiers"]),
        "normalization": len(issues["normalization"]),
    }

    return {
        "issues": issues,
        "recommendations": recommendations,
        "issue_counts": issue_counts,
    }


def _analyze_logical_data_model_internal(
    database_name: str,
    schema: str = "dbo",
    include_views: bool = False,
    max_entities: int | None = None,
    include_attributes: bool = True,
    instance: int = 1,
) -> dict[str, Any]:
    conn = get_connection(database_name, instance=instance)
    try:
        cur = conn.cursor()
        entities, relationships = _fetch_relationships(cur, schema, include_views, max_entities)

        if include_attributes:
            for entity in entities:
                _execute_safe(
                    cur,
                    """
                    SELECT c.name, c.column_id, ty.name AS type_name, c.is_nullable, c.max_length, c.precision, c.scale
                    FROM sys.columns c
                    JOIN sys.types ty ON c.user_type_id = ty.user_type_id
                    WHERE c.object_id = OBJECT_ID(?)
                    ORDER BY c.column_id
                    """,
                    [f"[{entity['schema_name']}].[{entity['entity_name']}]"],
                )
                attrs = _rows_to_dicts(cur, cur.fetchall())
                entity["attributes"] = attrs

        # Analyze ERD for issues
        analysis = _analyze_erd_issues(cur, entities, relationships, schema)

        return {
            "summary": {
                "database": database_name,
                "schema": schema,
                "generated_at_utc": _now_utc_iso(),
                "entities": len(entities),
                "relationships": len(relationships),
                "issues_count": analysis["issue_counts"],
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
            "issues": analysis["issues"],
            "recommendations": analysis["recommendations"],
        }
    finally:
        conn.close()


_OPEN_MODEL_CACHE = {}  # LRUCache replaced with dict for stub


def db_sql2019_open_logical_model(database_name: str, instance: int = 1) -> dict[str, Any]:
    """Generate a URL to the in-memory logical model snapshot."""
    model = _analyze_logical_data_model_internal(database_name, instance=instance)
    model_id = str(uuid.uuid4())
    _OPEN_MODEL_CACHE[model_id] = model  # LRUCache handles eviction
    base = SETTINGS.public_base_url or f"http://localhost:{SETTINGS.port}"
    return {
        "message": f"ERD webpage generated for database '{database_name}'.",
        "database": database_name,
        "erd_url": f"{base}/data-model-analysis?id={model_id}",
        "summary": model.get("summary", {}),
    }


def db_sql2019_generate_ddl(
    database_name: str,
    object_name: str,
    object_type: str,
    page: int = 1,
    page_size: int = DEFAULT_TOOL_PAGE_SIZE,
    instance: int = 1,
) -> dict[str, Any]:
    """Generate CREATE script for table/view/procedure/function/trigger object."""
    object_type_norm = object_type.lower()
    table_schema = "dbo"
    table_name = object_name
    if object_type_norm == "table":
        table_schema, table_name = _parse_schema_qualified_name(object_name, default_schema="dbo")
        _enforce_table_scope_for_ident(table_schema, table_name)
    
    conn = get_connection(database_name, instance=instance)
    try:
        cur = conn.cursor()

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
                JOIN sys.schemas s ON t.schema_id = s.schema_id
                WHERE t.name = ? AND s.name = ?
                ORDER BY c.column_id
                """,
                [table_name, table_schema],
            )
            cols = _rows_to_dicts(cur, cur.fetchall())
            if not cols:
                result = {
                    "database_name": database_name,
                    "object_name": object_name,
                    "object_type": object_type,
                    "success": False,
                    "error": "Object not found",
                }
                return _paginate_tool_result(result, page=page, page_size=page_size)

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
            ddl = f"CREATE TABLE [{table_schema}].[{table_name}] (\n" + ",\n".join(col_lines) + "\n);"

            result = {
                "database_name": database_name,
                "object_name": object_name,
                "object_type": object_type,
                "success": True,
                "metadata": {},
                "dependencies": [],
                "ddl": ddl,
            }
            return _paginate_tool_result(result, page=page, page_size=page_size)

        _execute_safe(cur, "SELECT OBJECT_DEFINITION(OBJECT_ID(?))", [object_name])
        row = cur.fetchone()
        ddl = row[0] if row and row[0] else None
        result = {
            "database_name": database_name,
            "object_name": object_name,
            "object_type": object_type,
            "success": ddl is not None,
            "metadata": {},
            "dependencies": [],
            "ddl": ddl,
        }
        return _paginate_tool_result(result, page=page, page_size=page_size)
    finally:
        conn.close()


def db_sql2019_create_db_user(
    username: str,
    password: str,
    privileges: str = "read",
    database: str | None = None,
    instance: int = 1,
) -> dict[str, Any]:
    """Create SQL login/user and grant role permissions."""
    if privileges not in {"read", "readwrite"}:
        raise ValueError(f"Invalid privileges: {privileges}. Must be 'read' or 'readwrite'.")
    _ensure_write_enabled()
    db_name = str(database or get_instance_config(instance).get("db_name") or "master")
    safe_user = _validate_identifier(username, "username")

    conn = get_connection("master", instance=instance)
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


def db_sql2019_drop_db_user(username: str, database: str | None = None, instance: int = 1) -> dict[str, Any]:
    """Drop SQL user and login if present."""
    _ensure_write_enabled()
    db_name = str(database or get_instance_config(instance).get("db_name") or "master")
    safe_user = _validate_identifier(username, "username")

    conn = get_connection("master", instance=instance)
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


def db_sql2019_kill_session(session_id: int, instance: int = 1) -> dict[str, Any]:
    """Terminate a SQL Server session on the selected instance."""
    _ensure_write_enabled()
    if session_id <= 0:
        raise ValueError("session_id must be > 0")
    if instance <= 0:
        raise ValueError("instance must be > 0")

    conn = get_connection("master", instance=instance)
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


def db_sql2019_create_object(
    object_type: str,
    object_name: str,
    schema: str | None = None,
    parameters: dict[str, Any] | None = None,
    instance: int = 1,
) -> dict[str, Any]:
    """Create table/view/index/function/procedure/trigger."""
    _ensure_write_enabled()
    safe_schema = _validate_identifier(schema or "dbo", "schema")
    safe_name = _validate_identifier(object_name, "object name")

    sql = _build_create_object_sql(object_type, safe_name, safe_schema, parameters)

    db_name = str(get_instance_config(instance).get("db_name") or "master")
    conn = get_connection(db_name, instance=instance)
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


def db_sql2019_alter_object(
    object_type: str,
    object_name: str,
    operation: str,
    schema: str | None = None,
    parameters: dict[str, Any] | None = None,
    instance: int = 1,
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

    db_name = str(get_instance_config(instance).get("db_name") or "master")
    conn = get_connection(db_name, instance=instance)
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


def db_sql2019_drop_object(
    object_type: str,
    object_name: str,
    schema: str | None = None,
    parameters: dict[str, Any] | None = None,
    instance: int = 1,
) -> dict[str, Any]:
    """Drop object with optional IF EXISTS and CASCADE-like behavior where supported."""
    _ensure_write_enabled()

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

    db_name = get_instance_config(instance).get("db_name")
    if not isinstance(db_name, str) or not db_name:
        db_name = "master"
    conn = get_connection(db_name, instance=instance)
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



_TOOL_REGISTRATION_LIST = [
    ("ping", db_sql2019_ping),
    ("list_databases", db_sql2019_list_databases),
    ("list_tables", db_sql2019_list_tables),
    ("get_schema", db_sql2019_get_schema),
    ("execute_query", db_sql2019_execute_query),
    ("run_query", db_sql2019_run_query),
    ("list_objects", db_sql2019_list_objects),
    ("get_index_fragmentation", db_sql2019_get_index_fragmentation),
    ("analyze_index_health", db_sql2019_analyze_index_health),
    ("analyze_table_health", db_sql2019_analyze_table_health),
    ("db_stats", db_sql2019_db_stats),
    ("server_info_mcp", db_sql2019_server_info_mcp),
    ("show_top_queries", db_sql2019_show_top_queries),
    ("check_fragmentation", db_sql2019_check_fragmentation),
    ("db_sec_perf_metrics", db_sql2019_db_sec_perf_metrics),
    ("explain_query", db_sql2019_explain_query),
    ("analyze_logical_data_model", db_sql2019_analyze_logical_data_model),
    ("open_logical_model", db_sql2019_open_logical_model),
    ("generate_ddl", db_sql2019_generate_ddl),
    ("create_db_user", db_sql2019_create_db_user),
    ("drop_db_user", db_sql2019_drop_db_user),
    ("kill_session", db_sql2019_kill_session),
    ("create_object", db_sql2019_create_object),
    ("alter_object", db_sql2019_alter_object),
    ("drop_object", db_sql2019_drop_object),
]

def _register_dual_instance_tools():
    """
    Register each tool in _TOOL_REGISTRATION_LIST twice: 
    as db_01_sql2019_* (instance=1) and db_02_sql2019_* (instance=2).
    """
    import functools

    def make_tool_wrapper(f, default_instance):
        @functools.wraps(f)
        def wrapper(*args, instance=default_instance, **kwargs):
            return f(*args, instance=instance, **kwargs)
        return wrapper

    for tool_suffix, func in _TOOL_REGISTRATION_LIST:
        # Instance 1: db_01_sql2019_*
        mcp.tool(name=f"db_01_sql2019_{tool_suffix}")(make_tool_wrapper(func, 1))
        # Instance 2: db_02_sql2019_*
        mcp.tool(name=f"db_02_sql2019_{tool_suffix}")(make_tool_wrapper(func, 2))


# --- Register dual-instance tools at the very end to ensure all functions are defined ---

_register_dual_instance_tools()

# Print all registered tool names at startup for verification
def _print_registered_tools():
    try:
        import asyncio
        tools = asyncio.run(mcp.get_tools())
        print("Registered MCP tools:")
        for t in sorted(tools, key=lambda x: x.name):
            print(f" - {t.name}")
    except Exception as e:
        logger.warning("Could not list registered tools: %s", e)

_print_registered_tools()

def _paginate(items: list[Any], page: int, per_page: int) -> tuple[list[Any], int]:
    total = len(items)
    if per_page <= 0:
        return items, 1
    total_pages = max(1, (total + per_page - 1) // per_page)
    safe_page = min(max(1, page), total_pages)
    start = (safe_page - 1) * per_page
    end = start + per_page
    return items[start:end], total_pages


def _render_data_model_html(model_id: str, model: dict[str, Any], page: int, focus_entity: str | None) -> str:
    summary = model.get("summary", {})
    entities = model.get("logical_model", {}).get("entities", [])
    relationships = model.get("logical_model", {}).get("relationships", [])

    def _entity_key(schema_name: str, entity_name: str) -> str:
        raw = f"{schema_name}_{entity_name}"
        cleaned = re.sub(r"[^A-Za-z0-9_]", "_", raw)
        if not re.match(r"^[A-Za-z_]", cleaned):
            cleaned = f"E_{cleaned}"
        return cleaned

    entity_map: dict[str, str] = {}
    lines: list[str] = ["erDiagram"]

    per_page = 10
    max_entities = 120
    max_attrs = 12
    all_entities = sorted(
        entities,
        key=lambda e: (str(e.get("schema_name", "")), str(e.get("entity_name", ""))),
    )
    paged_entities, total_pages = _paginate(all_entities, page, per_page)

    focus = (focus_entity or "").strip()
    focus_set: set[str] = set()
    if focus:
        adjacency: dict[str, set[str]] = {}
        for rel in relationships:
            from_name = str(rel.get("from_entity", ""))
            to_name = str(rel.get("to_entity", ""))
            if not from_name or not to_name:
                continue
            adjacency.setdefault(from_name, set()).add(to_name)
            adjacency.setdefault(to_name, set()).add(from_name)

        level1 = set(adjacency.get(focus, set()))
        level2: set[str] = set()
        for node in level1:
            level2.update(adjacency.get(node, set()))
        focus_set = {focus} | level1 | level2

    if focus_set:
        limited_entities = [e for e in all_entities if f"{e.get('schema_name')}.{e.get('entity_name')}" in focus_set]
    else:
        limited_entities = all_entities[:max_entities]

    for entity in limited_entities:
        schema_name = str(entity.get("schema_name", "dbo"))
        entity_name = str(entity.get("entity_name", "unknown"))
        key = _entity_key(schema_name, entity_name)
        entity_map[f"{schema_name}.{entity_name}"] = key
        lines.append(f"    {key} {{")

        attrs = entity.get("attributes", [])
        if isinstance(attrs, list):
            for attr in attrs[:max_attrs]:
                col_name = str(attr.get("name", "col"))
                data_type = str(attr.get("type_name", ""))
                safe_col_name = re.sub(r"[^A-Za-z0-9_]", "_", col_name)
                safe_data_type = re.sub(r"[^A-Za-z0-9_]", "_", data_type)
                lines.append(f"        {safe_data_type} {safe_col_name}")
            if len(attrs) > max_attrs:
                lines.append("        string MORE_COLUMNS")

        lines.append("    }")

    for rel in relationships:
        from_entity = str(rel.get("from_entity", ""))
        to_entity = str(rel.get("to_entity", ""))
        if from_entity not in entity_map or to_entity not in entity_map:
            continue
        rel_name = str(rel.get("name", "FK"))
        rel_label = re.sub(r"[^A-Za-z0-9_]", "", rel_name)[:80] or "FK"
        lines.append(f"    {entity_map[from_entity]}}}o--||{entity_map[to_entity]} : \"{rel_label}\"")

    mermaid_markup = "\n".join(lines)

    entity_cards: list[str] = []
    for entity in paged_entities:
        schema_name = str(entity.get("schema_name", "dbo"))
        entity_name = str(entity.get("entity_name", "unknown"))
        attrs = entity.get("attributes", [])
        attr_preview: list[str] = []
        if isinstance(attrs, list):
            for attr in attrs[:8]:
                col = escape(str(attr.get("name", "col")))
                typ = escape(str(attr.get("type_name", "")))
                attr_preview.append(f"{col} ({typ})")
        entity_label = f"{schema_name}.{entity_name}"
        entity_cards.append(
            f"<div class='entity-card' data-entity='{escape(entity_label)}'>"
            f"<h4><a href='/data-model-analysis?id={quote(model_id)}&focus={quote(entity_label)}&page={page}'>{escape(entity_label)}</a></h4>"
            f"<div class='muted'>Columns: {len(attrs) if isinstance(attrs, list) else 0}</div>"
            "<ul>"
            + "".join(f"<li>{item}</li>" for item in attr_preview)
            + "</ul>"
            "</div>"
        )

    issues_count = summary.get("issues_count", {})
    issues_html = (
        "<div class='stats'>"
        f"<div><strong>Entities</strong><br>{len(entities)}</div>"
        f"<div><strong>Relationships</strong><br>{len(relationships)}</div>"
        f"<div><strong>Identifier Issues</strong><br>{issues_count.get('identifiers', 0)}</div>"
        f"<div><strong>Relationship Issues</strong><br>{issues_count.get('relationships', 0)}</div>"
        "</div>"
    )

    truncated_note = ""
    if focus_set:
        truncated_note = f"<p class='warn'>ERD focused on {escape(focus)} with two-level relationships.</p>"
    elif len(entities) > max_entities:
        truncated_note = f"<p class='warn'>Diagram is showing first {max_entities} of {len(entities)} entities for readability.</p>"

    prev_page = max(1, page - 1)
    next_page = min(total_pages, page + 1)
    pagination_html = (
        "<div class='pager'>"
        f"<a href='/data-model-analysis?id={quote(model_id)}&page={prev_page}&focus={quote(focus)}'>Prev</a>"
        f"<span>Page {page} of {total_pages}</span>"
        f"<a href='/data-model-analysis?id={quote(model_id)}&page={next_page}&focus={quote(focus)}'>Next</a>"
        "</div>"
    )

    return f"""
<!doctype html>
<html>
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Data Model Analysis</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; color: #1f2937; }}
        .wrap {{ padding: 16px; }}
        .muted {{ color: #6b7280; font-size: 13px; }}
        .warn {{ color: #92400e; background: #fffbeb; border: 1px solid #fcd34d; padding: 8px; border-radius: 6px; }}
        .stats {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 10px; margin: 12px 0; }}
        .stats > div {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px; text-align: center; }}
        .toolbar {{ display: flex; gap: 8px; margin: 8px 0; align-items: center; flex-wrap: wrap; }}
        .toolbar button {{ padding: 6px 10px; border: 1px solid #d1d5db; background: white; border-radius: 6px; cursor: pointer; }}
        .toolbar input {{ padding: 6px 10px; border: 1px solid #d1d5db; border-radius: 6px; min-width: 260px; }}
        .search-status {{ font-size: 12px; color: #4b5563; }}
        .diagram-shell {{ border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; height: 70vh; background: #fff; }}
        #diagramViewport {{ width: 100%; height: 100%; overflow: hidden; cursor: grab; }}
        #diagramViewport:active {{ cursor: grabbing; }}
        #diagramLayer {{ transform-origin: 0 0; }}
        .grid {{ margin-top: 16px; display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }}
        .entity-card {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; background: #fff; }}
        .entity-card.match {{ border-color: #2563eb; box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15); }}
        .entity-card h4 {{ margin: 0 0 4px; font-size: 14px; }}
        .entity-card a {{ color: #1d4ed8; text-decoration: none; }}
        .entity-card ul {{ margin: 8px 0 0; padding-left: 18px; }}
        .entity-card li {{ font-size: 12px; line-height: 1.35; }}
        .pager {{ display: flex; gap: 12px; align-items: center; margin: 8px 0 16px; }}
        .pager a {{ color: #1d4ed8; text-decoration: none; }}
    </style>
    <script type=\"module\">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        window._mermaid = mermaid;
    </script>
</head>
<body>
    <div class=\"wrap\">
        <h2>Logical Model Report: {escape(str(summary.get("database", "unknown")))}</h2>
        <div class=\"muted\">Report ID: {escape(model_id)} · Generated: {escape(str(summary.get("generated_at_utc", "")))}</div>
        {issues_html}
        {truncated_note}

        <div class=\"toolbar\">
            <button onclick=\"zoomIn()\">Zoom In</button>
            <button onclick=\"zoomOut()\">Zoom Out</button>
            <button onclick=\"resetView()\">Reset</button>
            <input id=\"entitySearch\" type=\"text\" placeholder=\"Focus entity (e.g., AccountDataIndicator)\" onkeydown=\"if(event.key==='Enter') focusEntity()\" />
            <button onclick=\"focusEntity()\">Focus Entity</button>
            <button onclick=\"clearEntityFocus()\">Clear Focus</button>
            <span id=\"searchStatus\" class=\"search-status\"></span>
            <a href=\"/data-model-analysis?id={quote(model_id)}\" class=\"muted\">Clear ERD</a>
            <a href=\"/data-model-identifiers?id={quote(model_id)}\" class=\"muted\">Identifier Issues</a>
            <a href=\"/data-model-relationships?id={quote(model_id)}\" class=\"muted\">Relationship Issues</a>
        </div>

        <div class=\"diagram-shell\">
            <div id=\"diagramViewport\">
                <div id=\"diagramLayer\" class=\"mermaid\">{escape(mermaid_markup)}</div>
            </div>
        </div>

        <h3>Entity Details</h3>
        {pagination_html}
        <div id=\"entityGrid\" class=\"grid\">{''.join(entity_cards)}</div>
    </div>

    <script>
        let scale = 1;
        let tx = 0;
        let ty = 0;
        let dragging = false;
        let startX = 0;
        let startY = 0;
        const viewport = document.getElementById('diagramViewport');
        const layer = document.getElementById('diagramLayer');
        const entityGrid = document.getElementById('entityGrid');
        const searchInput = document.getElementById('entitySearch');
        const searchStatus = document.getElementById('searchStatus');

        function applyTransform() {{
            layer.style.transform = `translate(${{tx}}px, ${{ty}}px) scale(${{scale}})`;
        }}
        function zoomIn() {{ scale = Math.min(3, scale + 0.1); applyTransform(); }}
        function zoomOut() {{ scale = Math.max(0.2, scale - 0.1); applyTransform(); }}
        function resetView() {{ scale = 1; tx = 0; ty = 0; applyTransform(); }}
        window.zoomIn = zoomIn;
        window.zoomOut = zoomOut;
        window.resetView = resetView;

        function focusEntity() {{
            const query = (searchInput.value || '').trim().toLowerCase();
            const cards = Array.from(entityGrid.querySelectorAll('.entity-card'));
            cards.forEach((card) => card.classList.remove('match'));
            if (!query) {{
                searchStatus.textContent = '';
                return;
            }}

            const matches = cards.filter((card) => (card.dataset.entity || '').toLowerCase().includes(query));
            searchStatus.textContent = `${{matches.length}} match(es)`;
            if (matches.length === 0) return;

            matches.forEach((card) => card.classList.add('match'));
            matches[0].scrollIntoView({{ behavior: 'smooth', block: 'center' }});

            const svg = layer.querySelector('svg');
            if (!svg) return;
            const targetText = Array.from(svg.querySelectorAll('text')).find((node) => (node.textContent || '').toLowerCase().includes(query));
            if (!targetText) return;
            const graphNode = targetText.closest('g');
            if (!graphNode || !graphNode.getBBox) return;
            const box = graphNode.getBBox();
            tx = Math.max(20, (viewport.clientWidth / 2) - ((box.x + box.width / 2) * scale));
            ty = Math.max(20, (viewport.clientHeight / 2) - ((box.y + box.height / 2) * scale));
            applyTransform();
        }}

        function clearEntityFocus() {{
            const cards = Array.from(entityGrid.querySelectorAll('.entity-card'));
            cards.forEach((card) => card.classList.remove('match'));
            searchInput.value = '';
            searchStatus.textContent = '';
        }}

        window.focusEntity = focusEntity;
        window.clearEntityFocus = clearEntityFocus;

        viewport.addEventListener('wheel', (e) => {{
            e.preventDefault();
            if (e.deltaY < 0) zoomIn(); else zoomOut();
        }}, {{ passive: false }});

        viewport.addEventListener('mousedown', (e) => {{
            dragging = true;
            startX = e.clientX - tx;
            startY = e.clientY - ty;
        }});
        window.addEventListener('mouseup', () => dragging = false);
        window.addEventListener('mousemove', (e) => {{
            if (!dragging) return;
            tx = e.clientX - startX;
            ty = e.clientY - startY;
            applyTransform();
        }});

        async function initMermaid() {{
            const mermaid = window._mermaid;
            if (!mermaid) return;
            mermaid.initialize({{ startOnLoad: true, securityLevel: 'loose', theme: 'default' }});
            await mermaid.run({{ querySelector: '.mermaid' }});
            applyTransform();
        }}
        initMermaid();
    </script>
</body>
</html>
"""


def _render_issue_list_html(
    model_id: str,
    title: str,
    issues: list[dict[str, Any]],
    page: int,
) -> str:
    per_page = 10
    paged, total_pages = _paginate(issues, page, per_page)
    prev_page = max(1, page - 1)
    next_page = min(total_pages, page + 1)
    items_html = "".join(
        "<li>"
        f"<strong>{escape(str(item.get('entity', '')))}</strong><br>"
        f"<span class='muted'>{escape(str(item.get('issue', 'Issue')))}</span><br>"
        f"{escape(str(item.get('description', '')))}"
        "</li>"
        for item in paged
    )
    if not items_html:
        items_html = "<li>No issues found.</li>"

    return f"""
<!doctype html>
<html>
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{escape(title)}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; color: #1f2937; }}
        .wrap {{ padding: 16px; }}
        .pager {{ display: flex; gap: 12px; align-items: center; margin: 8px 0 16px; }}
        .pager a {{ color: #1d4ed8; text-decoration: none; }}
        .muted {{ color: #6b7280; font-size: 12px; }}
        ul {{ padding-left: 18px; }}
        li {{ margin-bottom: 10px; }}
    </style>
</head>
<body>
    <div class=\"wrap\">
        <h2>{escape(title)}</h2>
        <div class=\"pager\">
            <a href=\"?id={quote(model_id)}&page={prev_page}\">Prev</a>
            <span>Page {page} of {total_pages}</span>
            <a href=\"?id={quote(model_id)}&page={next_page}\">Next</a>
            <a href=\"/data-model-analysis?id={quote(model_id)}\">Back to ERD</a>
        </div>
        <ul>{items_html}</ul>
    </div>
</body>
</html>
"""



# All mcp.custom_route, Request, JSONResponse, and HTMLResponse usages stubbed out below.


## Removed duplicate definition; see new version below
def _get_sessions_data(instance: int = 1) -> dict[str, Any]:
    """Fetch current SQL Server session data for a given instance."""
    conn = get_connection(instance=instance)
    try:
        cur = conn.cursor()
        _execute_safe(
            cur,
            """
            SELECT 
                es.session_id,
                es.login_name,
                es.host_name,
                es.program_name,
                es.status AS session_status,
                CONVERT(VARCHAR, es.login_time, 121) AS login_time,
                CONVERT(VARCHAR, es.last_request_end_time, 121) AS last_request_end_time,
                r.command,
                COALESCE(r.status, es.status) AS status,
                r.wait_type,
                r.blocking_session_id,
                CONVERT(VARCHAR, r.start_time, 121) AS start_time,
                DATEDIFF(SECOND, r.start_time, GETUTCDATE()) AS duration_seconds,
                es.cpu_time,
                es.memory_usage
            FROM sys.dm_exec_sessions es
            LEFT JOIN sys.dm_exec_requests r ON es.session_id = r.session_id
            WHERE es.session_id > 50
            ORDER BY r.status DESC, es.session_id
            """,
        )
        
        columns = [desc[0] for desc in cur.description]
        sessions = []
        for row in cur.fetchall():
            session_dict = dict(zip(columns, row))
            sessions.append(session_dict)
        
        active_count = sum(1 for s in sessions if s.get("status") in {"running", "runnable", "suspended"})
        idle_count = len(sessions) - active_count
        blocked_count = sum(1 for s in sessions if (s.get("blocking_session_id") or 0) > 0)
        blocker_count = len({
            int(s.get("blocking_session_id"))
            for s in sessions
            if (s.get("blocking_session_id") or 0) > 0
        })
        
        return {
            "timestamp": _now_utc_iso(),
            "active_sessions": active_count,
            "idle_sessions": idle_count,
            "total_sessions": len(sessions),
            "blocked_sessions": blocked_count,
            "blocking_sessions": blocker_count,
            "sessions": sessions,
        }
    finally:
        conn.close()




# All mcp.custom_route, Request, JSONResponse, and HTMLResponse usages stubbed out below.



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
        run_kwargs: dict[str, Any] = {}

        ssl_cert = SETTINGS.ssl_cert
        ssl_key = SETTINGS.ssl_key
        if ssl_cert or ssl_key:
            if not (ssl_cert and ssl_key):
                raise RuntimeError("Both MCP_SSL_CERT and MCP_SSL_KEY must be set to enable HTTPS.")
            run_kwargs["ssl_certfile"] = ssl_cert
            run_kwargs["ssl_keyfile"] = ssl_key
            logger.info(
                "HTTPS enabled for MCP HTTP transport",
                extra={"ssl_cert": ssl_cert, "ssl_key": ssl_key},
            )

        mcp.run(transport=transport, host=SETTINGS.host, port=SETTINGS.port, **run_kwargs)
    else:
        mcp.run(transport="stdio")


>>>>>>> 26c0f30 (Restore and sync MCP tool registration, dual-instance support, and instance param propagation in server.py)
