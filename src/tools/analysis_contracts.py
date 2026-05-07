from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

Severity = Literal["critical", "high", "medium", "low", "info"]


_VALID_SEVERITIES: tuple[Severity, ...] = ("critical", "high", "medium", "low", "info")


def _normalize_severity(value: str) -> Severity:
    normalized = value.strip().lower()
    if normalized not in _VALID_SEVERITIES:
        raise ValueError(f"INVALID_INPUT: unsupported severity '{value}'")
    return normalized  # type: ignore[return-value]


def build_finding(*, code: str, severity: str, title: str, detail: str, evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "severity": _normalize_severity(severity),
        "title": title,
        "detail": detail,
        "evidence": evidence or [],
    }


def build_recommendation(*, priority: str, action: str, rationale: str) -> dict[str, str]:
    return {
        "priority": _normalize_severity(priority),
        "action": action,
        "rationale": rationale,
    }


def build_report_envelope(
    *,
    instance_number: int,
    database_name: str,
    tool_name: str,
    summary: dict[str, Any],
    findings: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    severity_counts = {name: 0 for name in _VALID_SEVERITIES}
    for finding in findings:
        sev = str(finding.get("severity", "info"))
        if sev not in severity_counts:
            sev = "info"
        severity_counts[sev] += 1

    return {
        "instance_number": instance_number,
        "database_name": database_name,
        "tool": tool_name,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "severity_counts": severity_counts,
        "findings": findings,
        "recommendations": recommendations,
    }
