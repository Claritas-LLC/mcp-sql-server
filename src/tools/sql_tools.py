from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time
import uuid
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastmcp import Context, FastMCP
from fastmcp.server.dependencies import get_access_token
from fastmcp.utilities.logging import get_logger

from src.diagnostics.routes import REQUEST_COUNT, REQUEST_LATENCY
from src.security.privilege_mapper import resolve_group_privilege
from src.tools.analysis_contracts import (
    build_finding,
    build_recommendation,
    build_report_envelope,
)
from src.tools.dashboard_payloads import build_sessions_dashboard_full
from src.tools.dashboard_page_store import (
    get_dashboard_page_expiry_utc,
    register_dashboard_page_with_metadata,
)
from src.tools.input_validation import (
    validate_database_name,
    validate_identifier,
    validate_positive_int,
)
from src.tools.model_graph import build_fk_graph
from src.tools.query_catalog import (
    active_sessions_query,
    backup_recency_query,
    blocking_chain_query,
    database_statistics_settings_query,
    datatype_inconsistency_query,
    elevated_roles_query,
    fk_graph_query,
    fragmented_indexes_query,
    lock_chain_query,
    low_sampled_statistics_query,
    missing_fk_index_query,
    missing_statistics_coverage_candidate_query,
    missing_index_dmv_query,
    missing_pk_query,
    normalization_column_overlap_query,
    orphan_user_query,
    redundant_indexes_query,
    soft_delete_columns_query,
    stale_statistics_query,
    statistics_histogram_query,
    statistics_never_updated_query,
    table_size_query,
    top_statements_dmv_fallback_query,
    top_statements_object_pressure_query,
    top_statements_query_store_query,
    tran_locks_query,
    update_heavy_tables_query,
    unused_indexes_query,
    waiting_tasks_query,
)
from src.tools.security_redaction import redact_sensitive_fields
from src.tools.tool_flags import is_tool_enabled
from src.tools.tool_registry import generate_tool_specs

# Server-side logging
logger = get_logger(__name__)


STATS_MIN_ROWS_FOR_STALENESS = 1000
STATS_MIN_MOD_COUNT = 500
STATS_MOD_RATIO_MEDIUM = 0.20
STATS_MOD_RATIO_HIGH = 0.35
STATS_DAYS_STALE_MEDIUM = 30
STATS_DAYS_STALE_HIGH = 90
STATS_MIN_ROWS_HIGH_SEVERITY = 100000
STATS_MIN_MOD_COUNT_HIGH = 20000

STATS_LOW_SAMPLE_LOW = 0.10
STATS_LOW_SAMPLE_MEDIUM = 0.05
STATS_LOW_SAMPLE_HIGH = 0.01
STATS_MIN_ROWS_FOR_SAMPLING = 10000


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_utc_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _filter_rows_by_schema_table(
    rows: list[dict[str, Any]],
    schema_name: str | None,
    table_name: str | None,
) -> list[dict[str, Any]]:
    filtered = rows
    if schema_name:
        schema_filter = schema_name.lower()
        filtered = [
            r for r in filtered if str(r.get("schema_name", "")).lower() == schema_filter
        ]
    if table_name:
        table_filter = table_name.lower()
        filtered = [
            r for r in filtered if str(r.get("table_name", "")).lower() == table_filter
        ]
    return filtered


def _classify_stale_statistics_row(
    row: dict[str, Any], now_utc: datetime | None = None
) -> dict[str, Any] | None:
    rows_total = _safe_float(row.get("rows"))
    modification_counter = _safe_float(row.get("modification_counter"))
    if rows_total < STATS_MIN_ROWS_FOR_STALENESS:
        return None

    now = now_utc or datetime.now(timezone.utc)
    last_updated = _parse_utc_datetime(row.get("last_updated"))
    days_since_update = (now - last_updated).days if last_updated else None
    mod_ratio = (modification_counter / rows_total) if rows_total > 0 else 0.0

    is_stale = (
        modification_counter
        >= max(STATS_MIN_MOD_COUNT, STATS_MOD_RATIO_MEDIUM * rows_total)
    ) or (
        days_since_update is not None and days_since_update >= STATS_DAYS_STALE_MEDIUM
    )
    if not is_stale:
        return None

    is_high = (
        modification_counter
        >= max(STATS_MIN_MOD_COUNT_HIGH, STATS_MOD_RATIO_HIGH * rows_total)
    ) or (
        days_since_update is not None
        and days_since_update >= STATS_DAYS_STALE_HIGH
        and rows_total >= STATS_MIN_ROWS_HIGH_SEVERITY
    )

    enriched = dict(row)
    enriched["severity"] = "high" if is_high else "medium"
    enriched["modification_ratio"] = round(mod_ratio, 4)
    enriched["days_since_update"] = days_since_update
    return enriched


def _classify_low_sample_statistics_row(row: dict[str, Any]) -> dict[str, Any] | None:
    rows_total = _safe_float(row.get("rows"))
    rows_sampled = _safe_float(row.get("rows_sampled"))
    if rows_total < STATS_MIN_ROWS_FOR_SAMPLING or rows_total <= 0:
        return None

    sample_ratio = rows_sampled / rows_total
    if sample_ratio >= STATS_LOW_SAMPLE_LOW:
        return None

    severity = "high" if sample_ratio < STATS_LOW_SAMPLE_HIGH else "medium"
    enriched = dict(row)
    enriched["severity"] = severity
    enriched["sample_ratio"] = round(sample_ratio, 4)
    return enriched


def _sanitize_dashboard_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except Exception:
        return "<invalid-url>"
    parts = [p for p in parsed.path.split("/") if p]
    if parts:
        parts[-1] = "<request-id>"
    safe_path = "/" + "/".join(parts) if parts else "/"
    return urlunsplit((parsed.scheme, parsed.netloc, safe_path, "", ""))


# ---------------------------------------------------------------------------
# Private async subtool helpers – used exclusively by _analyze_db_data_model
# ---------------------------------------------------------------------------


async def _subtool_analyze_indexes(
    db_name: str,
    instance_id: str,
    connection_manager: Any,
    schema_filter: str | None,
    request_id: str,
    ctx: Context | None,
) -> dict[str, Any]:
    """Detect missing (DMV + FK), redundant, and unused nonclustered indexes."""
    findings: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []
    missing_optimizer_count = 0
    missing_fk_count = 0
    redundant_count = 0
    unused_count = 0

    # 1. Missing indexes from query optimizer DMVs
    try:
        if ctx is not None:
            await ctx.debug(
                f"[{request_id}] Subtool: missing index DMV scan",
                extra={"request_id": request_id, "db": db_name},
            )
        result = await asyncio.to_thread(
            connection_manager.execute_catalog_query,
            instance_id,
            db_name,
            missing_index_dmv_query(50),
            50,
        )
        rows = result["rows"]
        if schema_filter:
            rows = [
                r
                for r in rows
                if str(r.get("schema_name", "")).lower() == schema_filter.lower()
            ]
        missing_optimizer_count = len(rows)
        if rows:
            sev = "high" if missing_optimizer_count >= 5 else "medium"
            findings.append(
                build_finding(
                    code="INDEX_MISSING_QUERY",
                    severity=sev,
                    title=f"{missing_optimizer_count} missing index(es) identified by SQL Server optimizer",
                    detail=(
                        "SQL Server DMV analysis detected indexes whose creation would significantly "
                        "reduce query cost. Sorted by estimated_impact descending."
                    ),
                    evidence=[
                        {
                            "table": f"{r.get('schema_name', '')}.{r.get('table_name', '')}",
                            "equality_columns": r.get("equality_columns"),
                            "inequality_columns": r.get("inequality_columns"),
                            "included_columns": r.get("included_columns"),
                            "estimated_impact": r.get("estimated_impact"),
                        }
                        for r in rows[:10]
                    ],
                )
            )
            recommendations.append(
                build_recommendation(
                    priority=sev,
                    action="Create the top missing indexes (highest estimated_impact first). Validate impact in non-production before applying to production.",
                    rationale="Missing indexes cause full or partial scans, increasing I/O, CPU, and query latency under load.",
                )
            )
    except Exception as exc:
        if ctx is not None:
            await ctx.warning(
                f"[{request_id}] Subtool: missing index DMV query unavailable: {exc}",
                extra={"request_id": request_id},
            )
        logger.warning(f"Transaction {request_id}: missing index DMV skipped: {exc}")

    # 2. FK columns without a supporting index
    try:
        result = await asyncio.to_thread(
            connection_manager.execute_catalog_query,
            instance_id,
            db_name,
            missing_fk_index_query(),
            200,
        )
        rows = result["rows"]
        if schema_filter:
            rows = [
                r
                for r in rows
                if str(r.get("parent_schema", "")).lower() == schema_filter.lower()
            ]
        missing_fk_count = len(rows)
        if rows:
            findings.append(
                build_finding(
                    code="INDEX_MISSING_FK",
                    severity="medium",
                    title=f"{missing_fk_count} FK column(s) lack a supporting index",
                    detail="Foreign key columns without an index force full scans during joins, cascade deletes, and parent updates.",
                    evidence=[
                        {
                            "table": f"{r.get('parent_schema', '')}.{r.get('parent_table', '')}",
                            "fk_column": r.get("fk_column"),
                            "constraint": r.get("fk_constraint_name"),
                        }
                        for r in rows[:20]
                    ],
                )
            )
            recommendations.append(
                build_recommendation(
                    priority="medium",
                    action="Create a nonclustered index on each FK column listed in the evidence.",
                    rationale="Indexed FK columns reduce lookup cost during joins, cascades, and parent-row deletes.",
                )
            )
    except Exception as exc:
        if ctx is not None:
            await ctx.warning(
                f"[{request_id}] Subtool: FK index analysis failed: {exc}",
                extra={"request_id": request_id},
            )
        logger.warning(f"Transaction {request_id}: FK index scan skipped: {exc}")

    # 3. Redundant index pairs sharing the same leading key column
    try:
        result = await asyncio.to_thread(
            connection_manager.execute_catalog_query,
            instance_id,
            db_name,
            redundant_indexes_query(100),
            100,
        )
        rows = result["rows"]
        if schema_filter:
            rows = [
                r
                for r in rows
                if str(r.get("schema_name", "")).lower() == schema_filter.lower()
            ]
        redundant_count = len(rows)
        if rows:
            findings.append(
                build_finding(
                    code="INDEX_REDUNDANT",
                    severity="low",
                    title=f"{redundant_count} redundant index pair(s) detected",
                    detail="Index pairs sharing the same leading key column add write overhead without additional read benefit.",
                    evidence=[
                        {
                            "table": f"{r.get('schema_name', '')}.{r.get('table_name', '')}",
                            "index_a": r.get("index_a"),
                            "index_b": r.get("index_b"),
                            "shared_leading_key": r.get("shared_leading_key_column"),
                        }
                        for r in rows[:20]
                    ],
                )
            )
            recommendations.append(
                build_recommendation(
                    priority="low",
                    action="Review each redundant pair; remove the less selective index after confirming no exclusive usage.",
                    rationale="Redundant indexes increase INSERT/UPDATE/DELETE maintenance cost and waste storage.",
                )
            )
    except Exception as exc:
        if ctx is not None:
            await ctx.warning(
                f"[{request_id}] Subtool: redundant index analysis failed: {exc}",
                extra={"request_id": request_id},
            )
        logger.warning(f"Transaction {request_id}: redundant index scan skipped: {exc}")

    # 4. Unused nonclustered indexes (never read since last restart, but still maintained)
    try:
        result = await asyncio.to_thread(
            connection_manager.execute_catalog_query,
            instance_id,
            db_name,
            unused_indexes_query(100),
            100,
        )
        rows = result["rows"]
        if schema_filter:
            rows = [
                r
                for r in rows
                if str(r.get("schema_name", "")).lower() == schema_filter.lower()
            ]
        unused_count = len(rows)
        if rows:
            findings.append(
                build_finding(
                    code="INDEX_UNUSED",
                    severity="low",
                    title=f"{unused_count} unused nonclustered index(es) detected",
                    detail="Indexes with zero reads but positive write counts incur maintenance cost with no query benefit.",
                    evidence=[
                        {
                            "table": f"{r.get('schema_name', '')}.{r.get('table_name', '')}",
                            "index": r.get("index_name"),
                            "total_writes": r.get("total_writes"),
                        }
                        for r in rows[:20]
                    ],
                )
            )
            recommendations.append(
                build_recommendation(
                    priority="low",
                    action="Confirm index is unnecessary after a full workload cycle, then drop unused indexes.",
                    rationale="Unused indexes waste I/O on every write and consume storage without improving any query.",
                )
            )
    except Exception as exc:
        if ctx is not None:
            await ctx.warning(
                f"[{request_id}] Subtool: unused index analysis failed: {exc}",
                extra={"request_id": request_id},
            )
        logger.warning(f"Transaction {request_id}: unused index scan skipped: {exc}")

    return {
        "findings": findings,
        "recommendations": recommendations,
        "summary": {
            "missing_optimizer_count": missing_optimizer_count,
            "missing_fk_index_count": missing_fk_count,
            "redundant_count": redundant_count,
            "unused_count": unused_count,
        },
    }


async def _subtool_analyze_normalization(
    db_name: str,
    instance_id: str,
    connection_manager: Any,
    schema_filter: str | None,
    request_id: str,
    ctx: Context | None,
) -> dict[str, Any]:
    """Detect 3NF violations: transitive dependencies via column-name overlap across FK relationships."""
    findings: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []
    transitive_count = 0

    try:
        if ctx is not None:
            await ctx.debug(
                f"[{request_id}] Subtool: normalization column-overlap scan",
                extra={"request_id": request_id, "db": db_name},
            )
        result = await asyncio.to_thread(
            connection_manager.execute_catalog_query,
            instance_id,
            db_name,
            normalization_column_overlap_query(),
            200,
        )
        rows = result["rows"]
        if schema_filter:
            rows = [
                r
                for r in rows
                if str(r.get("child_schema", "")).lower() == schema_filter.lower()
                or str(r.get("parent_schema", "")).lower() == schema_filter.lower()
            ]

        # Group by child_table to aggregate overlapping columns
        table_map: dict[str, list[str]] = {}
        for r in rows:
            key = f"{r.get('child_schema', '')}.{r.get('child_table', '')}"
            table_map.setdefault(key, []).append(str(r.get("overlapping_column", "")))

        transitive_count = len(table_map)
        if table_map:
            sev = "medium" if transitive_count >= 3 else "low"
            findings.append(
                build_finding(
                    code="NORM_VIOLATION_TRANSITIVE",
                    severity=sev,
                    title=f"{transitive_count} table(s) with potential transitive dependency (3NF violation)",
                    detail=(
                        "These child tables contain non-key columns whose names match non-key columns in the "
                        "referenced parent table. This pattern suggests denormalized copies that violate 3NF."
                    ),
                    evidence=[
                        {"table": tbl, "overlapping_columns": cols}
                        for tbl, cols in list(table_map.items())[:15]
                    ],
                )
            )
            recommendations.append(
                build_recommendation(
                    priority=sev,
                    action=(
                        "Review overlapping columns per table. If the child table duplicates data from the parent, "
                        "remove the copy and rely on the FK join to retrieve parent attributes."
                    ),
                    rationale=(
                        "Denormalized copies of parent attributes create update anomalies: "
                        "a change in the parent must be propagated to every child row manually."
                    ),
                )
            )
    except Exception as exc:
        if ctx is not None:
            await ctx.warning(
                f"[{request_id}] Subtool: normalization analysis failed: {exc}",
                extra={"request_id": request_id},
            )
        logger.warning(f"Transaction {request_id}: normalization scan skipped: {exc}")

    return {
        "findings": findings,
        "recommendations": recommendations,
        "summary": {"transitive_dependency_tables": transitive_count},
    }


async def _subtool_analyze_anomalies(
    db_name: str,
    instance_id: str,
    connection_manager: Any,
    schema_filter: str | None,
    request_id: str,
    ctx: Context | None,
) -> dict[str, Any]:
    """Detect update, delete, and insert anomalies in data lifecycle patterns."""
    findings: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []
    update_anomaly_count = 0
    delete_anomaly_count = 0
    insert_anomaly_count = 0

    # 1. Update anomalies: tables written much more frequently than read
    try:
        if ctx is not None:
            await ctx.debug(
                f"[{request_id}] Subtool: update anomaly scan",
                extra={"request_id": request_id, "db": db_name},
            )
        result = await asyncio.to_thread(
            connection_manager.execute_catalog_query,
            instance_id,
            db_name,
            update_heavy_tables_query(50),
            50,
        )
        rows = result["rows"]
        if schema_filter:
            rows = [
                r
                for r in rows
                if str(r.get("schema_name", "")).lower() == schema_filter.lower()
            ]
        update_anomaly_count = len(rows)
        if rows:
            findings.append(
                build_finding(
                    code="ANOMALY_UPDATE_WITHOUT_DELETE",
                    severity="medium",
                    title=f"{update_anomaly_count} table(s) with abnormally high write-to-read ratio",
                    detail=(
                        "These tables receive many more writes than reads. This may indicate data being "
                        "overwritten in-place (update anomaly) rather than versioned or appended."
                    ),
                    evidence=[
                        {
                            "table": f"{r.get('schema_name', '')}.{r.get('table_name', '')}",
                            "total_reads": r.get("total_reads"),
                            "total_writes": r.get("total_writes"),
                            "write_read_ratio": r.get("write_read_ratio"),
                        }
                        for r in rows[:10]
                    ],
                )
            )
            recommendations.append(
                build_recommendation(
                    priority="medium",
                    action="Evaluate whether high-write tables should use append-only/event-sourced patterns or audit trails.",
                    rationale="In-place updates without audit history violate auditability requirements and hide data lineage.",
                )
            )
    except Exception as exc:
        if ctx is not None:
            await ctx.warning(
                f"[{request_id}] Subtool: update anomaly scan failed: {exc}",
                extra={"request_id": request_id},
            )
        logger.warning(f"Transaction {request_id}: update anomaly scan skipped: {exc}")

    # 2. Delete anomalies: soft-delete columns without audit/history tables
    try:
        if ctx is not None:
            await ctx.debug(
                f"[{request_id}] Subtool: soft-delete anomaly scan",
                extra={"request_id": request_id, "db": db_name},
            )
        result = connection_manager.execute_catalog_query(
            instance_id, db_name, soft_delete_columns_query(), 200
        )
        rows = result["rows"]
        if schema_filter:
            rows = [
                r
                for r in rows
                if str(r.get("schema_name", "")).lower() == schema_filter.lower()
            ]
        delete_anomaly_count = len(rows)
        if rows:
            findings.append(
                build_finding(
                    code="ANOMALY_SOFT_DELETE_NO_AUDIT",
                    severity="medium",
                    title=f"{delete_anomaly_count} table(s) use soft-delete without a corresponding audit/history table",
                    detail=(
                        "Soft-delete columns were detected, but no matching audit, history, or log table "
                        "exists in the same schema. Deleted records remain in the main table with no "
                        "immutable audit trail."
                    ),
                    evidence=[
                        {
                            "table": f"{r.get('schema_name', '')}.{r.get('table_name', '')}",
                            "soft_delete_column": r.get("soft_delete_column"),
                            "column_type": r.get("column_type"),
                        }
                        for r in rows[:20]
                    ],
                )
            )
            recommendations.append(
                build_recommendation(
                    priority="medium",
                    action="Add a corresponding _Audit or _History table, or implement temporal tables (system-versioned) for soft-delete entities.",
                    rationale="Soft deletes without audit tables violate data governance requirements and complicate compliance reporting.",
                )
            )
    except Exception as exc:
        if ctx is not None:
            await ctx.warning(
                f"[{request_id}] Subtool: soft-delete anomaly scan failed: {exc}",
                extra={"request_id": request_id},
            )
        logger.warning(f"Transaction {request_id}: soft-delete scan skipped: {exc}")

    # 3. Insert anomalies: heap tables (no clustered index) that accumulate fragmentation
    try:
        if ctx is not None:
            await ctx.debug(
                f"[{request_id}] Subtool: insert anomaly (heap) scan",
                extra={"request_id": request_id, "db": db_name},
            )
        # Re-use the existing heap_tables_query available from query_catalog
        from src.tools.query_catalog import (
            heap_tables_query,
        )  # local import to avoid circular at module init

        result = connection_manager.execute_catalog_query(
            instance_id, db_name, heap_tables_query(), 200
        )
        rows = result["rows"]
        if schema_filter:
            rows = [
                r
                for r in rows
                if str(r.get("schema_name", "")).lower() == schema_filter.lower()
            ]
        insert_anomaly_count = len(rows)
        if rows:
            findings.append(
                build_finding(
                    code="ANOMALY_INSERT_INEFFICIENT",
                    severity="low",
                    title=f"{insert_anomaly_count} heap table(s) detected (no clustered index)",
                    detail=(
                        "Heap tables accumulate forwarded records on updates and become fragmented over time, "
                        "causing insert anomalies and degraded scan performance."
                    ),
                    evidence=[
                        {
                            "table": f"{r.get('schema_name', '')}.{r.get('table_name', '')}",
                            "row_count": r.get("row_count"),
                        }
                        for r in rows[:20]
                    ],
                )
            )
            recommendations.append(
                build_recommendation(
                    priority="low",
                    action="Add a clustered index (ideally on a natural key or sequential surrogate) to heap tables.",
                    rationale="A clustered index eliminates forwarded records, reduces fragmentation, and improves range-scan efficiency.",
                )
            )
    except Exception as exc:
        if ctx is not None:
            await ctx.warning(
                f"[{request_id}] Subtool: heap table scan failed: {exc}",
                extra={"request_id": request_id},
            )
        logger.warning(f"Transaction {request_id}: heap table scan skipped: {exc}")

    return {
        "findings": findings,
        "recommendations": recommendations,
        "summary": {
            "update_anomaly_tables": update_anomaly_count,
            "soft_delete_no_audit_tables": delete_anomaly_count,
            "heap_tables": insert_anomaly_count,
        },
    }


async def _subtool_analyze_datatype_consistency(
    db_name: str,
    instance_id: str,
    connection_manager: Any,
    schema_filter: str | None,
    request_id: str,
    ctx: Context | None,
) -> dict[str, Any]:
    """Detect FK relationships where parent/child column base types, lengths, or precision differ."""
    findings: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []
    mismatch_count = 0

    try:
        if ctx is not None:
            await ctx.debug(
                f"[{request_id}] Subtool: FK datatype consistency scan",
                extra={"request_id": request_id, "db": db_name},
            )
        result = await asyncio.to_thread(
            connection_manager.execute_catalog_query,
            instance_id,
            db_name,
            datatype_inconsistency_query(200),
            200,
        )
        rows = result["rows"]
        if schema_filter:
            rows = [
                r
                for r in rows
                if str(r.get("child_schema", "")).lower() == schema_filter.lower()
                or str(r.get("parent_schema", "")).lower() == schema_filter.lower()
            ]

        # Separate type-name mismatches from length/precision-only mismatches
        type_mismatches = [
            r for r in rows if r.get("child_type") != r.get("parent_type")
        ]
        length_mismatches = [
            r
            for r in rows
            if r.get("child_type") == r.get("parent_type")
            and (
                r.get("child_max_length") != r.get("parent_max_length")
                or r.get("child_precision") != r.get("parent_precision")
            )
        ]
        mismatch_count = len(rows)

        if type_mismatches:
            sev = "high" if len(type_mismatches) >= 3 else "medium"
            findings.append(
                build_finding(
                    code="DATATYPE_INCONSISTENCY_EXPLICIT",
                    severity=sev,
                    title=f"{len(type_mismatches)} FK relationship(s) with mismatched base types",
                    detail=(
                        "The child FK column and the referenced parent column have different base types. "
                        "SQL Server performs implicit conversion on every join, reducing plan quality and causing index scan instead of seek."
                    ),
                    evidence=[
                        {
                            "fk": r.get("fk_name"),
                            "child": f"{r.get('child_schema')}.{r.get('child_table')}.{r.get('child_column')} ({r.get('child_type')})",
                            "parent": f"{r.get('parent_schema')}.{r.get('parent_table')}.{r.get('parent_column')} ({r.get('parent_type')})",
                        }
                        for r in type_mismatches[:20]
                    ],
                )
            )
            recommendations.append(
                build_recommendation(
                    priority=sev,
                    action="Align FK column types to match the referenced parent column type exactly.",
                    rationale="Implicit type conversions in FK joins prevent index seeks, increasing CPU and I/O for every join query.",
                )
            )

        if length_mismatches:
            findings.append(
                build_finding(
                    code="DATATYPE_INCONSISTENCY_IMPLICIT",
                    severity="low",
                    title=f"{len(length_mismatches)} FK relationship(s) with mismatched length or precision",
                    detail=(
                        "The child FK column shares the same base type as the parent but differs in max_length or precision. "
                        "This can cause silent truncation or implicit conversions."
                    ),
                    evidence=[
                        {
                            "fk": r.get("fk_name"),
                            "child": f"{r.get('child_schema')}.{r.get('child_table')}.{r.get('child_column')} "
                            f"({r.get('child_type')} len={r.get('child_max_length')} prec={r.get('child_precision')})",
                            "parent": f"{r.get('parent_schema')}.{r.get('parent_table')}.{r.get('parent_column')} "
                            f"({r.get('parent_type')} len={r.get('parent_max_length')} prec={r.get('parent_precision')})",
                        }
                        for r in length_mismatches[:20]
                    ],
                )
            )
            recommendations.append(
                build_recommendation(
                    priority="low",
                    action="Standardize FK column lengths and precision to match the referenced column definition.",
                    rationale="Consistent column sizes prevent silent truncation and avoid conversion overhead in join predicates.",
                )
            )
    except Exception as exc:
        if ctx is not None:
            await ctx.warning(
                f"[{request_id}] Subtool: datatype consistency analysis failed: {exc}",
                extra={"request_id": request_id},
            )
        logger.warning(
            f"Transaction {request_id}: datatype consistency scan skipped: {exc}"
        )

    return {
        "findings": findings,
        "recommendations": recommendations,
        "summary": {"fk_datatype_mismatches": mismatch_count},
    }


def register_sql_tools(mcp: FastMCP, state: Any) -> list[str]:
    registered: list[str] = []

    instance_ids = state.connection_manager.list_enabled_instances()
    number_by_instance = {
        instance_id: idx for idx, instance_id in enumerate(instance_ids, start=1)
    }

    def _auth_enforced() -> bool:
        auth_cfg = getattr(state, "auth", None)
        if auth_cfg is None:
            return False
        return bool(
            auth_cfg.azure_auth_enabled or auth_cfg.auth_mode == "azure_token_verifier"
        )

    async def _resolve_actor_and_authorize(
        *,
        actor: str,
        tool: str,
        required_privilege: str,
        ctx: Context | None,
    ) -> tuple[str, dict[str, Any]]:
        auth_cfg = getattr(state, "auth", None)
        if auth_cfg is None or not _auth_enforced():
            return actor, {
                "auth_mode": "disabled",
                "auth_subject": None,
                "privilege_level": "none",
                "group_match_result": {"group_authorization_enabled": False},
            }

        token = get_access_token()
        if token is None:
            raise PermissionError("AUTH_FAILED: missing or invalid bearer token")

        claims = getattr(token, "claims", {}) or {}
        subject = (
            claims.get("preferred_username")
            or claims.get("oid")
            or claims.get("sub")
            or claims.get("upn")
        )
        principal_groups = claims.get(auth_cfg.azure_group_claim_name, [])
        privilege_level, group_match_result = resolve_group_privilege(
            principal_groups=principal_groups,
            read_groups=auth_cfg.azure_read_groups,
            write_groups=auth_cfg.azure_write_groups,
            group_authorization_enabled=auth_cfg.azure_group_authorization_enabled,
        )

        if required_privilege == "write" and privilege_level != "write":
            raise PermissionError("AUTH_FAILED: write privilege required")
        if required_privilege == "read" and privilege_level == "none":
            raise PermissionError("AUTH_FAILED: read privilege required")

        resolved_actor = (
            subject
            if actor in {"system", "unknown"} and isinstance(subject, str) and subject
            else actor
        )

        if ctx is not None:
            await ctx.debug(
                f"Auth context for {tool}: subject={subject}, privilege={privilege_level}",
                extra={
                    "tool": tool,
                    "auth_subject": subject,
                    "privilege_level": privilege_level,
                    "group_match_result": group_match_result,
                },
            )

        return resolved_actor, {
            "auth_mode": auth_cfg.auth_mode,
            "auth_subject": subject,
            "privilege_level": privilege_level,
            "group_match_result": group_match_result,
        }

    def _log_audit_event(
        *,
        request_id: str,
        actor: str,
        tool: str,
        instance: str,
        sql: str,
        decision: str,
        latency_ms: int,
        rows: int,
        error_code: str | None,
        auth_ctx: dict[str, Any] | None,
    ) -> None:
        state.audit_logger.log_event(
            request_id=request_id,
            actor=actor,
            tool=tool,
            instance=instance,
            sql=sql,
            decision=decision,
            latency_ms=latency_ms,
            rows=rows,
            error_code=error_code,
            auth_mode=(auth_ctx or {}).get("auth_mode"),
            auth_subject=(auth_ctx or {}).get("auth_subject"),
            privilege_level=(auth_ctx or {}).get("privilege_level"),
            group_match_result=(auth_ctx or {}).get("group_match_result"),
        )

    async def _run_read_tool(
        *,
        sql: str,
        tool: str,
        instance: str,
        actor: str,
        ctx: Context | None,
        max_rows: int,
    ) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        started = time.time()
        decision = "allow"
        rows = 0
        error_code = None
        _auth_ctx: dict[str, Any] | None = None
        try:
            if ctx is not None:
                await ctx.debug(
                    f"[{request_id}] Starting {tool} transaction for actor={actor}",
                    extra={
                        "request_id": request_id,
                        "tool": tool,
                        "actor": actor,
                        "instance": instance,
                    },
                )

            actor, _auth_ctx = await _resolve_actor_and_authorize(
                actor=actor,
                tool=tool,
                required_privilege="read",
                ctx=ctx,
            )
            state.session_manager.touch(actor, request_id)
            if ctx is not None:
                await ctx.debug(f"[{request_id}] Session validated for {actor}")

            state.rate_limiter.allow(actor)
            if ctx is not None:
                await ctx.debug(f"[{request_id}] Rate limit check passed for {actor}")

            state.write_guard.enforce(tool, sql)
            if ctx is not None:
                await ctx.debug(f"[{request_id}] Write guard policy check passed")

            result = state.connection_manager.execute_read(instance, sql, max_rows)
            rows = len(result)

            if ctx is not None:
                await ctx.info(
                    f"[{request_id}] {tool} transaction completed successfully",
                    extra={
                        "request_id": request_id,
                        "tool": tool,
                        "instance": instance,
                        "actor": actor,
                        "decision": decision,
                        "rows_returned": rows,
                        "latency_ms": int((time.time() - started) * 1000),
                    },
                )

            logger.info(
                f"Transaction {request_id}: {tool} on {instance} by {actor} - {rows} rows",
                extra={
                    "request_id": request_id,
                    "tool": tool,
                    "instance": instance,
                    "actor": actor,
                    "rows": rows,
                },
            )

            return {
                "instance": instance,
                "tool": tool,
                "row_count": rows,
                "rows": result,
            }
        except PermissionError as exc:
            decision = "deny"
            state.denied_requests += 1
            error_code = str(exc)

            if ctx is not None:
                await ctx.warning(
                    f"[{request_id}] {tool} transaction denied for {actor}: {error_code}",
                    extra={
                        "request_id": request_id,
                        "tool": tool,
                        "instance": instance,
                        "actor": actor,
                        "decision": decision,
                        "error_code": error_code,
                    },
                )

            logger.warning(
                f"Transaction {request_id} DENIED: {error_code}",
                extra={
                    "request_id": request_id,
                    "tool": tool,
                    "instance": instance,
                    "actor": actor,
                    "error": error_code,
                },
            )
            raise
        except Exception as exc:
            decision = "deny"
            sql_err = _extract_sql_error(exc)
            error_code = sql_err["code"] if sql_err else f"NON_SQL_ERROR:{exc.__class__.__name__}"
            if ctx is not None:
                await ctx.error(
                    f"[{request_id}] {tool} transaction failed: {error_code}",
                    extra={
                        "request_id": request_id,
                        "tool": tool,
                        "instance": instance,
                        "actor": actor,
                        "decision": decision,
                        "error_code": error_code,
                    },
                )
            logger.error(
                f"Transaction {request_id} ERROR: {error_code}",
                extra={
                    "request_id": request_id,
                    "tool": tool,
                    "instance": instance,
                    "actor": actor,
                    "decision": decision,
                    "error": error_code,
                },
            )
            raise
        finally:
            latency_ms = int((time.time() - started) * 1000)
            REQUEST_COUNT.labels(tool, instance, decision).inc()
            REQUEST_LATENCY.labels(tool, instance).observe(latency_ms)
            _log_audit_event(
                request_id=request_id,
                actor=actor,
                tool=tool,
                instance=instance,
                sql=sql,
                decision=decision,
                latency_ms=latency_ms,
                rows=rows,
                error_code=error_code,
                auth_ctx=_auth_ctx,
            )

    for spec in generate_tool_specs(instance_ids):
        tool_name = spec.full_name
        instance = spec.instance

        if not is_tool_enabled(state.policy, instance, spec.toolname):
            continue

        if spec.toolname == "select":

            @mcp.tool(name=tool_name)
            async def _select(
                sql: str,
                actor: str = "unknown",
                ctx: Context | None = None,
                _tool=tool_name,
                _instance=instance,
            ):
                """Execute a read query against the bound SQL instance.

                Inputs:
                - sql: SQL statement to execute.
                - actor: caller identity used for session/rate controls.

                Outputs:
                - instance, rows, row_count.
                """
                request_id = str(uuid.uuid4())
                started = time.time()
                decision = "allow"
                rows = 0
                error_code = None
                _auth_ctx: dict[str, Any] | None = None
                try:
                    if ctx is not None:
                        await ctx.debug(
                            f"[{request_id}] Executing select query on {_instance} for actor={actor}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "actor": actor,
                                "instance": _instance,
                            },
                        )

                    actor, _auth_ctx = await _resolve_actor_and_authorize(
                        actor=actor,
                        tool=_tool,
                        required_privilege="read",
                        ctx=ctx,
                    )
                    state.session_manager.touch(actor, request_id)
                    state.rate_limiter.allow(actor)
                    state.write_guard.enforce(_tool, sql)
                    result = state.connection_manager.execute_read(
                        _instance, sql, state.policy.max_result_rows
                    )
                    rows = len(result)

                    if ctx is not None:
                        await ctx.info(
                            f"[{request_id}] Select query executed successfully",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "instance": _instance,
                                "actor": actor,
                                "rows_returned": rows,
                                "decision": decision,
                            },
                        )
                    logger.info(
                        f"Transaction {request_id}: {_tool} - {rows} rows returned"
                    )
                    return {"instance": _instance, "rows": result, "row_count": rows}
                except PermissionError as exc:
                    decision = "deny"
                    state.denied_requests += 1
                    error_code = str(exc)
                    if ctx is not None:
                        await ctx.warning(
                            f"[{request_id}] Select query denied: {error_code}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "instance": _instance,
                                "actor": actor,
                                "decision": decision,
                            },
                        )
                    logger.warning(f"Transaction {request_id} DENIED: {error_code}")
                    raise
                except Exception as exc:
                    decision = "deny"
                    sql_err = _extract_sql_error(exc)
                    error_code = sql_err["code"] if sql_err else f"NON_SQL_ERROR:{exc.__class__.__name__}"
                    if ctx is not None:
                        await ctx.error(
                            f"[{request_id}] Select query failed: {error_code}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "instance": _instance,
                                "actor": actor,
                                "decision": decision,
                                "error": error_code,
                            },
                        )
                    logger.error(f"Transaction {request_id} ERROR: {error_code}")
                    raise
                finally:
                    latency_ms = int((time.time() - started) * 1000)
                    REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                    REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                    _log_audit_event(
                        request_id=request_id,
                        actor=actor,
                        tool=_tool,
                        instance=_instance,
                        sql=sql,
                        decision=decision,
                        latency_ms=latency_ms,
                        rows=rows,
                        error_code=error_code,
                        auth_ctx=_auth_ctx,
                    )

        elif spec.toolname == "exec_proc":

            @mcp.tool(name=tool_name)
            async def _exec_proc(
                proc_name: str,
                params: list[str | int | float | bool | None] | None = None,
                actor: str = "unknown",
                ctx: Context | None = None,
                _tool=tool_name,
                _instance=instance,
            ):
                """Execute an approved stored procedure on the bound instance.

                Inputs:
                - proc_name: procedure to execute.
                - params: positional procedure arguments.
                - actor: caller identity.

                Output:
                - status payload containing procedure metadata and optional result set.
                """
                request_id = str(uuid.uuid4())
                started = time.time()
                decision = "allow"
                error_code = None
                sql = f"EXEC {proc_name}"
                audit_rows = 0
                _auth_ctx: dict[str, Any] | None = None
                result: dict[str, Any] = {}
                try:
                    if ctx is not None:
                        await ctx.debug(
                            f"[{request_id}] Executing stored procedure {proc_name} on {_instance} for actor={actor}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "actor": actor,
                                "instance": _instance,
                                "proc": proc_name,
                            },
                        )

                    actor, _auth_ctx = await _resolve_actor_and_authorize(
                        actor=actor,
                        tool=_tool,
                        required_privilege="write",
                        ctx=ctx,
                    )
                    state.session_manager.touch(actor, request_id)
                    state.rate_limiter.allow(actor)
                    state.write_guard.validate_procedure(_tool, proc_name)
                    state.write_guard.enforce(
                        _tool, "UPDATE __policy_probe__ SET x = 1"
                    )
                    raw_result = state.connection_manager.execute_proc(
                        _instance, proc_name, params
                    )
                    if not isinstance(raw_result, dict):
                        raise RuntimeError(
                            "EXEC_PROC_RESULT_INVALID: expected mapping result"
                        )
                    result = raw_result
                    result_rows = result.get("rows")
                    if isinstance(result_rows, list):
                        audit_rows = len(result_rows)

                    if ctx is not None:
                        await ctx.info(
                            f"[{request_id}] Stored procedure {proc_name} executed successfully",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "instance": _instance,
                                "actor": actor,
                                "proc": proc_name,
                                "decision": decision,
                            },
                        )
                    logger.info(
                        f"Transaction {request_id}: {_tool} - procedure {proc_name} executed"
                    )
                    return {"instance": _instance, **result}
                except PermissionError as exc:
                    decision = "deny"
                    state.denied_requests += 1
                    error_code = str(exc)
                    if ctx is not None:
                        await ctx.warning(
                            f"[{request_id}] Stored procedure {proc_name} execution denied: {error_code}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "instance": _instance,
                                "actor": actor,
                                "proc": proc_name,
                                "decision": decision,
                            },
                        )
                    logger.warning(f"Transaction {request_id} DENIED: {error_code}")
                    raise
                except Exception as exc:
                    decision = "deny"
                    sql_err = _extract_sql_error(exc)
                    error_code = sql_err["code"] if sql_err else f"NON_SQL_ERROR:{exc.__class__.__name__}"
                    if ctx is not None:
                        await ctx.error(
                            f"[{request_id}] Stored procedure {proc_name} failed: {error_code}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "instance": _instance,
                                "actor": actor,
                                "proc": proc_name,
                                "decision": decision,
                                "error": error_code,
                            },
                        )
                    logger.error(f"Transaction {request_id} ERROR: {error_code}")
                    raise
                finally:
                    latency_ms = int((time.time() - started) * 1000)
                    REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                    REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                    _log_audit_event(
                        request_id=request_id,
                        actor=actor,
                        tool=_tool,
                        instance=_instance,
                        sql=sql,
                        decision=decision,
                        latency_ms=latency_ms,
                        rows=audit_rows,
                        error_code=error_code,
                        auth_ctx=_auth_ctx,
                    )

        elif spec.toolname == "latency_report":

            @mcp.tool(name=tool_name)
            async def _latency_report(
                actor: str = "system", _tool=tool_name, _instance=instance
            ):
                """Return guidance for latency diagnostics on this instance.

                Use diagnostics metrics endpoint for histogram/percentile analysis.
                """
                return {
                    "instance": _instance,
                    "tool": _tool,
                    "message": "Use /diagnostics/metrics for histogram data and rollups.",
                    "actor": actor,
                }

        elif spec.toolname == "block_report":

            @mcp.tool(name=tool_name)
            async def _block_report(
                actor: str = "system",
                ctx: Context | None = None,
                _tool=tool_name,
                _instance=instance,
            ):
                """Return blocking session chains and wait details for the bound instance.

                Inputs:
                - actor: caller identity.

                Output:
                - row set with session_id, blocking_session_id, wait_type, wait_time, and SQL text.
                """
                sql = (
                    "SELECT TOP 25 r.session_id, r.blocking_session_id, r.wait_type, r.wait_time, t.text "
                    "FROM sys.dm_exec_requests r "
                    "CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t "
                    "WHERE r.blocking_session_id <> 0 ORDER BY r.wait_time DESC"
                )
                return await _run_read_tool(
                    sql=sql,
                    tool=_tool,
                    instance=_instance,
                    actor=actor,
                    ctx=ctx,
                    max_rows=25,
                )

        elif spec.toolname == "top_queries_report":

            @mcp.tool(name=tool_name)
            async def _top_queries_report(
                limit: int = 20,
                actor: str = "system",
                ctx: Context | None = None,
                _tool=tool_name,
                _instance=instance,
            ):
                """Return top expensive cached queries by worker time.

                Inputs:
                - limit: max rows (1..100).
                - actor: caller identity.

                Output:
                - query cost/elapsed/execution stats and query text.
                """
                size = max(1, min(limit, 100))
                sql = (
                    f"SELECT TOP {size} qs.total_worker_time, qs.total_elapsed_time, qs.execution_count, "
                    "DB_NAME(st.dbid) AS database_name, st.text AS query_text "
                    "FROM sys.dm_exec_query_stats qs "
                    "CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st "
                    "ORDER BY qs.total_worker_time DESC"
                )
                return await _run_read_tool(
                    sql=sql,
                    tool=_tool,
                    instance=_instance,
                    actor=actor,
                    ctx=ctx,
                    max_rows=size,
                )

        elif spec.toolname == "active_sessions_report":

            @mcp.tool(name=tool_name)
            async def _active_sessions_report(
                limit: int = 50,
                actor: str = "system",
                ctx: Context | None = None,
                _tool=tool_name,
                _instance=instance,
            ):
                """Return active user session/request diagnostics.

                Inputs:
                - limit: max rows (1..200).
                - actor: caller identity.

                Output:
                - session metadata and request/wait state.
                """
                size = max(1, min(limit, 200))
                sql = (
                    f"SELECT TOP {size} s.session_id, s.login_name, s.host_name, s.program_name, "
                    "s.status, r.command, r.wait_type, r.wait_time, r.cpu_time "
                    "FROM sys.dm_exec_sessions s "
                    "LEFT JOIN sys.dm_exec_requests r ON s.session_id = r.session_id "
                    "WHERE s.is_user_process = 1 "
                    "ORDER BY s.session_id DESC"
                )
                return await _run_read_tool(
                    sql=sql,
                    tool=_tool,
                    instance=_instance,
                    actor=actor,
                    ctx=ctx,
                    max_rows=size,
                )

        elif spec.toolname == "index_health_report":

            @mcp.tool(name=tool_name)
            async def _index_health_report(
                limit: int = 50,
                actor: str = "system",
                ctx: Context | None = None,
                _tool=tool_name,
                _instance=instance,
            ):
                """Return index usage health indicators for maintenance triage.

                Inputs:
                - limit: max rows (1..200).
                - actor: caller identity.

                Output:
                - table/index names, type, and usage counters.
                """
                size = max(1, min(limit, 200))
                sql = (
                    f"SELECT TOP {size} OBJECT_NAME(i.object_id) AS table_name, i.name AS index_name, "
                    "i.type_desc, ISNULL(us.user_seeks,0) AS user_seeks, ISNULL(us.user_scans,0) AS user_scans, "
                    "ISNULL(us.user_lookups,0) AS user_lookups, ISNULL(us.user_updates,0) AS user_updates "
                    "FROM sys.indexes i "
                    "LEFT JOIN sys.dm_db_index_usage_stats us "
                    "ON i.object_id = us.object_id AND i.index_id = us.index_id AND us.database_id = DB_ID() "
                    "WHERE i.index_id > 0 "
                    "ORDER BY ISNULL(us.user_scans,0) + ISNULL(us.user_seeks,0) DESC"
                )
                return await _run_read_tool(
                    sql=sql,
                    tool=_tool,
                    instance=_instance,
                    actor=actor,
                    ctx=ctx,
                    max_rows=size,
                )

        registered.append(tool_name)

    tool_metadata_by_suffix: dict[str, dict[str, Any]] = {
        "ping": {
            "description": (
                "Connectivity check for the target SQL Server instance. Returns accessibility flag, "
                "instance/server identity data, server IP, version, and current UTC system date from SQL Server."
            ),
            "required_parameters": [],
            "optional_parameters": ["actor"],
            "output_fields": [
                "accessible",
                "instance_number",
                "instance_name",
                "hostname",
                "database_version",
                "ip_address",
                "current_system_date",
                "error_code",
            ],
            "operational_behavior": "Performs a lightweight query in master and records audit/latency metrics.",
        },
        "list_tools": {
            "description": (
                "Discovery endpoint that enumerates MCP tools registered for the selected instance number. "
                "Includes tool descriptions and required parameters for runtime introspection."
            ),
            "required_parameters": [],
            "optional_parameters": ["actor"],
            "output_fields": [
                "instance_number",
                "database_instance_name",
                "ip_address",
                "system_date",
                "tools",
            ],
            "operational_behavior": "Reads in-memory registry and attaches SQL instance identity metadata.",
        },
        "list_object": {
            "description": (
                "Lists objects in a specified database by object type. Supports table, view, procedure, function, "
                "and synonym. Designed for schema discovery and validation workflows."
            ),
            "required_parameters": ["database_name", "object_type"],
            "optional_parameters": ["actor"],
            "output_fields": [
                "instance_number",
                "database_name",
                "system_date",
                "object_type",
                "objects",
                "row_count",
            ],
            "operational_behavior": "Executes catalog query in target DB context and enforces session/rate controls.",
        },
        "execute_query": {
            "description": (
                "Executes SQL in the specified database context. Fully qualified object names are supported for "
                "cross-database reads. Use COMPACT for row payload only; FULL adds explain-plan summary when available."
            ),
            "required_parameters": [
                "database_name",
                "sql_statement",
            ],
            "optional_parameters": ["actor", "view_mode"],
            "output_fields": [
                "instance_number",
                "database_name",
                "execution_datetime_utc",
                "view_mode",
                "columns",
                "row_count",
                "rows",
                "plan",
            ],
            "operational_behavior": (
                "Applies write guard and rate/session checks before execution; FULL mode attempts SHOWPLAN summary."
            ),
        },
        "analyze_tab_health": {
            "description": (
                "Analyzes table and index health for a database, including table size, index fragmentation, and "
                "tables missing primary keys. Returns prioritized findings and recommendations."
            ),
            "required_parameters": ["database_name"],
            "optional_parameters": [
                "schema_name",
                "table_name",
                "include_indexes",
                "top_n",
                "actor",
            ],
            "output_fields": [
                "instance_number",
                "database_name",
                "tool",
                "generated_at_utc",
                "summary",
                "severity_counts",
                "findings",
                "recommendations",
            ],
            "operational_behavior": "Runs read-only catalog/DMV checks and returns deterministic analysis JSON.",
        },
        "analyze_db_data_model": {
            "description": (
                "Analyzes logical data model relationships in the target database and reports dependency graph "
                "health, including circular foreign-key dependencies."
            ),
            "required_parameters": ["database_name"],
            "optional_parameters": ["schema_filter", "max_edges", "actor"],
            "output_fields": [
                "instance_number",
                "database_name",
                "tool",
                "generated_at_utc",
                "summary",
                "severity_counts",
                "findings",
                "recommendations",
            ],
            "operational_behavior": "Extracts FK graph metadata and flags structural integrity risks.",
        },
        "analyze_sec_config": {
            "description": (
                "Assesses security and configuration posture for the target database/instance, including elevated "
                "role memberships, orphan users, and backup recency."
            ),
            "required_parameters": ["database_name"],
            "optional_parameters": ["include_server_scope", "actor"],
            "output_fields": [
                "instance_number",
                "database_name",
                "tool",
                "generated_at_utc",
                "summary",
                "severity_counts",
                "findings",
                "recommendations",
            ],
            "operational_behavior": "Uses read-only security/catalog checks and redacts sensitive fields in output.",
        },
        "sessions_dashboard": {
            "description": (
                "Builds an interactive session dashboard payload for active sessions and lock chains, returning "
                "both HTML and machine-readable widget data."
            ),
            "required_parameters": [],
            "optional_parameters": [
                "database_name",
                "lookback_minutes",
                "include_locks",
                "actor",
            ],
            "output_fields": ["content_type", "html", "data"],
            "operational_behavior": "Collects bounded DMV data and formats a dashboard payload for MCP clients.",
        },
        "top_statements": {
            "description": (
                "Analyzes top longest-running SQL statements in a database context, with execution counts "
                "and prescriptive recommendations for index strategy, query rewrites, query hints, and "
                "partitioning. Falls back from Query Store to DMV data when Query Store views are unavailable."
            ),
            "required_parameters": ["database_name"],
            "optional_parameters": [
                "top_n",
                "lookback_minutes",
                "view_mode",
                "actor",
            ],
            "output_fields": [
                "instance_number",
                "database_name",
                "tool",
                "generated_at_utc",
                "summary",
                "severity_counts",
                "findings",
                "recommendations",
                "top_statements",
                "data_source",
            ],
            "operational_behavior": (
                "Collects Query Store or DMV metrics, analyzes duration/execution/scan patterns, "
                "and returns deterministic analysis JSON with DBA review disclaimer."
            ),
        },
    }

    for instance_id in instance_ids:
        instance_number = number_by_instance[instance_id]

        ping_tool_name = f"db_{instance_number}_sql2019_ping"

        @mcp.tool(name=ping_tool_name)
        async def _ping(
            actor: str = "system",
            ctx: Context | None = None,
            _tool=ping_tool_name,
            _instance=instance_id,
            _instance_number=instance_number,
        ):
            """Check accessibility and identity of a SQL instance.

            Outputs accessibility flag plus instance name, host, version, IP, and current SQL UTC date.
            """
            sql = (
                "SELECT @@SERVERNAME AS instance_name, "
                "CAST(SERVERPROPERTY('MachineName') AS NVARCHAR(128)) AS hostname, "
                "CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128)) AS database_version, "
                "CONVERT(NVARCHAR(64), CONNECTIONPROPERTY('local_net_address')) AS ip_address, "
                "CONVERT(NVARCHAR(33), SYSUTCDATETIME(), 127) AS current_system_date"
            )
            request_id = str(uuid.uuid4())
            started = time.time()
            decision = "allow"
            error_code = None
            row_count = 0
            _auth_ctx: dict[str, Any] | None = None
            try:
                if ctx is not None:
                    await ctx.debug(
                        f"[{request_id}] Pinging instance {_instance_number} for actor={actor}"
                    )

                actor, _auth_ctx = await _resolve_actor_and_authorize(
                    actor=actor,
                    tool=_tool,
                    required_privilege="read",
                    ctx=ctx,
                )
                state.session_manager.touch(actor, request_id)
                state.rate_limiter.allow(actor)
                payload = state.connection_manager.fetch_single_row_in_database(
                    _instance, "master", sql
                )
                row_count = 1 if payload else 0

                if ctx is not None:
                    await ctx.info(
                        f"[{request_id}] Instance {_instance_number} is accessible",
                        extra={
                            "request_id": request_id,
                            "tool": _tool,
                            "instance_number": _instance_number,
                            "accessible": True,
                        },
                    )
                logger.info(f"Transaction {request_id}: {_tool} - instance accessible")

                return {
                    "accessible": True,
                    "instance_number": _instance_number,
                    "instance_name": payload.get("instance_name"),
                    "hostname": payload.get("hostname"),
                    "database_version": payload.get("database_version"),
                    "ip_address": payload.get("ip_address"),
                    "current_system_date": payload.get("current_system_date"),
                }
            except Exception as exc:
                decision = "deny"
                error_code = f"INSTANCE_UNREACHABLE: {exc}"
                state.denied_requests += 1

                if ctx is not None:
                    await ctx.warning(
                        f"[{request_id}] Instance {_instance_number} is not accessible: {error_code}",
                        extra={
                            "request_id": request_id,
                            "tool": _tool,
                            "instance_number": _instance_number,
                            "accessible": False,
                            "error": error_code,
                        },
                    )
                logger.warning(
                    f"Transaction {request_id}: {_tool} - instance unreachable: {error_code}"
                )

                return {
                    "accessible": False,
                    "instance_number": _instance_number,
                    "instance_name": None,
                    "hostname": None,
                    "database_version": None,
                    "ip_address": None,
                    "current_system_date": datetime.now(timezone.utc).isoformat(),
                    "error_code": error_code,
                }
            finally:
                latency_ms = int((time.time() - started) * 1000)
                REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                _log_audit_event(
                    request_id=request_id,
                    actor=actor,
                    tool=_tool,
                    instance=_instance,
                    sql=sql,
                    decision=decision,
                    latency_ms=latency_ms,
                    rows=row_count,
                    error_code=error_code,
                    auth_ctx=_auth_ctx,
                )

        registered.append(ping_tool_name)

        list_tools_name = f"db_{instance_number}_sql2019_list_tools"

        @mcp.tool(name=list_tools_name)
        async def _list_tools(
            actor: str = "system",
            ctx: Context | None = None,
            _tool=list_tools_name,
            _instance=instance_id,
            _instance_number=instance_number,
        ):
            """List MCP tools available for the specified instance number.

            Returns tool descriptions, required/optional parameters, output fields, and behavior notes.
            """
            sql = (
                "SELECT @@SERVERNAME AS instance_name, "
                "CONVERT(NVARCHAR(64), CONNECTIONPROPERTY('local_net_address')) AS ip_address, "
                "CONVERT(NVARCHAR(33), SYSUTCDATETIME(), 127) AS current_system_date"
            )
            request_id = str(uuid.uuid4())
            started = time.time()
            decision = "allow"
            error_code = None
            row_count = 0
            _auth_ctx: dict[str, Any] | None = None
            try:
                if ctx is not None:
                    await ctx.debug(
                        f"[{request_id}] Listing tools for instance {_instance_number}"
                    )

                actor, _auth_ctx = await _resolve_actor_and_authorize(
                    actor=actor,
                    tool=_tool,
                    required_privilege="read",
                    ctx=ctx,
                )
                state.session_manager.touch(actor, request_id)
                state.rate_limiter.allow(actor)
                info = state.connection_manager.fetch_single_row_in_database(
                    _instance, "master", sql
                )
                prefix = f"db_{_instance_number}_sql2019_"
                matching = [
                    name for name in state.registered_tools if name.startswith(prefix)
                ]
                tools = []
                for name in matching:
                    suffix = name[len(prefix) :]
                    meta = tool_metadata_by_suffix.get(
                        suffix,
                        {
                            "description": "Registered MCP tool",
                            "required_parameters": [],
                        },
                    )
                    tools.append(
                        {
                            "name": name,
                            "description": meta["description"],
                            "required_parameters": meta["required_parameters"],
                            "optional_parameters": meta.get("optional_parameters", []),
                            "output_fields": meta.get("output_fields", []),
                            "operational_behavior": meta.get(
                                "operational_behavior", "Registered MCP tool"
                            ),
                        }
                    )
                row_count = len(tools)

                if ctx is not None:
                    await ctx.info(
                        f"[{request_id}] Listed {row_count} tools for instance {_instance_number}",
                        extra={
                            "request_id": request_id,
                            "tool": _tool,
                            "instance_number": _instance_number,
                            "tool_count": row_count,
                        },
                    )
                logger.info(
                    f"Transaction {request_id}: {_tool} - {row_count} tools listed"
                )

                return {
                    "instance_number": _instance_number,
                    "database_instance_name": info.get("instance_name"),
                    "ip_address": info.get("ip_address"),
                    "system_date": info.get("current_system_date"),
                    "tools": tools,
                }
            except Exception as exc:
                decision = "deny"
                sql_err = _extract_sql_error(exc)
                if sql_err:
                    error_code = (
                        f"{sql_err['code']}: {sql_err['sql_message']}"
                    )
                else:
                    error_code = f"SQL_EXECUTION_ERROR: {exc}"
                state.denied_requests += 1

                if ctx is not None:
                    extra_payload: dict[str, Any] = {
                        "request_id": request_id,
                        "tool": _tool,
                        "instance_number": _instance_number,
                        "error": error_code,
                    }
                    if sql_err:
                        extra_payload["sqlstate"] = sql_err["sqlstate"]
                        extra_payload["sql_error_number"] = sql_err["sql_error_number"]
                    await ctx.error(
                        f"[{request_id}] Failed to list tools: {error_code}",
                        extra=extra_payload,
                    )
                logger.error(f"Transaction {request_id} ERROR: {error_code}")

                raise RuntimeError(error_code) from exc
            finally:
                latency_ms = int((time.time() - started) * 1000)
                REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                _log_audit_event(
                    request_id=request_id,
                    actor=actor,
                    tool=_tool,
                    instance=_instance,
                    sql=sql,
                    decision=decision,
                    latency_ms=latency_ms,
                    rows=row_count,
                    error_code=error_code,
                    auth_ctx=_auth_ctx,
                )

        registered.append(list_tools_name)

        list_object_name = f"db_{instance_number}_sql2019_list_object"

        @mcp.tool(name=list_object_name)
        async def _list_object(
            database_name: str,
            object_type: str,
            actor: str = "system",
            ctx: Context | None = None,
            _tool=list_object_name,
            _instance=instance_id,
            _instance_number=instance_number,
        ):
            """List objects by type within a specified database on the bound instance.

            Inputs:
            - database_name: target database.
            - object_type: table|view|procedure|function|synonym.

            Output includes object rows and total row_count.
            """
            sql = f"LIST_OBJECT database={database_name} type={object_type}"
            request_id = str(uuid.uuid4())
            started = time.time()
            decision = "allow"
            error_code = None
            row_count = 0
            _auth_ctx: dict[str, Any] | None = None
            try:
                if ctx is not None:
                    await ctx.debug(
                        f"[{request_id}] Listing {object_type} objects in {database_name}",
                        extra={
                            "request_id": request_id,
                            "tool": _tool,
                            "database": database_name,
                            "object_type": object_type,
                        },
                    )

                actor, _auth_ctx = await _resolve_actor_and_authorize(
                    actor=actor,
                    tool=_tool,
                    required_privilege="read",
                    ctx=ctx,
                )
                state.session_manager.touch(actor, request_id)
                state.rate_limiter.allow(actor)
                rows = state.connection_manager.list_objects(
                    _instance, database_name, object_type
                )
                row_count = len(rows)

                if ctx is not None:
                    await ctx.info(
                        f"[{request_id}] Listed {row_count} {object_type} objects",
                        extra={
                            "request_id": request_id,
                            "tool": _tool,
                            "database": database_name,
                            "object_type": object_type,
                            "object_count": row_count,
                            "decision": decision,
                        },
                    )
                logger.info(
                    f"Transaction {request_id}: {_tool} - {row_count} objects listed"
                )

                return {
                    "instance_number": _instance_number,
                    "database_name": database_name,
                    "system_date": datetime.now(timezone.utc).isoformat(),
                    "object_type": object_type.lower(),
                    "objects": rows,
                    "row_count": row_count,
                }
            except ValueError as exc:
                decision = "deny"
                error_code = str(exc)
                state.denied_requests += 1

                if ctx is not None:
                    await ctx.warning(
                        f"[{request_id}] Invalid parameters: {error_code}",
                        extra={
                            "request_id": request_id,
                            "tool": _tool,
                            "database": database_name,
                            "object_type": object_type,
                            "error": error_code,
                        },
                    )
                logger.warning(f"Transaction {request_id} denied: {error_code}")
                raise
            except Exception as exc:
                decision = "deny"
                sql_err = _extract_sql_error(exc)
                if sql_err:
                    error_code = (
                        f"{sql_err['code']}: {sql_err['sql_message']}"
                    )
                else:
                    error_code = f"SQL_EXECUTION_ERROR: {exc}"
                state.denied_requests += 1

                if ctx is not None:
                    extra_payload: dict[str, Any] = {
                        "request_id": request_id,
                        "tool": _tool,
                        "database": database_name,
                        "object_type": object_type,
                        "error": error_code,
                    }
                    if sql_err:
                        extra_payload["sqlstate"] = sql_err["sqlstate"]
                        extra_payload["sql_error_number"] = sql_err["sql_error_number"]
                    await ctx.error(
                        f"[{request_id}] Object listing failed: {error_code}",
                        extra=extra_payload,
                    )
                logger.error(f"Transaction {request_id} ERROR: {error_code}")

                raise RuntimeError(error_code) from exc
            finally:
                latency_ms = int((time.time() - started) * 1000)
                REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                _log_audit_event(
                    request_id=request_id,
                    actor=actor,
                    tool=_tool,
                    instance=_instance,
                    sql=sql,
                    decision=decision,
                    latency_ms=latency_ms,
                    rows=row_count,
                    error_code=error_code,
                    auth_ctx=_auth_ctx,
                )

        registered.append(list_object_name)

        execute_query_name = f"db_{instance_number}_sql2019_execute_query"

        @mcp.tool(name=execute_query_name)
        async def _execute_query(
            database_name: str,
            sql_statement: str,
            view_mode: str = "COMPACT",
            actor: str = "system",
            ctx: Context | None = None,
            _tool=execute_query_name,
            _instance=instance_id,
            _instance_number=instance_number,
        ):
            """Execute SQL against a specific database context on the bound instance.

            Inputs:
            - database_name: execution context DB.
            - sql_statement: SQL text (supports fully qualified cross-database names).
            - view_mode: COMPACT (default) or FULL.

            FULL mode appends explain-plan summary when available.
            """
            request_id = str(uuid.uuid4())
            started = time.time()
            decision = "allow"
            error_code = None
            rows = 0
            _auth_ctx: dict[str, Any] | None = None
            try:
                if ctx is not None:
                    await ctx.debug(
                        f"[{request_id}] Executing query in {database_name} (view_mode={view_mode})",
                        extra={
                            "request_id": request_id,
                            "tool": _tool,
                            "database": database_name,
                            "view_mode": view_mode,
                        },
                    )

                normalized = view_mode.strip().upper()
                if normalized not in {"FULL", "COMPACT"}:
                    raise ValueError("INVALID_INPUT: view_mode must be FULL or COMPACT")

                actor, _auth_ctx = await _resolve_actor_and_authorize(
                    actor=actor,
                    tool=_tool,
                    required_privilege="read",
                    ctx=ctx,
                )
                state.session_manager.touch(actor, request_id)
                state.rate_limiter.allow(actor)
                state.write_guard.enforce(_tool, sql_statement)

                result = state.connection_manager.execute_read_in_database(
                    _instance,
                    database_name,
                    sql_statement,
                    state.policy.max_result_rows,
                )
                rows = len(result["rows"])

                output: dict[str, Any] = {
                    "instance_number": _instance_number,
                    "database_name": database_name,
                    "execution_datetime_utc": datetime.now(timezone.utc).isoformat(),
                    "view_mode": normalized,
                    "columns": result["columns"],
                    "row_count": rows,
                    "rows": result["rows"],
                }

                if normalized == "FULL":
                    try:
                        output["plan"] = state.connection_manager.explain_query(
                            _instance, database_name, sql_statement
                        )
                    except Exception as exc:
                        output["plan"] = {
                            "available": False,
                            "estimated_cost": None,
                            "accessed_objects": [],
                            "error": f"SQL_EXECUTION_ERROR: {exc}",
                        }

                if ctx is not None:
                    await ctx.info(
                        f"[{request_id}] Query executed successfully - {rows} rows",
                        extra={
                            "request_id": request_id,
                            "tool": _tool,
                            "database": database_name,
                            "rows_returned": rows,
                            "view_mode": normalized,
                            "decision": decision,
                        },
                    )
                logger.info(f"Transaction {request_id}: {_tool} - {rows} rows returned")

                return output
            except ValueError as exc:
                decision = "deny"
                error_code = str(exc)
                state.denied_requests += 1

                if ctx is not None:
                    await ctx.warning(
                        f"[{request_id}] Invalid query parameters: {error_code}",
                        extra={
                            "request_id": request_id,
                            "tool": _tool,
                            "database": database_name,
                            "error": error_code,
                        },
                    )
                logger.warning(f"Transaction {request_id} denied: {error_code}")
                raise
            except PermissionError as exc:
                decision = "deny"
                error_code = str(exc)
                state.denied_requests += 1

                if ctx is not None:
                    await ctx.warning(
                        f"[{request_id}] Query execution denied: {error_code}",
                        extra={
                            "request_id": request_id,
                            "tool": _tool,
                            "database": database_name,
                            "error": error_code,
                        },
                    )
                logger.warning(f"Transaction {request_id} DENIED: {error_code}")
                raise
            except Exception as exc:
                decision = "deny"
                sql_err = _extract_sql_error(exc)
                if sql_err:
                    error_code = (
                        f"{sql_err['code']}: {sql_err['sql_message']}"
                    )
                else:
                    error_code = f"SQL_EXECUTION_ERROR: {exc}"
                state.denied_requests += 1

                if ctx is not None:
                    extra_payload: dict[str, Any] = {
                        "request_id": request_id,
                        "tool": _tool,
                        "database": database_name,
                        "error": error_code,
                    }
                    if sql_err:
                        extra_payload["sqlstate"] = sql_err["sqlstate"]
                        extra_payload["sql_error_number"] = sql_err["sql_error_number"]
                    await ctx.error(
                        f"[{request_id}] Query execution failed: {error_code}",
                        extra=extra_payload,
                    )
                logger.error(f"Transaction {request_id} ERROR: {error_code}")
                raise RuntimeError(error_code) from exc
            finally:
                latency_ms = int((time.time() - started) * 1000)
                REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                _log_audit_event(
                    request_id=request_id,
                    actor=actor,
                    tool=_tool,
                    instance=_instance,
                    sql=sql_statement,
                    decision=decision,
                    latency_ms=latency_ms,
                    rows=rows,
                    error_code=error_code,
                    auth_ctx=_auth_ctx,
                )

        registered.append(execute_query_name)

        analyze_tab_health_name = f"db_{instance_number}_sql2019_analyze_tab_health"
        if is_tool_enabled(state.policy, instance_id, "analyze_tab_health"):

            @mcp.tool(name=analyze_tab_health_name)
            async def _analyze_tab_health(
                database_name: str,
                schema_name: str | None = None,
                table_name: str | None = None,
                include_indexes: bool = True,
                include_statistics: bool = True,
                include_histogram_analysis: bool = False,
                histogram_top_n: int = 10,
                top_n: int = 50,
                actor: str = "system",
                ctx: Context | None = None,
                _tool=analyze_tab_health_name,
                _instance=instance_id,
                _instance_number=instance_number,
            ):
                """Analyze table/index health for a bound SQL instance and database context."""
                request_id = str(uuid.uuid4())
                started = time.time()
                decision = "allow"
                error_code = None
                rows = 0
                sql_marker = "ANALYZE_TAB_HEALTH"
                _auth_ctx: dict[str, Any] | None = None
                try:
                    if ctx is not None:
                        await ctx.debug(
                            f"[{request_id}] Analyzing table health in {database_name}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                            },
                        )

                    db_name = validate_database_name(database_name)
                    if schema_name is not None:
                        schema_name = validate_identifier(schema_name, "schema_name")
                    if table_name is not None:
                        table_name = validate_identifier(table_name, "table_name")
                    size = validate_positive_int(top_n, "top_n", 1, 500)
                    histogram_limit = validate_positive_int(
                        histogram_top_n, "histogram_top_n", 1, 100
                    )

                    actor, _auth_ctx = await _resolve_actor_and_authorize(
                        actor=actor,
                        tool=_tool,
                        required_privilege="read",
                        ctx=ctx,
                    )
                    state.session_manager.touch(actor, request_id)
                    state.rate_limiter.allow(actor)
                    state.write_guard.enforce(_tool, "SELECT 1")

                    table_sizes = state.connection_manager.execute_catalog_query(
                        _instance, db_name, table_size_query(size), size
                    )
                    fragmented = {"rows": []}
                    if include_indexes:
                        fragmented = state.connection_manager.execute_catalog_query(
                            _instance,
                            db_name,
                            fragmented_indexes_query(size),
                            size,
                        )
                    missing_pk = state.connection_manager.execute_catalog_query(
                        _instance, db_name, missing_pk_query(), size
                    )

                    stale_stats = {"rows": []}
                    never_updated_stats = {"rows": []}
                    low_sampled_stats = {"rows": []}
                    db_stats_settings = {"rows": []}
                    missing_stats_coverage = {"rows": []}
                    if include_statistics:
                        stale_stats = state.connection_manager.execute_catalog_query(
                            _instance,
                            db_name,
                            stale_statistics_query(size),
                            size,
                        )
                        never_updated_stats = state.connection_manager.execute_catalog_query(
                            _instance,
                            db_name,
                            statistics_never_updated_query(size),
                            size,
                        )
                        low_sampled_stats = state.connection_manager.execute_catalog_query(
                            _instance,
                            db_name,
                            low_sampled_statistics_query(size),
                            size,
                        )
                        db_stats_settings = state.connection_manager.execute_catalog_query(
                            _instance,
                            db_name,
                            database_statistics_settings_query(),
                            1,
                        )
                        missing_stats_coverage = (
                            state.connection_manager.execute_catalog_query(
                                _instance,
                                db_name,
                                missing_statistics_coverage_candidate_query(size),
                                size,
                            )
                        )

                    filtered_sizes = _filter_rows_by_schema_table(
                        table_sizes["rows"], schema_name, table_name
                    )
                    filtered_fragmented = _filter_rows_by_schema_table(
                        fragmented["rows"], schema_name, table_name
                    )
                    filtered_missing_pk = _filter_rows_by_schema_table(
                        missing_pk["rows"], schema_name, table_name
                    )
                    filtered_stale_stats = _filter_rows_by_schema_table(
                        stale_stats["rows"], schema_name, table_name
                    )
                    filtered_never_updated_stats = _filter_rows_by_schema_table(
                        never_updated_stats["rows"], schema_name, table_name
                    )
                    filtered_low_sampled_stats = _filter_rows_by_schema_table(
                        low_sampled_stats["rows"], schema_name, table_name
                    )
                    filtered_missing_stats_coverage = _filter_rows_by_schema_table(
                        missing_stats_coverage["rows"], schema_name, table_name
                    )

                    findings: list[dict[str, Any]] = []
                    recommendations: list[dict[str, Any]] = []
                    if include_indexes and filtered_fragmented:
                        top_frag = filtered_fragmented[0]
                        findings.append(
                            build_finding(
                                code="TAB_HEALTH_FRAGMENTED_INDEXES",
                                severity="high",
                                title="High index fragmentation detected",
                                detail="One or more indexes exceed healthy fragmentation levels.",
                                evidence=filtered_fragmented[:10],
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority="high",
                                action="Rebuild/reorganize top fragmented indexes during maintenance windows.",
                                rationale=f"Highest observed fragmentation: {top_frag.get('avg_fragmentation_in_percent')}%",
                            )
                        )

                    if filtered_missing_pk:
                        findings.append(
                            build_finding(
                                code="TAB_HEALTH_MISSING_PRIMARY_KEY",
                                severity="medium",
                                title="Tables without primary keys",
                                detail="Detected tables lacking primary key constraints.",
                                evidence=filtered_missing_pk[:10],
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority="medium",
                                action="Define primary keys for unconstrained tables.",
                                rationale="Primary keys improve integrity, optimizer quality, and replication behavior.",
                            )
                        )

                    classified_stale_stats = [
                        enriched
                        for enriched in (
                            _classify_stale_statistics_row(r)
                            for r in filtered_stale_stats
                        )
                        if enriched is not None
                    ]
                    if classified_stale_stats:
                        has_high_stale = any(
                            row.get("severity") == "high"
                            for row in classified_stale_stats
                        )
                        findings.append(
                            build_finding(
                                code="TAB_HEALTH_STALE_STATISTICS",
                                severity="high" if has_high_stale else "medium",
                                title="Potentially stale statistics detected",
                                detail=(
                                    "Statistics show high change volume or extended age since last update, "
                                    "which can degrade cardinality estimates and plan quality."
                                ),
                                evidence=classified_stale_stats[:10],
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority="high" if has_high_stale else "medium",
                                action=(
                                    "Refresh stale statistics for the listed objects during a planned maintenance window."
                                ),
                                rationale=(
                                    "Reducing statistics staleness improves cardinality estimates and lowers plan-regression risk."
                                ),
                            )
                        )

                    if filtered_never_updated_stats:
                        has_large_never_updated = any(
                            _safe_float(row.get("rows")) >= STATS_MIN_ROWS_HIGH_SEVERITY
                            for row in filtered_never_updated_stats
                        )
                        findings.append(
                            build_finding(
                                code="TAB_HEALTH_STATS_NEVER_UPDATED",
                                severity="high" if has_large_never_updated else "medium",
                                title="Statistics with no update history detected",
                                detail=(
                                    "Some user-table statistics report no last-updated timestamp, indicating they may be uninitialized or stale."
                                ),
                                evidence=filtered_never_updated_stats[:10],
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority="high" if has_large_never_updated else "medium",
                                action=(
                                    "Review auto stats behavior and refresh the listed statistics for active large tables."
                                ),
                                rationale=(
                                    "Uninitialized statistics can produce poor row estimates and unstable query plans."
                                ),
                            )
                        )

                    classified_low_sample_stats = [
                        enriched
                        for enriched in (
                            _classify_low_sample_statistics_row(r)
                            for r in filtered_low_sampled_stats
                        )
                        if enriched is not None
                    ]
                    if classified_low_sample_stats:
                        has_high_low_sample = any(
                            row.get("severity") == "high"
                            for row in classified_low_sample_stats
                        )
                        findings.append(
                            build_finding(
                                code="TAB_HEALTH_STATS_LOW_SAMPLE_RATIO",
                                severity="high" if has_high_low_sample else "medium",
                                title="Low statistics sample ratio detected",
                                detail=(
                                    "Some statistics were built from weak samples, which can reduce histogram quality."
                                ),
                                evidence=classified_low_sample_stats[:10],
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority="high" if has_high_low_sample else "medium",
                                action=(
                                    "Consider higher-quality statistics updates (for example, larger sampling or fullscan) on critical tables."
                                ),
                                rationale=(
                                    "Higher sample quality improves histogram fidelity and plan stability for skewed distributions."
                                ),
                            )
                        )

                    settings_row = (
                        db_stats_settings["rows"][0] if db_stats_settings["rows"] else {}
                    )
                    auto_create_on = bool(settings_row.get("auto_create_statistics_on", 1))
                    auto_update_on = bool(settings_row.get("auto_update_statistics_on", 1))
                    if include_statistics and (not auto_create_on or not auto_update_on):
                        severity = "high" if not auto_update_on else "medium"
                        findings.append(
                            build_finding(
                                code="TAB_HEALTH_STATS_AUTO_SETTINGS_DISABLED",
                                severity=severity,
                                title="Database automatic statistics settings may increase risk",
                                detail=(
                                    "AUTO_CREATE_STATISTICS or AUTO_UPDATE_STATISTICS is disabled for this database."
                                ),
                                evidence=[
                                    {
                                        "database_name": settings_row.get("database_name", db_name),
                                        "auto_create_statistics_on": auto_create_on,
                                        "auto_update_statistics_on": auto_update_on,
                                        "auto_update_statistics_async_on": bool(
                                            settings_row.get(
                                                "auto_update_statistics_async_on", 0
                                            )
                                        ),
                                    }
                                ],
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority=severity,
                                action=(
                                    "Review database auto statistics settings and align with workload requirements."
                                ),
                                rationale=(
                                    "Disabled automatic statistics maintenance can increase plan-quality drift over time."
                                ),
                            )
                        )

                    if filtered_missing_stats_coverage:
                        has_large_missing_coverage = any(
                            _safe_float(row.get("row_count")) >= STATS_MIN_ROWS_HIGH_SEVERITY
                            for row in filtered_missing_stats_coverage
                        )
                        severity = "high" if has_large_missing_coverage else "medium"
                        findings.append(
                            build_finding(
                                code="TAB_HEALTH_STATS_COVERAGE_HEURISTIC",
                                severity=severity,
                                title="Tables with limited statistics coverage (heuristic)",
                                detail=(
                                    "Metadata suggests some tables have no usable user-table statistics. "
                                    "This is heuristic analysis and not execution-plan verified."
                                ),
                                evidence=filtered_missing_stats_coverage[:10],
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority=severity,
                                action=(
                                    "Review statistics coverage for listed tables and refresh/create relevant statistics during maintenance windows."
                                ),
                                rationale=(
                                    "Insufficient statistics coverage can reduce optimizer accuracy for join and predicate cardinality."
                                ),
                            )
                        )

                    histogram_evidence: list[dict[str, Any]] = []
                    if (
                        include_statistics
                        and include_histogram_analysis
                        and (classified_stale_stats or classified_low_sample_stats)
                    ):
                        candidates = (classified_stale_stats + classified_low_sample_stats)[
                            :histogram_limit
                        ]
                        for candidate in candidates:
                            schema_value = str(candidate.get("schema_name", ""))
                            table_value = str(candidate.get("table_name", ""))
                            stat_value = str(candidate.get("stat_name", ""))
                            if not schema_value or not table_value or not stat_value:
                                continue
                            histogram_rows = state.connection_manager.execute_catalog_query(
                                _instance,
                                db_name,
                                statistics_histogram_query(
                                    schema_value,
                                    table_value,
                                    stat_value,
                                ),
                                200,
                            )["rows"]
                            if not histogram_rows:
                                continue

                            equal_values = [
                                _safe_float(step.get("equal_rows"))
                                for step in histogram_rows
                            ]
                            avg_equal = (
                                sum(equal_values) / len(equal_values)
                                if equal_values
                                else 0.0
                            )
                            max_equal = max(equal_values) if equal_values else 0.0
                            skew_ratio = (
                                max_equal / avg_equal
                                if avg_equal > 0
                                else (999.0 if max_equal > 0 else 0.0)
                            )
                            if skew_ratio >= 10.0:
                                histogram_evidence.append(
                                    {
                                        "schema_name": schema_value,
                                        "table_name": table_value,
                                        "stat_name": stat_value,
                                        "histogram_step_count": len(histogram_rows),
                                        "equal_rows_max": round(max_equal, 2),
                                        "equal_rows_avg": round(avg_equal, 2),
                                        "skew_ratio": round(skew_ratio, 2),
                                    }
                                )

                    if histogram_evidence:
                        findings.append(
                            build_finding(
                                code="TAB_HEALTH_STATS_HISTOGRAM_SKEW",
                                severity="medium",
                                title="Histogram skew indicators detected",
                                detail=(
                                    "Opt-in histogram inspection found strongly skewed distributions in selected statistics."
                                ),
                                evidence=histogram_evidence[:10],
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority="medium",
                                action=(
                                    "Refresh skewed statistics and review parameter-sensitive query paths for the listed objects."
                                ),
                                rationale=(
                                    "Large histogram skew can increase cardinality-estimation errors for selective predicates."
                                ),
                            )
                        )

                    if not findings:
                        findings.append(
                            build_finding(
                                code="TAB_HEALTH_NO_MAJOR_ISSUES",
                                severity="info",
                                title="No major table health issues detected",
                                detail="Current checks did not identify critical, high, or medium table health findings.",
                                evidence=[],
                            )
                        )

                    rows = (
                        len(filtered_sizes)
                        + len(filtered_fragmented)
                        + len(filtered_missing_pk)
                        + len(filtered_stale_stats)
                        + len(filtered_never_updated_stats)
                        + len(filtered_low_sampled_stats)
                        + len(filtered_missing_stats_coverage)
                    )

                    if ctx is not None:
                        await ctx.info(
                            f"[{request_id}] Table health analysis completed - {len(findings)} findings",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "findings_count": len(findings),
                                "tables_scanned": len(filtered_sizes),
                                "decision": decision,
                            },
                        )
                    logger.info(
                        f"Transaction {request_id}: {_tool} - {len(findings)} findings identified"
                    )

                    return build_report_envelope(
                        instance_number=_instance_number,
                        database_name=db_name,
                        tool_name=_tool,
                        summary={
                            "table_count_scanned": len(filtered_sizes),
                            "fragmented_index_rows": len(filtered_fragmented),
                            "missing_primary_key_tables": len(filtered_missing_pk),
                            "stale_statistics_count": len(classified_stale_stats),
                            "never_updated_statistics_count": len(
                                filtered_never_updated_stats
                            ),
                            "low_sampled_statistics_count": len(
                                classified_low_sample_stats
                            ),
                            "missing_statistics_coverage_candidates": len(
                                filtered_missing_stats_coverage
                            ),
                            "database_statistics_settings": {
                                "auto_create_statistics_on": auto_create_on,
                                "auto_update_statistics_on": auto_update_on,
                                "auto_update_statistics_async_on": bool(
                                    settings_row.get(
                                        "auto_update_statistics_async_on", 0
                                    )
                                ),
                            },
                            "statistics_preview": {
                                "stale_statistics": classified_stale_stats[:5],
                                "never_updated_statistics": filtered_never_updated_stats[
                                    :5
                                ],
                                "low_sampled_statistics": classified_low_sample_stats[
                                    :5
                                ],
                                "histogram_skew": histogram_evidence[:5],
                            },
                            "table_size_preview": filtered_sizes[:10],
                        },
                        findings=findings,
                        recommendations=recommendations,
                    )
                except ValueError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    if ctx is not None:
                        await ctx.warning(
                            f"[{request_id}] Validation error: {error_code}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "error": error_code,
                            },
                        )
                    logger.warning(f"Transaction {request_id} denied: {error_code}")
                    raise
                except PermissionError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    if ctx is not None:
                        await ctx.warning(
                            f"[{request_id}] Analysis denied: {error_code}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "error": error_code,
                            },
                        )
                    logger.warning(f"Transaction {request_id} DENIED: {error_code}")
                    raise
                except Exception as exc:
                    decision = "deny"
                    sql_err = _extract_sql_error(exc)
                    if sql_err:
                        error_code = (
                            f"{sql_err['code']}: {sql_err['sql_message']}"
                        )
                    else:
                        error_code = f"SQL_EXECUTION_ERROR: {exc}"
                    state.denied_requests += 1
                    if ctx is not None:
                        extra_payload: dict[str, Any] = {
                            "request_id": request_id,
                            "tool": _tool,
                            "database": database_name,
                            "error": error_code,
                        }
                        if sql_err:
                            extra_payload["sqlstate"] = sql_err["sqlstate"]
                            extra_payload["sql_error_number"] = sql_err["sql_error_number"]
                        await ctx.error(
                            f"[{request_id}] Analysis failed: {error_code}",
                            extra=extra_payload,
                        )
                    logger.error(f"Transaction {request_id} ERROR: {error_code}")
                    raise RuntimeError(error_code) from exc
                finally:
                    latency_ms = int((time.time() - started) * 1000)
                    REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                    REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                    _log_audit_event(
                        request_id=request_id,
                        actor=actor,
                        tool=_tool,
                        instance=_instance,
                        sql=sql_marker,
                        decision=decision,
                        latency_ms=latency_ms,
                        rows=rows,
                        error_code=error_code,
                        auth_ctx=_auth_ctx,
                    )

            registered.append(analyze_tab_health_name)

        analyze_db_data_model_name = (
            f"db_{instance_number}_sql2019_analyze_db_data_model"
        )
        if is_tool_enabled(state.policy, instance_id, "analyze_db_data_model"):

            @mcp.tool(name=analyze_db_data_model_name)
            async def _analyze_db_data_model(
                database_name: str,
                schema_filter: str | None = None,
                max_edges: int = 500,
                actor: str = "system",
                ctx: Context | None = None,
                _tool=analyze_db_data_model_name,
                _instance=instance_id,
                _instance_number=instance_number,
            ):
                """Analyze logical data model quality for a bound SQL instance/database."""
                request_id = str(uuid.uuid4())
                started = time.time()
                decision = "allow"
                error_code = None
                rows = 0
                sql_marker = "ANALYZE_DB_DATA_MODEL"
                _auth_ctx: dict[str, Any] | None = None
                try:
                    if ctx is not None:
                        await ctx.debug(
                            f"[{request_id}] Analyzing data model in {database_name}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                            },
                        )

                    db_name = validate_database_name(database_name)
                    if schema_filter is not None:
                        schema_filter = validate_identifier(
                            schema_filter, "schema_filter"
                        )
                    edge_limit = validate_positive_int(max_edges, "max_edges", 1, 5000)

                    actor, _auth_ctx = await _resolve_actor_and_authorize(
                        actor=actor,
                        tool=_tool,
                        required_privilege="read",
                        ctx=ctx,
                    )
                    state.session_manager.touch(actor, request_id)
                    state.rate_limiter.allow(actor)
                    state.write_guard.enforce(_tool, "SELECT 1")

                    graph_rows = state.connection_manager.execute_catalog_query(
                        _instance, db_name, fk_graph_query(), edge_limit
                    )
                    filtered_rows = graph_rows["rows"]
                    if schema_filter:
                        filtered_rows = [
                            row
                            for row in filtered_rows
                            if str(row.get("parent_schema", "")).lower()
                            == schema_filter.lower()
                            or str(row.get("referenced_schema", "")).lower()
                            == schema_filter.lower()
                        ]
                    graph = build_fk_graph(filtered_rows)

                    findings: list[dict[str, Any]] = []
                    recommendations: list[dict[str, Any]] = []

                    if graph["circular_dependency_tables"]:
                        findings.append(
                            build_finding(
                                code="DATA_MODEL_CIRCULAR_DEPENDENCY",
                                severity="high",
                                title="Circular foreign-key dependencies detected",
                                detail="Cyclic dependencies increase migration and delete/update complexity.",
                                evidence=[
                                    {"table": t}
                                    for t in graph["circular_dependency_tables"]
                                ],
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority="high",
                                action="Refactor cyclic relationships or introduce nullable staging keys.",
                                rationale="Breaking FK cycles simplifies deployment and data lifecycle operations.",
                            )
                        )

                    if graph["edge_count"] == 0:
                        findings.append(
                            build_finding(
                                code="DATA_MODEL_NO_FK_RELATIONSHIPS",
                                severity="medium",
                                title="No foreign-key relationships detected",
                                detail="Database appears to have no declared FK relationships.",
                                evidence=[],
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority="medium",
                                action="Define explicit foreign keys for core entity relationships.",
                                rationale="Declared constraints improve integrity and query plan quality.",
                            )
                        )

                    # ------------------------------------------------------------------
                    # Extended analysis: indexes, normalization, anomalies, datatypes
                    # ------------------------------------------------------------------
                    if ctx is not None:
                        await ctx.debug(
                            f"[{request_id}] Running extended data model analysis (indexes, normalization, anomalies, datatypes)",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                            },
                        )

                    index_result = await _subtool_analyze_indexes(
                        db_name,
                        _instance,
                        state.connection_manager,
                        schema_filter,
                        request_id,
                        ctx,
                    )
                    norm_result = await _subtool_analyze_normalization(
                        db_name,
                        _instance,
                        state.connection_manager,
                        schema_filter,
                        request_id,
                        ctx,
                    )
                    anomaly_result = await _subtool_analyze_anomalies(
                        db_name,
                        _instance,
                        state.connection_manager,
                        schema_filter,
                        request_id,
                        ctx,
                    )
                    datatype_result = await _subtool_analyze_datatype_consistency(
                        db_name,
                        _instance,
                        state.connection_manager,
                        schema_filter,
                        request_id,
                        ctx,
                    )

                    findings.extend(index_result["findings"])
                    findings.extend(norm_result["findings"])
                    findings.extend(anomaly_result["findings"])
                    findings.extend(datatype_result["findings"])
                    recommendations.extend(index_result["recommendations"])
                    recommendations.extend(norm_result["recommendations"])
                    recommendations.extend(anomaly_result["recommendations"])
                    recommendations.extend(datatype_result["recommendations"])

                    if not findings:
                        findings.append(
                            build_finding(
                                code="DATA_MODEL_NO_MAJOR_ISSUES",
                                severity="info",
                                title="No major data model issues detected",
                                detail="All data model checks passed without identifying high-risk structural anomalies.",
                                evidence=[],
                            )
                        )

                    rows = len(filtered_rows)

                    if ctx is not None:
                        await ctx.info(
                            f"[{request_id}] Data model analysis completed - {graph['edge_count']} FK edges, {len(findings)} finding(s)",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "edge_count": graph["edge_count"],
                                "findings_count": len(findings),
                                "decision": decision,
                            },
                        )
                    logger.info(
                        f"Transaction {request_id}: {_tool} - {graph['edge_count']} edges, {len(findings)} findings"
                    )

                    return build_report_envelope(
                        instance_number=_instance_number,
                        database_name=db_name,
                        tool_name=_tool,
                        summary={
                            "model_overview": {
                                "node_count": graph["node_count"],
                                "edge_count": graph["edge_count"],
                                "circular_dependency_count": len(
                                    graph["circular_dependency_tables"]
                                ),
                                "edge_preview": graph["edges"][:20],
                            },
                            "integrity_findings": {
                                "missing_optimizer_index_count": index_result[
                                    "summary"
                                ]["missing_optimizer_count"],
                                "missing_fk_index_count": index_result["summary"][
                                    "missing_fk_index_count"
                                ],
                                "redundant_index_count": index_result["summary"][
                                    "redundant_count"
                                ],
                                "unused_index_count": index_result["summary"][
                                    "unused_count"
                                ],
                                "fk_datatype_mismatches": datatype_result["summary"][
                                    "fk_datatype_mismatches"
                                ],
                            },
                            "normalization_findings": {
                                "transitive_dependency_tables": norm_result["summary"][
                                    "transitive_dependency_tables"
                                ],
                                "update_anomaly_tables": anomaly_result["summary"][
                                    "update_anomaly_tables"
                                ],
                                "soft_delete_no_audit_tables": anomaly_result[
                                    "summary"
                                ]["soft_delete_no_audit_tables"],
                                "heap_tables": anomaly_result["summary"]["heap_tables"],
                            },
                        },
                        findings=findings,
                        recommendations=recommendations,
                    )
                except ValueError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    if ctx is not None:
                        await ctx.warning(
                            f"[{request_id}] Validation error: {error_code}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "error": error_code,
                            },
                        )
                    logger.warning(f"Transaction {request_id} denied: {error_code}")
                    raise
                except PermissionError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    if ctx is not None:
                        await ctx.warning(
                            f"[{request_id}] Analysis denied: {error_code}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "error": error_code,
                            },
                        )
                    logger.warning(f"Transaction {request_id} DENIED: {error_code}")
                    raise
                except Exception as exc:
                    decision = "deny"
                    sql_err = _extract_sql_error(exc)
                    if sql_err:
                        error_code = (
                            f"{sql_err['code']}: {sql_err['sql_message']}"
                        )
                    else:
                        error_code = f"SQL_EXECUTION_ERROR: {exc}"
                    state.denied_requests += 1
                    if ctx is not None:
                        extra_payload: dict[str, Any] = {
                            "request_id": request_id,
                            "tool": _tool,
                            "database": database_name,
                            "error": error_code,
                        }
                        if sql_err:
                            extra_payload["sqlstate"] = sql_err["sqlstate"]
                            extra_payload["sql_error_number"] = sql_err["sql_error_number"]
                        await ctx.error(
                            f"[{request_id}] Analysis failed: {error_code}",
                            extra=extra_payload,
                        )
                    logger.error(f"Transaction {request_id} ERROR: {error_code}")
                    raise RuntimeError(error_code) from exc
                finally:
                    latency_ms = int((time.time() - started) * 1000)
                    REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                    REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                    _log_audit_event(
                        request_id=request_id,
                        actor=actor,
                        tool=_tool,
                        instance=_instance,
                        sql=sql_marker,
                        decision=decision,
                        latency_ms=latency_ms,
                        rows=rows,
                        error_code=error_code,
                        auth_ctx=_auth_ctx,
                    )

            registered.append(analyze_db_data_model_name)

        analyze_sec_config_name = f"db_{instance_number}_sql2019_analyze_sec_config"
        if is_tool_enabled(state.policy, instance_id, "analyze_sec_config"):

            @mcp.tool(name=analyze_sec_config_name)
            async def _analyze_sec_config(
                database_name: str,
                include_server_scope: bool = True,
                actor: str = "system",
                ctx: Context | None = None,
                _tool=analyze_sec_config_name,
                _instance=instance_id,
                _instance_number=instance_number,
            ):
                """Assess security posture and configuration risks for a bound SQL instance/database."""
                request_id = str(uuid.uuid4())
                started = time.time()
                decision = "allow"
                error_code = None
                rows = 0
                sql_marker = "ANALYZE_SEC_CONFIG"
                _auth_ctx: dict[str, Any] | None = None
                try:
                    if ctx is not None:
                        await ctx.debug(
                            f"[{request_id}] Analyzing security configuration in {database_name}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                            },
                        )

                    db_name = validate_database_name(database_name)

                    actor, _auth_ctx = await _resolve_actor_and_authorize(
                        actor=actor,
                        tool=_tool,
                        required_privilege="read",
                        ctx=ctx,
                    )
                    state.session_manager.touch(actor, request_id)
                    state.rate_limiter.allow(actor)
                    state.write_guard.enforce(_tool, "SELECT 1")

                    orphan_users = state.connection_manager.execute_catalog_query(
                        _instance, db_name, orphan_user_query(), 200
                    )
                    elevated_roles = state.connection_manager.execute_catalog_query(
                        _instance, db_name, elevated_roles_query(), 500
                    )
                    backup_rows = state.connection_manager.execute_catalog_query(
                        _instance, "master", backup_recency_query(), 200
                    )

                    xp_cmdshell_enabled = False
                    xp_cmdshell_error = None
                    if include_server_scope:
                        try:
                            xp_rows = state.connection_manager.execute_catalog_query(
                                _instance,
                                "master",
                                "SELECT CAST(value_in_use AS INT) AS value_in_use FROM sys.configurations WHERE name = 'xp_cmdshell'",
                                1,
                            )
                            xp_cmdshell_enabled = bool(
                                xp_rows["rows"]
                                and int(xp_rows["rows"][0].get("value_in_use", 0)) == 1
                            )
                        except Exception as exc:
                            xp_cmdshell_error = str(exc)

                    findings: list[dict[str, Any]] = []
                    recommendations: list[dict[str, Any]] = []

                    if orphan_users["rows"]:
                        findings.append(
                            build_finding(
                                code="SEC_ORPHAN_USERS",
                                severity="medium",
                                title="Orphan database users detected",
                                detail="Users exist without matching server principals.",
                                evidence=redact_sensitive_fields(
                                    orphan_users["rows"][:20]
                                ),
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority="medium",
                                action="Remap or remove orphan users.",
                                rationale="Orphan users create access ambiguity and incident response overhead.",
                            )
                        )

                    if elevated_roles["rows"]:
                        findings.append(
                            build_finding(
                                code="SEC_ELEVATED_ROLE_MEMBERS",
                                severity="high",
                                title="Elevated database role memberships found",
                                detail="High-privilege role assignments should be periodically reviewed.",
                                evidence=redact_sensitive_fields(
                                    elevated_roles["rows"][:30]
                                ),
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority="high",
                                action="Review and minimize elevated role memberships.",
                                rationale="Least-privilege alignment reduces blast radius.",
                            )
                        )

                    if include_server_scope and xp_cmdshell_enabled:
                        findings.append(
                            build_finding(
                                code="SEC_XP_CMDSHELL_ENABLED",
                                severity="critical",
                                title="xp_cmdshell is enabled",
                                detail="xp_cmdshell increases remote-command execution risk on SQL hosts.",
                                evidence=[{"name": "xp_cmdshell", "value_in_use": 1}],
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority="critical",
                                action="Disable xp_cmdshell unless explicitly required and approved.",
                                rationale="Disabling reduces command-injection blast radius.",
                            )
                        )

                    if not findings:
                        findings.append(
                            build_finding(
                                code="SEC_CONFIG_NO_MAJOR_ISSUES",
                                severity="info",
                                title="No major security/configuration issues detected",
                                detail="Current security checks did not identify critical/high findings.",
                                evidence=[],
                            )
                        )

                    rows = (
                        len(orphan_users["rows"])
                        + len(elevated_roles["rows"])
                        + len(backup_rows["rows"])
                    )

                    if ctx is not None:
                        await ctx.info(
                            f"[{request_id}] Security analysis completed - {len(findings)} findings",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "findings_count": len(findings),
                                "orphan_users": len(orphan_users["rows"]),
                                "elevated_roles": len(elevated_roles["rows"]),
                                "decision": decision,
                            },
                        )
                    logger.info(
                        f"Transaction {request_id}: {_tool} - {len(findings)} security findings"
                    )

                    return build_report_envelope(
                        instance_number=_instance_number,
                        database_name=db_name,
                        tool_name=_tool,
                        summary={
                            "server_security": {
                                "xp_cmdshell_enabled": xp_cmdshell_enabled,
                                "xp_cmdshell_check_error": xp_cmdshell_error,
                            },
                            "database_security": {
                                "orphan_user_count": len(orphan_users["rows"]),
                                "elevated_role_memberships": len(
                                    elevated_roles["rows"]
                                ),
                            },
                            "audit_backup": {
                                "backup_recency_rows": len(backup_rows["rows"]),
                            },
                            "hardening_actions": len(recommendations),
                        },
                        findings=findings,
                        recommendations=recommendations,
                    )
                except ValueError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    if ctx is not None:
                        await ctx.warning(
                            f"[{request_id}] Validation error: {error_code}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "error": error_code,
                            },
                        )
                    logger.warning(f"Transaction {request_id} denied: {error_code}")
                    raise
                except PermissionError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    if ctx is not None:
                        await ctx.warning(
                            f"[{request_id}] Analysis denied: {error_code}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "error": error_code,
                            },
                        )
                    logger.warning(f"Transaction {request_id} DENIED: {error_code}")
                    raise
                except Exception as exc:
                    decision = "deny"
                    sql_err = _extract_sql_error(exc)
                    if sql_err:
                        error_code = (
                            f"{sql_err['code']}: {sql_err['sql_message']}"
                        )
                    else:
                        error_code = f"SQL_EXECUTION_ERROR: {exc}"
                    state.denied_requests += 1
                    if ctx is not None:
                        extra_payload: dict[str, Any] = {
                            "request_id": request_id,
                            "tool": _tool,
                            "database": database_name,
                            "error": error_code,
                        }
                        if sql_err:
                            extra_payload["sqlstate"] = sql_err["sqlstate"]
                            extra_payload["sql_error_number"] = sql_err["sql_error_number"]
                        await ctx.error(
                            f"[{request_id}] Analysis failed: {error_code}",
                            extra=extra_payload,
                        )
                    logger.error(f"Transaction {request_id} ERROR: {error_code}")
                    raise RuntimeError(error_code) from exc
                finally:
                    latency_ms = int((time.time() - started) * 1000)
                    REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                    REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                    _log_audit_event(
                        request_id=request_id,
                        actor=actor,
                        tool=_tool,
                        instance=_instance,
                        sql=sql_marker,
                        decision=decision,
                        latency_ms=latency_ms,
                        rows=rows,
                        error_code=error_code,
                        auth_ctx=_auth_ctx,
                    )

            registered.append(analyze_sec_config_name)

        sessions_dashboard_name = f"db_{instance_number}_sql2019_sessions_dashboard"
        if is_tool_enabled(state.policy, instance_id, "sessions_dashboard"):

            @mcp.tool(name=sessions_dashboard_name)
            async def _sessions_dashboard(
                database_name: str = "master",
                lookback_minutes: int = 15,
                include_locks: bool = True,
                actor: str = "system",
                ctx: Context | None = None,
                _tool=sessions_dashboard_name,
                _instance=instance_id,
                _instance_number=instance_number,
            ):
                """Generate URL to interactive sessions dashboard for SQL Server diagnostics."""
                request_id = str(uuid.uuid4())
                started = time.time()
                decision = "allow"
                error_code = None
                rows = 0
                sql_marker = "SESSIONS_DASHBOARD"
                _auth_ctx: dict[str, Any] | None = None
                try:
                    if ctx is not None:
                        await ctx.debug(
                            f"[{request_id}] Generating sessions dashboard for {database_name}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                            },
                        )

                    db_name = validate_database_name(database_name)
                    validate_positive_int(lookback_minutes, "lookback_minutes", 1, 1440)

                    actor, _auth_ctx = await _resolve_actor_and_authorize(
                        actor=actor,
                        tool=_tool,
                        required_privilege="read",
                        ctx=ctx,
                    )
                    state.session_manager.touch(actor, request_id)
                    state.rate_limiter.allow(actor)
                    state.write_guard.enforce(_tool, "SELECT 1")

                    sessions = state.connection_manager.execute_catalog_query(
                        _instance, db_name, active_sessions_query(200), 200
                    )
                    lock_rows = {"rows": []}
                    tran_lock_rows = {"rows": []}
                    waiting_rows = {"rows": []}
                    blocking_chain_rows = {"rows": []}
                    if include_locks:
                        lock_rows = state.connection_manager.execute_catalog_query(
                            _instance, db_name, lock_chain_query(200), 200
                        )
                        tran_lock_rows = state.connection_manager.execute_catalog_query(
                            _instance, db_name, tran_locks_query(200), 200
                        )
                        waiting_rows = state.connection_manager.execute_catalog_query(
                            _instance, db_name, waiting_tasks_query(200), 200
                        )
                        blocking_chain_rows = (
                            state.connection_manager.execute_catalog_query(
                                _instance, db_name, blocking_chain_query(200), 200
                            )
                        )

                    head_blockers: list[int] = []
                    for row in lock_rows["rows"]:
                        blocker = row.get("blocking_session_id")
                        if blocker is None:
                            continue
                        try:
                            blocker_id = int(blocker)
                        except (TypeError, ValueError):
                            continue
                        if blocker_id > 0 and blocker_id not in head_blockers:
                            head_blockers.append(blocker_id)

                    rows = (
                        len(sessions["rows"])
                        + len(lock_rows["rows"])
                        + len(tran_lock_rows["rows"])
                        + len(waiting_rows["rows"])
                        + len(blocking_chain_rows["rows"])
                    )

                    refresh_url = f"/diagnostics/dashboards/{request_id}/refresh"
                    full_payload = build_sessions_dashboard_full(
                        instance_number=_instance_number,
                        database_name=db_name,
                        sessions=sessions["rows"],
                        lock_chains=lock_rows["rows"],
                        tran_locks=tran_lock_rows["rows"],
                        waiting_tasks=waiting_rows["rows"],
                        head_blockers=head_blockers,
                        blocking_chains=blocking_chain_rows["rows"],
                        refresh_url=refresh_url,
                    )

                    dashboard_url = register_dashboard_page_with_metadata(
                        request_id,
                        full_payload["html"],
                        ttl_seconds=900,
                        metadata={
                            "instance_id": _instance,
                            "instance_number": _instance_number,
                            "database_name": db_name,
                            "lookback_minutes": lookback_minutes,
                            "include_locks": include_locks,
                        },
                    )
                    sanitized_dashboard_url = _sanitize_dashboard_url(dashboard_url)
                    expires_at_utc = get_dashboard_page_expiry_utc(request_id)

                    if ctx is not None:
                        await ctx.info(
                            f"[{request_id}] Dashboard URL generated - {len(sessions['rows'])} sessions, {len(head_blockers)} blockers",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "sessions": len(sessions["rows"]),
                                "head_blockers": len(head_blockers),
                                "decision": decision,
                                "dashboard_url": sanitized_dashboard_url,
                            },
                        )
                    logger.info(
                        f"Transaction {request_id}: {_tool} - {len(sessions['rows'])} sessions analyzed - URL: {sanitized_dashboard_url}"
                    )

                    return {
                        "dashboard_url": dashboard_url,
                        "request_id": request_id,
                        "expires_at_utc": expires_at_utc,
                        **{
                            k: v
                            for k, v in full_payload.items()
                            if k
                            not in {"dashboard_url", "request_id", "expires_at_utc"}
                        },
                    }
                except ValueError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    if ctx is not None:
                        await ctx.warning(
                            f"[{request_id}] Validation error: {error_code}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "error": error_code,
                            },
                        )
                    logger.warning(f"Transaction {request_id} denied: {error_code}")
                    raise
                except PermissionError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    if ctx is not None:
                        await ctx.warning(
                            f"[{request_id}] Dashboard generation denied: {error_code}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "error": error_code,
                            },
                        )
                    logger.warning(f"Transaction {request_id} DENIED: {error_code}")
                    raise
                except Exception as exc:
                    decision = "deny"
                    sql_err = _extract_sql_error(exc)
                    if sql_err:
                        error_code = (
                            f"{sql_err['code']}: {sql_err['sql_message']}"
                        )
                    else:
                        error_code = f"SQL_EXECUTION_ERROR: {exc}"
                    state.denied_requests += 1
                    if ctx is not None:
                        extra_payload: dict[str, Any] = {
                            "request_id": request_id,
                            "tool": _tool,
                            "database": database_name,
                            "error": error_code,
                        }
                        if sql_err:
                            extra_payload["sqlstate"] = sql_err["sqlstate"]
                            extra_payload["sql_error_number"] = sql_err["sql_error_number"]
                        await ctx.error(
                            f"[{request_id}] Dashboard generation failed: {error_code}",
                            extra=extra_payload,
                        )
                    logger.error(f"Transaction {request_id} ERROR: {error_code}")
                    raise RuntimeError(error_code) from exc
                finally:
                    latency_ms = int((time.time() - started) * 1000)
                    REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                    REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                    _log_audit_event(
                        request_id=request_id,
                        actor=actor,
                        tool=_tool,
                        instance=_instance,
                        sql=sql_marker,
                        decision=decision,
                        latency_ms=latency_ms,
                        rows=rows,
                        error_code=error_code,
                        auth_ctx=_auth_ctx,
                    )

            registered.append(sessions_dashboard_name)

        top_statements_name = f"db_{instance_number}_sql2019_top_statements"
        if is_tool_enabled(state.policy, instance_id, "top_statements"):

            @mcp.tool(name=top_statements_name)
            async def _top_statements(
                database_name: str,
                top_n: int = 25,
                lookback_minutes: int = 1440,
                view_mode: str = "COMPACT",
                actor: str = "system",
                ctx: Context | None = None,
                _tool=top_statements_name,
                _instance=instance_id,
                _instance_number=instance_number,
            ):
                """Analyze top longest-running SQL statements with recommendations.

                Inputs:
                - database_name: database to analyze.
                - top_n: max statements to return (1..500).
                - lookback_minutes: Query Store lookback window (1..10080, DMV fallback ignores).
                - view_mode: COMPACT or FULL.
                - actor: caller identity.

                Output:
                - longest-running statements with execution counts.
                - findings and recommendations for index, rewrite, hint, and partition strategies.
                """
                request_id = str(uuid.uuid4())
                started = time.time()
                decision = "allow"
                error_code = None
                rows = 0
                sql_marker = "TOP_STATEMENTS"
                _auth_ctx: dict[str, Any] | None = None
                try:
                    if ctx is not None:
                        await ctx.debug(
                            f"[{request_id}] Analyzing top statements in {database_name}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                            },
                        )

                    db_name = validate_database_name(database_name)
                    size = validate_positive_int(top_n, "top_n", 1, 500)
                    lb_minutes = validate_positive_int(
                        lookback_minutes, "lookback_minutes", 1, 10080
                    )
                    normalized = view_mode.strip().upper()
                    if normalized not in {"FULL", "COMPACT"}:
                        raise ValueError(
                            "INVALID_INPUT: view_mode must be FULL or COMPACT"
                        )

                    actor, _auth_ctx = await _resolve_actor_and_authorize(
                        actor=actor,
                        tool=_tool,
                        required_privilege="read",
                        ctx=ctx,
                    )
                    state.session_manager.touch(actor, request_id)
                    state.rate_limiter.allow(actor)
                    state.write_guard.enforce(_tool, "SELECT 1")

                    stmt_rows, obj_rows, data_source = (
                        await _collect_top_statement_metrics(
                            state.connection_manager,
                            _instance,
                            db_name,
                            size,
                            lb_minutes,
                        )
                    )

                    findings, recommendations = _recommend_top_statement_actions(
                        stmt_rows, obj_rows
                    )

                    if not findings:
                        if data_source == "unavailable":
                            findings.append(
                                build_finding(
                                    code="TOP_STMT_TELEMETRY_UNAVAILABLE",
                                    severity="error",
                                    title="Statement telemetry source unavailable",
                                    detail="Both Query Store and DMV data sources are unavailable for this database. No statement performance analysis can be performed.",
                                    evidence=[],
                                )
                            )
                        else:
                            findings.append(
                                build_finding(
                                    code="TOP_STMT_NO_CRITICAL_ISSUES",
                                    severity="info",
                                    title="No critical statement performance issues detected",
                                    detail="Current analysis did not identify high-severity statement patterns.",
                                    evidence=[],
                                )
                            )

                    rows = len(stmt_rows) + len(obj_rows)

                    if ctx is not None:
                        await ctx.info(
                            f"[{request_id}] Top statements analysis completed - {len(findings)} findings",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "findings_count": len(findings),
                                "statements_analyzed": len(stmt_rows),
                                "data_source": data_source,
                                "decision": decision,
                            },
                        )
                    logger.info(
                        f"Transaction {request_id}: {_tool} - {len(findings)} findings from {data_source}"
                    )

                    report = build_report_envelope(
                        instance_number=_instance_number,
                        database_name=db_name,
                        tool_name=_tool,
                        summary={
                            "statements_analyzed": len(stmt_rows),
                            "objects_checked": len(obj_rows),
                            "lookback_minutes": lb_minutes,
                            "data_source": data_source,
                        },
                        findings=findings,
                        recommendations=recommendations,
                    )
                    report["top_statements"] = stmt_rows[:size]
                    report["data_source"] = data_source
                    return report
                except ValueError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    if ctx is not None:
                        await ctx.warning(
                            f"[{request_id}] Validation error: {error_code}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "error": error_code,
                            },
                        )
                    logger.warning(f"Transaction {request_id} denied: {error_code}")
                    raise
                except PermissionError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    if ctx is not None:
                        await ctx.warning(
                            f"[{request_id}] Analysis denied: {error_code}",
                            extra={
                                "request_id": request_id,
                                "tool": _tool,
                                "database": database_name,
                                "error": error_code,
                            },
                        )
                    logger.warning(f"Transaction {request_id} DENIED: {error_code}")
                    raise
                except Exception as exc:
                    decision = "deny"
                    sql_err = _extract_sql_error(exc)
                    if sql_err:
                        error_code = (
                            f"{sql_err['code']}: {sql_err['sql_message']}"
                        )
                    else:
                        error_code = f"SQL_EXECUTION_ERROR: {exc}"
                    state.denied_requests += 1
                    if ctx is not None:
                        extra_payload: dict[str, Any] = {
                            "request_id": request_id,
                            "tool": _tool,
                            "database": database_name,
                            "error": error_code,
                        }
                        if sql_err:
                            extra_payload["sqlstate"] = sql_err["sqlstate"]
                            extra_payload["sql_error_number"] = sql_err["sql_error_number"]
                        await ctx.error(
                            f"[{request_id}] Analysis failed: {error_code}",
                            extra=extra_payload,
                        )
                    logger.error(f"Transaction {request_id} ERROR: {error_code}")
                    raise RuntimeError(error_code) from exc
                finally:
                    latency_ms = int((time.time() - started) * 1000)
                    REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                    REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                    _log_audit_event(
                        request_id=request_id,
                        actor=actor,
                        tool=_tool,
                        instance=_instance,
                        sql=sql_marker,
                        decision=decision,
                        latency_ms=latency_ms,
                        rows=rows,
                        error_code=error_code,
                        auth_ctx=_auth_ctx,
                    )

            registered.append(top_statements_name)

    return registered


# Server-side logging
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# SQL error extraction helper
# ---------------------------------------------------------------------------

_SQLSTATE_DESCRIPTIONS: dict[str, str] = {
    "42S02": "Invalid object name. The table, view, or function referenced does not exist "
             "(check typos, database context, object permissions, and whether the view/DMV exists on this SQL Server build).",
    "42S22": "Invalid column name. One or more columns referenced in the query do not exist "
             "on the target object.",
    "42000": "Syntax error or access violation in the SQL statement.",
    "42S01": "Object already exists. A CREATE operation conflicts with an existing object.",
    "08001": "Unable to connect to the SQL Server data source.",
    "28000": "Invalid authorization specification. Check login credentials or permissions.",
    "08S01": "Communication link failure. The connection to SQL Server was lost.",
    "HYT00": "Query timeout expired.",
    "HY000": "General ODBC error. Check error details for more information.",
}


def _extract_sql_error(exc: BaseException) -> dict[str, Any] | None:
    """Extract structured SQL error info from a pyodbc or DB-API exception.

    Returns a dict with ``code``, ``sqlstate``, ``sql_message``,
    ``sql_error_number``, and ``description`` keys, or ``None`` if the
    exception is not a recognised SQL-level error.
    """
    try:
        raw = exc.args
        if isinstance(raw, (tuple, list)) and len(raw) >= 2:
            sqlstate = str(raw[0]).strip()
            message = str(raw[1]).strip()
        elif isinstance(raw, (tuple, list)) and len(raw) == 1:
            sqlstate = "HY000"
            message = str(raw[0]).strip()
        else:
            sqlstate = ""
            message = str(exc)
        if not sqlstate:
            return None
        description = _SQLSTATE_DESCRIPTIONS.get(
            sqlstate, "An unexpected SQL error occurred. Review the error details."
        )
        error_number: int | None = None
        for token in message.split(")"):
            token = token.strip("( ")
            if token.isdigit():
                error_number = int(token)
                break
        return {
            "code": f"SQL_ERROR_{sqlstate}",
            "sqlstate": sqlstate,
            "sql_message": message,
            "sql_error_number": error_number,
            "description": description,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# top_statements – threshold constants
# ---------------------------------------------------------------------------

TOP_STMT_DURATION_HIGH_US = 5000000        # 5 seconds
TOP_STMT_DURATION_MEDIUM_US = 1000000      # 1 second
TOP_STMT_EXEC_COUNT_HIGH = 10000
TOP_STMT_SCAN_RATIO_HIGH = 0.80
TOP_STMT_SCAN_RATIO_MEDIUM = 0.50
TOP_STMT_ROW_COUNT_LARGE = 10000000        # 10M rows – partition candidate
TOP_STMT_READ_PRESSURE_FACTOR = 10         # reads vs writes ratio for index hints


# ---------------------------------------------------------------------------
# top_statements – reusable helpers
# ---------------------------------------------------------------------------


async def _collect_top_statement_metrics(
    connection_manager: Any,
    instance_id: str,
    database_name: str,
    top_n: int,
    lookback_minutes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Collect statement-level metrics and object-pressure data.

    Returns (statement_rows, object_pressure_rows, data_source).
    ``data_source`` is ``"query_store"``, ``"dmv_fallback"``, or ``"unavailable"``.
    Each query path is independently resilient — failure in one does not block
    the others.
    """
    # --- statement metrics ---
    stmt_rows: list[dict[str, Any]] = []
    data_source = "query_store"
    try:
        stmt_result = connection_manager.execute_catalog_query(
            instance_id,
            database_name,
            top_statements_query_store_query(top_n, lookback_minutes),
            top_n,
        )
        stmt_rows = stmt_result["rows"]
    except Exception as exc:
        sql_state = getattr(exc, "sqlstate", None) or ""
        exc_str = str(exc).lower()
        is_query_store_unavailable = (
            sql_state == "42S02"
            or "query_store" in exc_str
            or "invalid object name" in exc_str
        )
        if not is_query_store_unavailable:
            raise
        data_source = "dmv_fallback"
        try:
            fallback_sql = top_statements_dmv_fallback_query(top_n)
            fallback_result = connection_manager.execute_catalog_query(
                instance_id, database_name, fallback_sql, top_n
            )
            stmt_rows = fallback_result["rows"]
        except Exception:
            data_source = "unavailable"
            stmt_rows = []

    # --- object pressure ---
    obj_rows: list[dict[str, Any]] = []
    try:
        obj_result = connection_manager.execute_catalog_query(
            instance_id,
            database_name,
            top_statements_object_pressure_query(top_n),
            top_n,
        )
        obj_rows = obj_result["rows"]
    except Exception:
        obj_rows = []

    return _normalize_top_statement_rows(stmt_rows), _normalize_object_pressure_rows(obj_rows), data_source


def _normalize_object_pressure_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Cast object-pressure numeric fields to safe types, replacing None with 0."""
    result: list[dict[str, Any]] = []
    for row in rows:
        normalized: dict[str, Any] = {}
        for key, val in row.items():
            if val is None:
                if key in ("user_seeks", "user_scans", "user_lookups", "user_updates", "row_count"):
                    normalized[key] = 0
                elif key == "scan_ratio":
                    normalized[key] = 0.0
                else:
                    normalized[key] = val
            else:
                normalized[key] = val
        result.append(normalized)
    return result


def _normalize_top_statement_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Cast numeric fields and truncate SQL text to stable output shape."""
    result: list[dict[str, Any]] = []
    for row in rows:
        normalized: dict[str, Any] = {}
        for key, val in row.items():
            if val is None:
                normalized[key] = None
                continue
            if key in (
                "weighted_avg_duration_us",
                "max_duration_us",
                "execution_count",
                "weighted_avg_cpu_time_us",
                "weighted_avg_logical_reads",
                "weighted_avg_physical_reads",
                "weighted_avg_log_bytes",
            ):
                try:
                    normalized[key] = int(float(val))
                except (TypeError, ValueError):
                    normalized[key] = 0
            elif key == "query_sql_text" and isinstance(val, str):
                normalized[key] = val[:4000] if len(val) > 4000 else val
            else:
                normalized[key] = val
        result.append(normalized)
    return result


def _recommend_top_statement_actions(
    statement_rows: list[dict[str, Any]],
    object_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Produce findings and recommendations for index, rewrite, hint, and partition strategies."""
    findings: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []

    if not statement_rows and not object_rows:
        return findings, recommendations

    # --- duration-based findings ---
    high_duration = [
        r
        for r in statement_rows
        if (r.get("weighted_avg_duration_us") or 0) >= TOP_STMT_DURATION_HIGH_US
    ]
    medium_duration = [
        r
        for r in statement_rows
        if TOP_STMT_DURATION_MEDIUM_US
        <= (r.get("weighted_avg_duration_us") or 0)
        < TOP_STMT_DURATION_HIGH_US
    ]
    high_exec = [
        r
        for r in statement_rows
        if (r.get("execution_count") or 0) >= TOP_STMT_EXEC_COUNT_HIGH
    ]

    if high_duration:
        top_dur = high_duration[0]
        evidence = [
            {
                "query_id": r.get("query_id"),
                "duration_us": r.get("weighted_avg_duration_us"),
                "execution_count": r.get("execution_count"),
                "sql_fragment": (r.get("query_sql_text", "") or "")[:500],
            }
            for r in high_duration[:10]
        ]
        findings.append(
            build_finding(
                code="TOP_STMT_HIGH_DURATION",
                severity="high",
                title="Long-running statements detected",
                detail=f"Top statement averaged {(top_dur.get('weighted_avg_duration_us') or 0) // 1000} ms and executed {top_dur.get('execution_count') or 0} times.",
                evidence=evidence,
            )
        )
        recommendations.append(
            build_recommendation(
                priority="high",
                action="Review execution plans for the listed high-duration statements. "
                "Consider index additions, query rewrites, or partitioning to reduce scan cost.",
                rationale="Statements exceeding 5 seconds average duration indicate potential I/O or plan inefficiencies.",
            )
        )

    if high_exec:
        top_exec = high_exec[0]
        findings.append(
            build_finding(
                code="TOP_STMT_HIGH_EXECUTION_COUNT",
                severity="medium",
                title="High-frequency statements identified",
                detail=f"Top statement executed {top_exec.get('execution_count') or 0} times.",
                evidence=[
                    {
                        "query_id": r.get("query_id"),
                        "execution_count": r.get("execution_count"),
                        "sql_fragment": (r.get("query_sql_text", "") or "")[:500],
                    }
                    for r in high_exec[:10]
                ],
            )
        )
        recommendations.append(
            build_recommendation(
                priority="medium",
                action="Consider parameterized queries for high-frequency statements. "
                "Evaluate plan guide or OPTIMIZE FOR hints where parameter sniffing causes variance.",
                rationale="Thousands of executions can amplify small inefficiencies into measurable resource pressure.",
            )
        )

    # --- object-level index / partition recommendations ---
    high_scan = [
        r
        for r in object_rows
        if (r.get("scan_ratio") or 0) >= TOP_STMT_SCAN_RATIO_HIGH
        and (r.get("row_count") or 0) > 0
    ]
    large_tables = [
        r
        for r in object_rows
        if (r.get("row_count") or 0) >= TOP_STMT_ROW_COUNT_LARGE
    ]

    if high_scan:
        top_scan = high_scan[0]
        findings.append(
            build_finding(
                code="TOP_STMT_HIGH_SCAN_PRESSURE",
                severity="high" if (top_scan.get("scan_ratio") or 0) >= 0.9 else "medium",
                title="Objects with dominant scan access patterns",
                detail=f"Table {top_scan.get('schema_name')}.{top_scan.get('table_name')} has {(top_scan.get('scan_ratio') or 0):.0%} scan ratio.",
                evidence=high_scan[:10],
            )
        )
        recommendations.append(
            build_recommendation(
                priority="high" if top_scan.get("scan_ratio", 0) >= 0.9 else "medium",
                action="Add targeted nonclustered indexes on scan-heavy tables. "
                "Evaluate covering indexes for the correlated high-duration statements above.",
                rationale="Scan-dominated workloads can benefit from indexes that satisfy predicates and reduce I/O.",
            )
        )

    if large_tables:
        top_large = large_tables[0]
        findings.append(
            build_finding(
                code="TOP_STMT_LARGE_TABLE_CANDIDATE",
                severity="medium",
                title="Large tables identified as partition candidates",
                detail=f"Table {top_large.get('schema_name')}.{top_large.get('table_name')} has {(top_large.get('row_count') or 0):,} rows.",
                evidence=large_tables[:10],
            )
        )
        recommendations.append(
            build_recommendation(
                priority="medium",
                action="Evaluate table partitioning strategy for tables exceeding 10M rows. "
                "Consider partition-aligned indexes and sliding-window maintenance.",
                rationale="Partitioning reduces scan range and facilitates faster data archival/retention for large tables.",
            )
        )

    # --- hint / rewrite catch-all for medium-duration statements ---
    if medium_duration:
        findings.append(
            build_finding(
                code="TOP_STMT_REWRITE_CANDIDATE",
                severity="medium",
                title="Medium-duration statements may benefit from rewrites or hints",
                detail=f"{len(medium_duration)} statements fall in the 1s–5s average-duration range.",
                evidence=[
                    {
                        "query_id": r.get("query_id"),
                        "duration_us": (r.get("weighted_avg_duration_us") or 0),
                        "sql_fragment": (r.get("query_sql_text", "") or "")[:500],
                    }
                    for r in medium_duration[:10]
                ],
            )
        )
        recommendations.append(
            build_recommendation(
                priority="medium",
                action="Review query structure for medium-duration statements. "
                "Consider CTE or temp-table rewrites, query hints (HASH/LOOP/MERGE JOIN, "
                "MAXDOP, RECOMPILE) where plan instability is observed.",
                rationale="Statements in the 1–5 second range often respond well to targeted tuning without schema changes.",
            )
        )

    return findings, recommendations
