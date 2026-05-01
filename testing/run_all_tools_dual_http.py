import asyncio
import json
import sys
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_sqlserver import server


MATRIX_FILE = Path("testing/tool_matrix.json")
RESULTS_DIR = Path("testing/tool_results")
SUMMARY_FILE = Path("testing/tool_execution_summary.json")
DEFECTS_FILE = Path("testing/defect_register.json")
INSTANCE_DATABASES = {
    "db_01": "test1",
    "db_02": "test2",
}
PAIR_ORDER = {
    "ping": 10,
    "list_databases": 20,
    "list_tables": 30,
    "get_schema": 40,
    "execute_query": 50,
    "run_query": 60,
    "list_objects": 70,
    "index_fragmentation": 80,
    "index_health": 90,
    "table_health": 100,
    "db_stats": 110,
    "server_info_mcp": 120,
    "show_top_queries": 130,
    "check_fragmentation": 140,
    "db_sec_perf_metrics": 150,
    "explain_query": 160,
    "analyze_logical_data_model": 170,
    "open_logical_model": 180,
    "generate_ddl": 190,
    "create_db_user": 200,
    "drop_db_user": 210,
    "kill_session": 220,
    "create_object": 230,
    "alter_object": 240,
    "drop_object": 250,
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    if hasattr(value, "text") and not isinstance(value, (str, bytes)):
        return {"text": str(getattr(value, "text"))}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


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
        return _jsonable(content)
    return _jsonable(result)


async def _call_tool(name: str, args: dict[str, Any]) -> Any:
    return await server.mcp.call_tool(name, args)


def _instance_prefix(tool_name: str) -> str:
    return "db_01" if tool_name.startswith("db_01_") else "db_02"


def _expected_database(tool_name: str) -> str:
    return INSTANCE_DATABASES[_instance_prefix(tool_name)]


def _prepare_args(item: dict[str, Any]) -> dict[str, Any]:
    tool_name = item["tool_name"]
    suffix = item["suffix"]
    args = dict(item.get("args_template", {}))
    expected_database = _expected_database(tool_name)

    if suffix == "kill_session":
        inst = 1 if tool_name.startswith("db_01_") else 2
        server_info = server.db_sql2019_server_info_mcp(instance=inst)
        spid = server_info.get("spid") if isinstance(server_info, dict) else None
        args["session_id"] = spid + 100000 if isinstance(spid, int) else 999999

    allowed = set(item.get("param_names", []))
    if allowed:
        args = {k: v for k, v in args.items() if k in allowed}

    if "database_name" in allowed and "database_name" not in args:
        args["database_name"] = expected_database
    if "database" in allowed and "database" not in args:
        args["database"] = expected_database
    if suffix == "run_query" and "arg1" in allowed and "arg1" not in args:
        args["arg1"] = expected_database

    return args


def _artifact_database(data: dict[str, Any]) -> str | None:
    args = data.get("args", {}) if isinstance(data, dict) else {}
    result = data.get("result", {}) if isinstance(data, dict) else {}

    for key in ("database_name", "database", "arg1"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value

    if isinstance(result, dict):
        for key in ("database", "DatabaseName"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
        table_info = result.get("table_info")
        if isinstance(table_info, dict):
            for key in ("database", "DatabaseName"):
                value = table_info.get(key)
                if isinstance(value, str) and value:
                    return value

    return None


def _validate_artifact(item: dict[str, Any], out_file: Path) -> str | None:
    artifact = json.loads(out_file.read_text(encoding="utf-8"))
    if artifact.get("status") != "SUCCESS":
        return f"Artifact {out_file.name} has status {artifact.get('status')}"

    result = artifact.get("result")
    if isinstance(result, dict) and result.get("error"):
        return f"Artifact {out_file.name} contains error: {result['error']}"

    expected_database = _expected_database(item["tool_name"])
    observed_database = _artifact_database(artifact)
    if observed_database and observed_database.lower() != expected_database.lower():
        return (
            f"Artifact {out_file.name} resolved to unexpected database {observed_database!r}; "
            f"expected {expected_database!r}"
        )

    return None


def _group_suffix_pairs(entries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    ordered: OrderedDict[str, dict[str, dict[str, Any]]] = OrderedDict()
    for entry in entries:
        suffix = entry["suffix"]
        prefix = _instance_prefix(entry["tool_name"])
        ordered.setdefault(suffix, {})[prefix] = entry

    pairs: list[list[dict[str, Any]]] = []
    sorted_suffixes = sorted(
        ordered.keys(),
        key=lambda suffix: (PAIR_ORDER.get(suffix, 10_000), suffix),
    )
    for suffix in sorted_suffixes:
        grouped = ordered[suffix]
        if "db_01" not in grouped or "db_02" not in grouped:
            raise RuntimeError(f"Missing dual-instance pair for suffix {suffix}")
        pairs.append([grouped["db_01"], grouped["db_02"]])
    return pairs


async def _execute_tool(item: dict[str, Any], defects: list[dict[str, Any]]) -> tuple[dict[str, Any], Path]:
    tool_name = item["tool_name"]
    suffix = item["suffix"]
    args = _prepare_args(item)
    started = time.perf_counter()
    status = "SUCCESS"
    error = None
    payload: Any = None

    try:
        result = await _call_tool(tool_name, args)
        payload = _unwrap(result)
    except Exception as exc:
        error = str(exc)
        payload = {"error": error}
        if suffix == "kill_session" and ("process ID" in error or "not an active process" in error):
            status = "SUCCESS"
        else:
            status = "FAILED"
            defects.append(
                {
                    "id": f"DEF-{len(defects)+1:03d}",
                    "tool_suffix": suffix,
                    "tool_name": tool_name,
                    "test_case": "tool_execution",
                    "symptom": error,
                    "root_cause_file": "unknown",
                    "root_cause_function": suffix,
                    "status": "open",
                }
            )

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    out_file = RESULTS_DIR / f"{tool_name}.json"
    artifact = {
        "tool_name": tool_name,
        "tool_suffix": suffix,
        "instance": _instance_prefix(tool_name),
        "args": args,
        "status": status,
        "duration_ms": duration_ms,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "result": payload,
    }
    out_file.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    return artifact, out_file


async def main() -> None:
    if not MATRIX_FILE.exists():
        raise SystemExit("tool_matrix.json missing. Run testing/generate_tool_matrix.py first.")

    matrix = json.loads(MATRIX_FILE.read_text(encoding="utf-8"))
    suffix_pairs = _group_suffix_pairs(matrix["matrix"])
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    summary: list[dict[str, Any]] = []
    pair_summaries: list[dict[str, Any]] = []
    defects: list[dict[str, Any]] = []
    halted_suffix: str | None = None

    for pair in suffix_pairs:
        suffix = pair[0]["suffix"]
        pair_records: list[dict[str, Any]] = []
        pair_files: list[tuple[dict[str, Any], Path]] = []

        for item in pair:
            artifact, out_file = await _execute_tool(item, defects)
            pair_files.append((item, out_file))
            pair_records.append(
                {
                    "tool_name": artifact["tool_name"],
                    "instance": artifact["instance"],
                    "status": artifact["status"],
                    "duration_ms": artifact["duration_ms"],
                    "result_file": str(out_file).replace('\\', '/'),
                    "error": artifact.get("result", {}).get("error") if isinstance(artifact.get("result"), dict) else None,
                }
            )
            summary.append(pair_records[-1])
            if artifact["status"] != "SUCCESS":
                halted_suffix = suffix
                break

        validation_errors: list[str] = []
        if halted_suffix is None:
            for item, out_file in pair_files:
                validation_error = _validate_artifact(item, out_file)
                if validation_error:
                    validation_errors.append(validation_error)

        pair_status = "SUCCESS" if not validation_errors and halted_suffix is None else "FAILED"
        if validation_errors:
            halted_suffix = suffix
            for validation_error in validation_errors:
                defects.append(
                    {
                        "id": f"DEF-{len(defects)+1:03d}",
                        "tool_suffix": suffix,
                        "tool_name": f"pair:{suffix}",
                        "test_case": "artifact_validation",
                        "symptom": validation_error,
                        "root_cause_file": "testing/run_all_tools_dual_http.py",
                        "root_cause_function": "_validate_artifact",
                        "status": "open",
                    }
                )

        pair_summary = {
            "suffix": suffix,
            "status": pair_status,
            "tools": pair_records,
            "validation_errors": validation_errors,
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        pair_file = RESULTS_DIR / f"pair_{suffix}.json"
        pair_file.write_text(json.dumps(pair_summary, indent=2), encoding="utf-8")
        pair_summary["pair_file"] = str(pair_file).replace('\\', '/')
        pair_summaries.append(pair_summary)

        if halted_suffix is not None:
            break

    summary_out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_tools": len(summary),
        "passed": sum(1 for x in summary if x["status"] == "SUCCESS"),
        "failed": sum(1 for x in summary if x["status"] == "FAILED"),
        "halted_suffix": halted_suffix,
        "pairs": pair_summaries,
        "tools": summary,
    }
    SUMMARY_FILE.write_text(json.dumps(summary_out, indent=2), encoding="utf-8")
    DEFECTS_FILE.write_text(json.dumps(defects, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "summary_file": str(SUMMARY_FILE),
                "defects_file": str(DEFECTS_FILE),
                "failed": summary_out["failed"],
                "halted_suffix": halted_suffix,
            },
            indent=2,
        )
    )

    if halted_suffix is not None or summary_out["failed"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
