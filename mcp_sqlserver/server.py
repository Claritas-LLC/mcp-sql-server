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
