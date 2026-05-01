"""
nonprod_harness.py — QA read-only validation against non-production SQL Server instances.

Execution Matrix:
  Instance 1 (db_01) | 10.125.1.7:1433 | databases: USGISPRO_800, US_RT_User_800
  Instance 2 (db_02) | 10.125.1.8:1433 | databases: ListGateway, US_UserData

Phases executed:
  1. Pre-flight: ping + read-only check for both instances
  2. Discovery: list_databases + list_tables per database -> nonprod_args_templates.json
  3. Instance-scoped tools: ping, list_databases, server_info_mcp (no db arg)
  4. Database-scoped tools: all 16 remaining read-only suffixes x 4 (prefix, db) combos
  5. Bulk artifact audit: confirm 0 errors across all nonprod_* artifacts
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_sqlserver import server

RESULTS_DIR = Path("testing/tool_results")
DEFECTS_FILE = Path("testing/nonprod_defect_register.json")
EXEC_LOG = Path("testing/nonprod_execution_log.jsonl")
ARGS_TEMPLATES_FILE = Path("testing/nonprod_args_templates.json")
MATRIX_FILE = Path("testing/tool_matrix.json")

# Non-production instance -> databases mapping
INSTANCE_DATABASES: dict[str, list[str]] = {
    "db_01": ["USGISPRO_800", "US_RT_User_800"],
    "db_02": ["ListGateway", "US_UserData"],
}

# Read-only suffixes only (no write tools)
READONLY_SUFFIXES_ORDERED = [
    "ping",
    "list_databases",
    "list_tables",
    "get_schema",
    "execute_query",
    "run_query",
    "list_objects",
    "index_fragmentation",
    "index_health",
    "table_health",
    "db_stats",
    "server_info_mcp",
    "show_top_queries",
    "check_fragmentation",
    "db_sec_perf_metrics",
    "explain_query",
    "analyze_logical_data_model",
    "open_logical_model",
    "generate_ddl",
]

# Suffixes that have no database_name param (instance-scoped)
INSTANCE_SCOPED = {"ping", "list_databases", "server_info_mcp"}

defects: list[dict[str, Any]] = []
exec_log_entries: list[dict[str, Any]] = []
args_templates: dict[str, dict[str, Any]] = {}


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _append_exec_log(entry: dict[str, Any]) -> None:
    with EXEC_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _add_defect(tool_name: str, suffix: str, database: str, symptom: str, root_cause: str = "unknown") -> None:
    defect = {
        "id": f"DEF-{len(defects)+1:03d}",
        "tool_name": tool_name,
        "tool_suffix": suffix,
        "database": database,
        "symptom": symptom,
        "root_cause_file": root_cause,
        "root_cause_function": suffix,
        "status": "open",
        "detected_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    defects.append(defect)
    DEFECTS_FILE.write_text(json.dumps(defects, indent=2), encoding="utf-8")
    _log(f"  DEFECT logged: {defect['id']} — {symptom[:100]}")


def _unwrap(result: Any) -> Any:
    if hasattr(result, "content"):
        content = getattr(result, "content")
        if isinstance(content, list) and len(content) == 1:
            item = content[0]
            if hasattr(item, "text"):
                text = getattr(item, "text")
                if isinstance(text, str):
                    try:
                        return json.loads(text)
                    except Exception:
                        return text
        return content
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return result


async def _call(tool_name: str, args: dict[str, Any]) -> Any:
    raw = await server.mcp.call_tool(tool_name, args)
    return _unwrap(raw)


def _save_artifact(filename: str, tool_name: str, suffix: str, database: str,
                   args: dict[str, Any], status: str, result: Any,
                   duration_ms: float, error: str | None = None) -> Path:
    out_file = RESULTS_DIR / filename
    artifact = {
        "tool_name": tool_name,
        "tool_suffix": suffix,
        "database": database,
        "args": args,
        "status": status,
        "duration_ms": round(duration_ms, 2),
        "error": error,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "result": result,
    }
    out_file.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    return out_file


def _validate_artifact(out_file: Path, tool_name: str, suffix: str, database: str) -> str | None:
    artifact = _load_artifact_json(out_file)
    if not isinstance(artifact, dict):
        return "artifact is not a JSON object"
    if artifact.get("status") != "SUCCESS":
        return f"status={artifact.get('status')}, error={artifact.get('error')}"
    result = artifact.get("result")
    if isinstance(result, dict) and result.get("error"):
        return f"result.error={result['error']}"
    return None


def _load_artifact_json(path: Path) -> dict[str, Any] | Any:
    """Load artifact JSON with recovery for accidental trailing braces."""
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # Some interrupted runs produced a valid object plus a trailing "}".
        decoder = json.JSONDecoder()
        obj, end = decoder.raw_decode(text)
        trailing = text[end:].strip()
        if trailing and set(trailing) <= {"}"}:
            # Normalize the file in place so subsequent reads are clean.
            path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
            return obj
        raise exc


async def _run_tool(tool_name: str, suffix: str, database: str,
                    args: dict[str, Any], filename_prefix: str) -> tuple[bool, Path]:
    filename = f"nonprod_{filename_prefix}_{suffix}.json"
    out_file = RESULTS_DIR / filename
    if out_file.exists():
        validation_error = _validate_artifact(out_file, tool_name, suffix, database)
        if validation_error is None:
            _append_exec_log({
                "tool_name": tool_name, "suffix": suffix, "database": database,
                "status": "SKIPPED_SUCCESS", "duration_ms": 0,
                "artifact": out_file.name,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            })
            _log(f"    [SKIP] {tool_name} db={database} -> {out_file.name} (already SUCCESS)")
            return True, out_file

    started = time.perf_counter()
    status = "SUCCESS"
    error_msg = None
    result = None
    try:
        result = await _call(tool_name, args)
        if isinstance(result, dict) and result.get("error"):
            status = "FAILED"
            error_msg = str(result["error"])
    except Exception as exc:
        status = "FAILED"
        error_msg = str(exc)
        result = {"error": error_msg}
    duration_ms = (time.perf_counter() - started) * 1000
    out_file = _save_artifact(filename, tool_name, suffix, database, args, status, result, duration_ms, error_msg)
    if status != "SUCCESS":
        _add_defect(tool_name, suffix, database, error_msg or "unknown error")
    validation_error = _validate_artifact(out_file, tool_name, suffix, database)
    if validation_error and status == "SUCCESS":
        _add_defect(tool_name, suffix, database, f"artifact validation: {validation_error}")
        status = "FAILED"
    _append_exec_log({
        "tool_name": tool_name, "suffix": suffix, "database": database,
        "status": status, "duration_ms": round(duration_ms, 2),
        "artifact": out_file.name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    })
    icon = "OK" if status == "SUCCESS" else "FAIL"
    _log(f"    [{icon}] {tool_name} db={database} -> {out_file.name} ({duration_ms:.0f}ms)")
    return status == "SUCCESS", out_file


# ── helpers to look up tool metadata from the matrix ──────────────────────────

def _get_matrix_item(matrix: list[dict], tool_name: str) -> dict[str, Any] | None:
    for item in matrix:
        if item["tool_name"] == tool_name:
            return item
    return None


def _build_args(matrix_item: dict, database_name: str, suffix: str,
                instance: int, discovered: dict[str, Any]) -> dict[str, Any]:
    """Build args for a tool call, replacing test-db placeholders with real values."""
    param_names = set(matrix_item.get("param_names", []))
    args: dict[str, Any] = {}

    # instance
    if "instance" in param_names:
        args["instance"] = instance

    # database routing
    if "database_name" in param_names:
        args["database_name"] = database_name
    if "database" in param_names:
        args["database"] = database_name
    if suffix == "run_query" and "arg1" in param_names:
        args["arg1"] = database_name

    # schema
    schema = discovered.get("schema", "dbo")
    table = discovered.get("table", "")
    if "schema" in param_names:
        args["schema"] = schema
    if "schema_name" in param_names:
        args["schema_name"] = schema

    # table
    if "table_name" in param_names and table:
        args["table_name"] = table

    # SQL for query tools
    if suffix in ("execute_query", "explain_query"):
        sql = discovered.get("sql", f"SELECT TOP 5 * FROM [{schema}].[{table}]") if table else "SELECT TOP 5 1 AS n"
        if "sql" in param_names:
            args["sql"] = sql
    if suffix == "run_query" and "arg2" in param_names:
        sql = discovered.get("sql", f"SELECT TOP 5 * FROM [{schema}].[{table}]") if table else "SELECT TOP 5 1 AS n"
        args["arg2"] = sql

    # view defaults
    if "view" in param_names:
        args["view"] = "summary"
    if "object_type" in param_names:
        args["object_type"] = "TABLE"

    # numeric defaults from matrix
    for k in ("min_fragmentation", "min_page_count", "limit", "page", "page_size"):
        if k in param_names:
            tmpl = matrix_item.get("args_template", {})
            if k in tmpl:
                args[k] = tmpl[k]

    return args


# ── Phase 1: Pre-flight ────────────────────────────────────────────────────────

async def phase1_preflight() -> bool:
    _log("=== Phase 1: Pre-flight ===")
    ok = True
    for prefix, instance in [("db_01", 1), ("db_02", 2)]:
        tool = f"{prefix}_ping"
        _log(f"  Pinging {tool} (instance {instance})...")
        args = {"instance": instance}
        started = time.perf_counter()
        try:
            result = await _call(tool, args)
            duration_ms = (time.perf_counter() - started) * 1000
            filename = f"nonprod_preflight_ping_i{instance}.json"
            _save_artifact(filename, tool, "ping", "N/A", args, "SUCCESS", result, duration_ms)
            _log(f"    OK  {filename}")
        except Exception as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            _log(f"    FAIL instance {instance}: {exc}")
            _add_defect(tool, "ping", "N/A", str(exc))
            ok = False
    if not ok:
        _log("  ABORT: One or both instances are unreachable. Fix connectivity before proceeding.")
    return ok


# ── Phase 2: Discovery ─────────────────────────────────────────────────────────

def _strip_brackets(name: str) -> str:
    """Remove surrounding [ ] SQL brackets from an identifier if present."""
    name = name.strip()
    if name.startswith("[") and name.endswith("]"):
        return name[1:-1]
    return name


def _extract_user_schema_table(list_tables_result: Any) -> tuple[str, str]:
    """Extract first user schema and table from list_tables result.

    Handles both paginated format {items: [...]} and flat {tables: [...]} or plain list.
    """
    SYSTEM_SCHEMAS = {"sys", "information_schema", "guest", "db_owner", "db_accessadmin",
                      "db_securityadmin", "db_ddladmin", "db_backupoperator", "db_datareader",
                      "db_datawriter", "db_denydatareader", "db_denydatawriter"}
    tables: list = []
    if isinstance(list_tables_result, dict):
        # paginated: {items: [...], pagination: {...}}
        tables = list_tables_result.get("items", [])
        if not tables:
            tables = list_tables_result.get("tables", [])
    elif isinstance(list_tables_result, list):
        tables = list_tables_result

    def _raw_name(t: dict) -> str:
        return (t.get("table_name") or t.get("name") or t.get("TABLE_NAME") or "").strip()

    def _is_plain(raw: str) -> bool:
        """Skip table names that have literal [ or ] in them — they need complex escaping."""
        return "[" not in raw and "]" not in raw

    # First pass: user schema, plain identifier
    for t in tables:
        raw = _raw_name(t)
        schema = _strip_brackets((t.get("schema_name") or t.get("schema") or t.get("TABLE_SCHEMA") or "dbo").strip())
        name = _strip_brackets(raw)
        if schema.lower() not in SYSTEM_SCHEMAS and name and _is_plain(raw):
            return schema, name

    # Second pass: any schema, plain identifier
    for t in tables:
        raw = _raw_name(t)
        schema = _strip_brackets((t.get("schema_name") or t.get("schema") or t.get("TABLE_SCHEMA") or "dbo").strip())
        name = _strip_brackets(raw)
        if name and _is_plain(raw):
            return schema, name

    # Final fallback: any table even with brackets (generates bracketed SQL)
    for t in tables:
        raw = _raw_name(t)
        schema = _strip_brackets((t.get("schema_name") or t.get("schema") or t.get("TABLE_SCHEMA") or "dbo").strip())
        name = _strip_brackets(raw)
        if name:
            return schema, name
    return "dbo", ""


async def phase2_discovery(matrix: list[dict]) -> dict[str, dict[str, Any]]:
    _log("=== Phase 2: Discovery ===")
    templates: dict[str, dict[str, Any]] = {}

    for prefix, instance, databases in [
        ("db_01", 1, INSTANCE_DATABASES["db_01"]),
        ("db_02", 2, INSTANCE_DATABASES["db_02"]),
    ]:
        # list_databases
        tool = f"{prefix}_list_databases"
        _log(f"  {tool}...")
        try:
            result = await _call(tool, {"instance": instance})
            fname = f"nonprod_{prefix}_list_databases.json"
            _save_artifact(fname, tool, "list_databases", "N/A", {"instance": instance}, "SUCCESS", result, 0)
            _log(f"    Saved {fname}")
        except Exception as exc:
            _log(f"    WARN: {exc}")

        # list_tables per database
        for db in databases:
            key = f"{prefix}_{db}"
            _log(f"  list_tables for {key}...")
            args = {"instance": instance, "database_name": db}
            try:
                result = await _call(f"{prefix}_list_tables", args)
                fname = f"nonprod_{prefix}_{db}_list_tables_discovery.json"
                _save_artifact(fname, f"{prefix}_list_tables", "list_tables", db, args, "SUCCESS", result, 0)
                schema, table = _extract_user_schema_table(result)
                sql = f"SELECT TOP 5 * FROM [{schema}].[{table}]" if table else "SELECT TOP 5 1 AS n"
                templates[key] = {
                    "prefix": prefix,
                    "instance": instance,
                    "database_name": db,
                    "schema": schema,
                    "table": table,
                    "sql": sql,
                }
                _log(f"    schema={schema!r} table={table!r}")
            except Exception as exc:
                _log(f"    WARN: {exc} — using fallback")
                templates[key] = {
                    "prefix": prefix, "instance": instance,
                    "database_name": db, "schema": "dbo", "table": "",
                    "sql": "SELECT TOP 5 1 AS n",
                }
                _add_defect(f"{prefix}_list_tables", "list_tables", db, str(exc))

    ARGS_TEMPLATES_FILE.write_text(json.dumps(templates, indent=2), encoding="utf-8")
    _log(f"  Saved {ARGS_TEMPLATES_FILE} with {len(templates)} entries")
    return templates


# ── Phases 3 + 4: Execute tools ───────────────────────────────────────────────

async def run_readonly_tools(matrix: list[dict], templates: dict) -> dict[str, Any]:
    _log("=== Phase 3 + 4: Executing read-only tools ===")
    totals = {"passed": 0, "failed": 0}

    for suffix in READONLY_SUFFIXES_ORDERED:
        _log(f"  --- Suffix: {suffix} ---")

        if suffix in INSTANCE_SCOPED:
            # Run once per instance, no database arg
            for prefix, instance in [("db_01", 1), ("db_02", 2)]:
                tool_name = f"{prefix}_{suffix}"
                matrix_item = _get_matrix_item(matrix, tool_name)
                if not matrix_item:
                    _log(f"    SKIP {tool_name} (not in matrix)")
                    continue
                param_names = set(matrix_item.get("param_names", []))
                args = {"instance": instance} if "instance" in param_names else {}
                fname_prefix = f"{prefix}_instance{instance}"
                ok, _ = await _run_tool(tool_name, suffix, "N/A", args, fname_prefix)
                if ok:
                    totals["passed"] += 1
                else:
                    totals["failed"] += 1
        else:
            # Run for each (prefix, database) combination
            pairs = [
                ("db_01", 1, INSTANCE_DATABASES["db_01"]),
                ("db_02", 2, INSTANCE_DATABASES["db_02"]),
            ]
            suffix_ok = True
            for prefix, instance, databases in pairs:
                for db in databases:
                    tool_name = f"{prefix}_{suffix}"
                    matrix_item = _get_matrix_item(matrix, tool_name)
                    if not matrix_item:
                        _log(f"    SKIP {tool_name} (not in matrix)")
                        continue
                    key = f"{prefix}_{db}"
                    disc = templates.get(key, {"schema": "dbo", "table": "", "sql": "SELECT TOP 5 1 AS n"})
                    args = _build_args(matrix_item, db, suffix, instance, disc)
                    fname_prefix = f"{prefix}_{db}"
                    ok, _ = await _run_tool(tool_name, suffix, db, args, fname_prefix)
                    if ok:
                        totals["passed"] += 1
                    else:
                        totals["failed"] += 1
                        suffix_ok = False

            if not suffix_ok:
                _log(f"  HALT: errors in suffix {suffix!r}. Open defects: {sum(1 for d in defects if d['status']=='open')}. Fix required before continuing.")
                # continue anyway to collect all errors in one run (plan phase 5 handles remediation)

        _append_exec_log({
            "event": "suffix_complete", "suffix": suffix,
            "open_defects": sum(1 for d in defects if d["status"] == "open"),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        })

    return totals


# ── Phase 5: Bulk audit ────────────────────────────────────────────────────────

def phase5_audit() -> dict[str, Any]:
    _log("=== Phase 5: Bulk artifact audit ===")
    nonprod_files = list(RESULTS_DIR.glob("nonprod_*.json"))
    errors = []
    for f in nonprod_files:
        try:
            data = _load_artifact_json(f)
            if data.get("status") != "SUCCESS" or (isinstance(data.get("result"), dict) and data["result"].get("error")):
                errors.append(f.name)
        except Exception as exc:
            errors.append(f"{f.name} (parse error: {exc})")

    _log(f"  Total nonprod artifacts: {len(nonprod_files)}")
    _log(f"  Artifacts with errors: {len(errors)}")
    if errors:
        for e in errors[:20]:
            _log(f"    {e}")
    return {"total": len(nonprod_files), "errors": len(errors), "error_files": errors}


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    DEFECTS_FILE.write_text("[]", encoding="utf-8")
    EXEC_LOG.write_text("", encoding="utf-8")

    matrix_data = json.loads(MATRIX_FILE.read_text(encoding="utf-8"))
    readonly_matrix = [e for e in matrix_data["matrix"] if e["classification"] == "read"]

    # Phase 1
    ok = await phase1_preflight()
    if not ok:
        _log("ABORT: Pre-flight failed.")
        sys.exit(1)

    # Phase 2
    templates = await phase2_discovery(readonly_matrix)

    # Phase 3 + 4
    totals = await run_readonly_tools(readonly_matrix, templates)
    _log(f"  Tool execution complete: passed={totals['passed']} failed={totals['failed']}")

    # Phase 5: bulk audit
    audit = phase5_audit()

    # Final summary
    open_defects = sum(1 for d in defects if d["status"] == "open")
    summary = {
        "event": "final_summary",
        "total_units_attempted": totals["passed"] + totals["failed"],
        "passed": totals["passed"],
        "failed": totals["failed"],
        "open_defects": open_defects,
        "total_artifacts": audit["total"],
        "artifacts_with_errors": audit["errors"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    _append_exec_log(summary)
    _log(f"=== DONE: passed={totals['passed']} failed={totals['failed']} open_defects={open_defects} artifacts={audit['total']} artifact_errors={audit['errors']} ===")

    if open_defects > 0:
        _log(f"  Open defects remain — see {DEFECTS_FILE}")
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
