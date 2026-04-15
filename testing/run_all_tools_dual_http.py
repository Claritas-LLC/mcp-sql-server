import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_sqlserver import server


MATRIX_FILE = Path("testing/tool_matrix.json")
RESULTS_DIR = Path("testing/tool_results")
SUMMARY_FILE = Path("testing/tool_execution_summary.json")
DEFECTS_FILE = Path("testing/defect_register.json")


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


def _prepare_args(item: dict[str, Any]) -> dict[str, Any]:
    tool_name = item["tool_name"]
    suffix = item["suffix"]
    args = dict(item.get("args_template", {}))

    if suffix == "kill_session":
        # Resolve current session and kill a different one if available; otherwise validate error-path behavior.
        inst = 1 if tool_name.startswith("db_01_") else 2
        server_info = server.db_sql2019_server_info_mcp(instance=inst)
        spid = server_info.get("spid") if isinstance(server_info, dict) else None
        if isinstance(spid, int):
            args["session_id"] = spid + 100000
        else:
            args["session_id"] = 999999

    allowed = set(item.get("param_names", []))
    if allowed:
        args = {k: v for k, v in args.items() if k in allowed}

    # Fill common defaults only if the tool schema supports them.
    if "database_name" in allowed and "database_name" not in args:
        args["database_name"] = "TEST_DB"
    if "database" in allowed and "database" not in args:
        args["database"] = "TEST_DB"

    return args


async def main() -> None:
    if not MATRIX_FILE.exists():
        raise SystemExit("tool_matrix.json missing. Run testing/generate_tool_matrix.py first.")

    matrix = json.loads(MATRIX_FILE.read_text(encoding="utf-8"))
    entries = matrix["matrix"]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    summary: list[dict[str, Any]] = []
    defects: list[dict[str, Any]] = []

    for item in entries:
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
                        "tool": tool_name,
                        "test_case": "tool_execution",
                        "symptom": error,
                        "root_cause_file": "unknown",
                        "root_cause_function": suffix,
                        "status": "open",
                    }
                )

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        out_file = RESULTS_DIR / f"{tool_name}.json"
        out_file.write_text(
            json.dumps(
                {
                    "tool_name": tool_name,
                    "args": args,
                    "status": status,
                    "duration_ms": duration_ms,
                    "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                    "result": payload,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        summary.append(
            {
                "tool_name": tool_name,
                "instance": "db_01" if tool_name.startswith("db_01_") else "db_02",
                "status": status,
                "duration_ms": duration_ms,
                "result_file": out_file.as_posix(),
                "error": error,
            }
        )

    summary_out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_tools": len(summary),
        "passed": sum(1 for x in summary if x["status"] == "SUCCESS"),
        "failed": sum(1 for x in summary if x["status"] == "FAILED"),
        "tools": summary,
    }
    SUMMARY_FILE.write_text(json.dumps(summary_out, indent=2), encoding="utf-8")
    DEFECTS_FILE.write_text(json.dumps(defects, indent=2), encoding="utf-8")

    print(json.dumps({"summary_file": str(SUMMARY_FILE), "defects_file": str(DEFECTS_FILE), "failed": summary_out["failed"]}, indent=2))

    if summary_out["failed"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
