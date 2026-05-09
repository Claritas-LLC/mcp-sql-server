from __future__ import annotations

import json
import pathlib
from typing import Any


def categorize_tool(tool_name: str) -> str:
    if tool_name.endswith("_exec_proc"):
        return "controlled_write"
    if tool_name.endswith("_report"):
        return "diagnostic"
    if "_analyze_" in tool_name:
        return "analysis"
    if tool_name.endswith("_dashboard"):
        return "interactive"
    return "read_only"


def summarize_audit_events(audit_path: pathlib.Path) -> dict[str, Any]:
    if not audit_path.exists():
        return {
            "events": 0,
            "by_category": {},
            "by_tool": {},
            "deny_total": 0,
            "latest": None,
        }

    events = 0
    deny_total = 0
    latest: dict[str, Any] | None = None
    by_category: dict[str, dict[str, int]] = {}
    by_tool: dict[str, dict[str, int]] = {}

    with audit_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            events += 1
            latest = row

            tool = str(row.get("tool", "unknown"))
            decision = str(row.get("decision", "unknown"))
            category = categorize_tool(tool)

            by_tool.setdefault(tool, {"allow": 0, "deny": 0, "unknown": 0})
            by_tool[tool][decision if decision in by_tool[tool] else "unknown"] += 1

            by_category.setdefault(category, {"allow": 0, "deny": 0, "unknown": 0})
            by_category[category][
                decision if decision in by_category[category] else "unknown"
            ] += 1

            if decision == "deny":
                deny_total += 1

    return {
        "events": events,
        "by_category": by_category,
        "by_tool": by_tool,
        "deny_total": deny_total,
        "latest": latest,
    }
