from __future__ import annotations

from datetime import datetime, timezone
import time
import uuid
from typing import Any

from fastmcp import Context, FastMCP

from src.diagnostics.routes import REQUEST_COUNT, REQUEST_LATENCY
from src.tools.analysis_contracts import build_finding, build_recommendation, build_report_envelope
from src.tools.dashboard_payloads import build_sessions_dashboard
from src.tools.input_validation import validate_database_name, validate_identifier, validate_positive_int
from src.tools.model_graph import build_fk_graph
from src.tools.query_catalog import (
    active_sessions_query,
    backup_recency_query,
    elevated_roles_query,
    fk_graph_query,
    fragmented_indexes_query,
    lock_chain_query,
    missing_pk_query,
    orphan_user_query,
    table_size_query,
)
from src.tools.security_redaction import redact_sensitive_fields
from src.tools.tool_flags import is_tool_enabled
from src.tools.tool_registry import generate_tool_specs


def register_sql_tools(mcp: FastMCP, state: Any) -> list[str]:
    registered: list[str] = []

    instance_ids = state.connection_manager.list_enabled_instances()
    number_by_instance = {instance_id: idx for idx, instance_id in enumerate(instance_ids, start=1)}

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
        try:
            state.session_manager.touch(actor, request_id)
            state.rate_limiter.allow(actor)
            state.write_guard.enforce(tool, sql)
            result = state.connection_manager.execute_read(instance, sql, max_rows)
            rows = len(result)
            return {"instance": instance, "tool": tool, "row_count": rows, "rows": result}
        except PermissionError as exc:
            decision = "deny"
            state.denied_requests += 1
            error_code = str(exc)
            raise
        finally:
            latency_ms = int((time.time() - started) * 1000)
            REQUEST_COUNT.labels(tool, instance, decision).inc()
            REQUEST_LATENCY.labels(tool, instance).observe(latency_ms)
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
            )
            if ctx is not None:
                await ctx.info(f"{tool} completed with decision={decision} latency_ms={latency_ms}")

    for spec in generate_tool_specs(instance_ids):
        tool_name = spec.full_name
        instance = spec.instance

        if not is_tool_enabled(state.policy, instance, spec.toolname):
            continue

        if spec.toolname == "select":

            @mcp.tool(name=tool_name)
            async def _select(sql: str, actor: str = "unknown", ctx: Context | None = None, _tool=tool_name, _instance=instance):
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
                try:
                    state.session_manager.touch(actor, request_id)
                    state.rate_limiter.allow(actor)
                    state.write_guard.enforce(_tool, sql)
                    result = state.connection_manager.execute_read(_instance, sql, state.policy.max_result_rows)
                    rows = len(result)
                    return {"instance": _instance, "rows": result, "row_count": rows}
                except PermissionError as exc:
                    decision = "deny"
                    state.denied_requests += 1
                    error_code = str(exc)
                    raise
                finally:
                    latency_ms = int((time.time() - started) * 1000)
                    REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                    REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                    state.audit_logger.log_event(
                        request_id=request_id,
                        actor=actor,
                        tool=_tool,
                        instance=_instance,
                        sql=sql,
                        decision=decision,
                        latency_ms=latency_ms,
                        rows=rows,
                        error_code=error_code,
                    )
                    if ctx is not None:
                        await ctx.info(f"{_tool} completed with decision={decision} latency_ms={latency_ms}")

        elif spec.toolname == "exec_proc":

            @mcp.tool(name=tool_name)
            async def _exec_proc(proc_name: str, params: list[str | int | float | bool | None] | None = None, actor: str = "unknown", ctx: Context | None = None, _tool=tool_name, _instance=instance):
                """Execute an approved stored procedure on the bound instance.

                Inputs:
                - proc_name: procedure to execute.
                - params: positional procedure arguments.
                - actor: caller identity.

                Output:
                - status payload containing procedure and rowcount.
                """
                request_id = str(uuid.uuid4())
                started = time.time()
                decision = "allow"
                error_code = None
                sql = f"EXEC {proc_name}"
                try:
                    state.session_manager.touch(actor, request_id)
                    state.rate_limiter.allow(actor)
                    state.write_guard.enforce(_tool, "UPDATE __policy_probe__ SET x = 1")
                    result = state.connection_manager.execute_proc(_instance, proc_name, params)
                    return {"instance": _instance, **result}
                except PermissionError as exc:
                    decision = "deny"
                    state.denied_requests += 1
                    error_code = str(exc)
                    raise
                finally:
                    latency_ms = int((time.time() - started) * 1000)
                    REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                    REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                    state.audit_logger.log_event(
                        request_id=request_id,
                        actor=actor,
                        tool=_tool,
                        instance=_instance,
                        sql=sql,
                        decision=decision,
                        latency_ms=latency_ms,
                        rows=0,
                        error_code=error_code,
                    )
                    if ctx is not None:
                        await ctx.info(f"{_tool} completed with decision={decision} latency_ms={latency_ms}")

        elif spec.toolname == "latency_report":

            @mcp.tool(name=tool_name)
            async def _latency_report(actor: str = "system", _tool=tool_name, _instance=instance):
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
            async def _block_report(actor: str = "system", ctx: Context | None = None, _tool=tool_name, _instance=instance):
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
            "required_parameters": ["database_name", "request_datetime_utc", "sql_statement", "view_mode"],
            "optional_parameters": ["actor"],
            "output_fields": [
                "instance_number",
                "database_name",
                "request_datetime_utc",
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
            "optional_parameters": ["schema_name", "table_name", "include_indexes", "top_n", "actor"],
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
            "optional_parameters": ["database_name", "lookback_minutes", "include_locks", "actor"],
            "output_fields": ["content_type", "html", "data"],
            "operational_behavior": "Collects bounded DMV data and formats a dashboard payload for MCP clients.",
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
            try:
                state.session_manager.touch(actor, request_id)
                state.rate_limiter.allow(actor)
                payload = state.connection_manager.fetch_single_row_in_database(_instance, "master", sql)
                row_count = 1 if payload else 0
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
                state.audit_logger.log_event(
                    request_id=request_id,
                    actor=actor,
                    tool=_tool,
                    instance=_instance,
                    sql=sql,
                    decision=decision,
                    latency_ms=latency_ms,
                    rows=row_count,
                    error_code=error_code,
                )
                if ctx is not None:
                    await ctx.info(f"{_tool} completed with decision={decision} latency_ms={latency_ms}")

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
            try:
                state.session_manager.touch(actor, request_id)
                state.rate_limiter.allow(actor)
                info = state.connection_manager.fetch_single_row_in_database(_instance, "master", sql)
                prefix = f"db_{_instance_number}_sql2019_"
                matching = [name for name in state.registered_tools if name.startswith(prefix)]
                tools = []
                for name in matching:
                    suffix = name[len(prefix) :]
                    meta = tool_metadata_by_suffix.get(suffix, {"description": "Registered MCP tool", "required_parameters": []})
                    tools.append(
                        {
                            "name": name,
                            "description": meta["description"],
                            "required_parameters": meta["required_parameters"],
                            "optional_parameters": meta.get("optional_parameters", []),
                            "output_fields": meta.get("output_fields", []),
                            "operational_behavior": meta.get("operational_behavior", "Registered MCP tool"),
                        }
                    )
                row_count = len(tools)
                return {
                    "instance_number": _instance_number,
                    "database_instance_name": info.get("instance_name"),
                    "ip_address": info.get("ip_address"),
                    "system_date": info.get("current_system_date"),
                    "tools": tools,
                }
            except Exception as exc:
                decision = "deny"
                error_code = f"SQL_EXECUTION_ERROR: {exc}"
                state.denied_requests += 1
                raise RuntimeError(error_code) from exc
            finally:
                latency_ms = int((time.time() - started) * 1000)
                REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                state.audit_logger.log_event(
                    request_id=request_id,
                    actor=actor,
                    tool=_tool,
                    instance=_instance,
                    sql=sql,
                    decision=decision,
                    latency_ms=latency_ms,
                    rows=row_count,
                    error_code=error_code,
                )
                if ctx is not None:
                    await ctx.info(f"{_tool} completed with decision={decision} latency_ms={latency_ms}")

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
            try:
                state.session_manager.touch(actor, request_id)
                state.rate_limiter.allow(actor)
                rows = state.connection_manager.list_objects(_instance, database_name, object_type)
                row_count = len(rows)
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
                raise
            except Exception as exc:
                decision = "deny"
                error_code = f"SQL_EXECUTION_ERROR: {exc}"
                state.denied_requests += 1
                raise RuntimeError(error_code) from exc
            finally:
                latency_ms = int((time.time() - started) * 1000)
                REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                state.audit_logger.log_event(
                    request_id=request_id,
                    actor=actor,
                    tool=_tool,
                    instance=_instance,
                    sql=sql,
                    decision=decision,
                    latency_ms=latency_ms,
                    rows=row_count,
                    error_code=error_code,
                )
                if ctx is not None:
                    await ctx.info(f"{_tool} completed with decision={decision} latency_ms={latency_ms}")

        registered.append(list_object_name)

        execute_query_name = f"db_{instance_number}_sql2019_execute_query"

        @mcp.tool(name=execute_query_name)
        async def _execute_query(
            database_name: str,
            request_datetime_utc: str,
            sql_statement: str,
            view_mode: str,
            actor: str = "system",
            ctx: Context | None = None,
            _tool=execute_query_name,
            _instance=instance_id,
            _instance_number=instance_number,
        ):
            """Execute SQL against a specific database context on the bound instance.

            Inputs:
            - database_name: execution context DB.
            - request_datetime_utc: caller timestamp.
            - sql_statement: SQL text (supports fully qualified cross-database names).
            - view_mode: COMPACT or FULL.

            FULL mode appends explain-plan summary when available.
            """
            request_id = str(uuid.uuid4())
            started = time.time()
            decision = "allow"
            error_code = None
            rows = 0
            try:
                normalized = view_mode.strip().upper()
                if normalized not in {"FULL", "COMPACT"}:
                    raise ValueError("INVALID_INPUT: view_mode must be FULL or COMPACT")

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
                    "request_datetime_utc": request_datetime_utc,
                    "execution_datetime_utc": datetime.now(timezone.utc).isoformat(),
                    "view_mode": normalized,
                    "columns": result["columns"],
                    "row_count": rows,
                    "rows": result["rows"],
                }

                if normalized == "FULL":
                    try:
                        output["plan"] = state.connection_manager.explain_query(_instance, database_name, sql_statement)
                    except Exception as exc:
                        output["plan"] = {
                            "available": False,
                            "estimated_cost": None,
                            "accessed_objects": [],
                            "error": f"SQL_EXECUTION_ERROR: {exc}",
                        }

                return output
            except ValueError as exc:
                decision = "deny"
                error_code = str(exc)
                state.denied_requests += 1
                raise
            except PermissionError as exc:
                decision = "deny"
                error_code = str(exc)
                state.denied_requests += 1
                raise
            except Exception as exc:
                decision = "deny"
                error_code = f"SQL_EXECUTION_ERROR: {exc}"
                state.denied_requests += 1
                raise RuntimeError(error_code) from exc
            finally:
                latency_ms = int((time.time() - started) * 1000)
                REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                state.audit_logger.log_event(
                    request_id=request_id,
                    actor=actor,
                    tool=_tool,
                    instance=_instance,
                    sql=sql_statement,
                    decision=decision,
                    latency_ms=latency_ms,
                    rows=rows,
                    error_code=error_code,
                )
                if ctx is not None:
                    await ctx.info(f"{_tool} completed with decision={decision} latency_ms={latency_ms}")

        registered.append(execute_query_name)

        analyze_tab_health_name = f"db_{instance_number}_sql2019_analyze_tab_health"
        if is_tool_enabled(state.policy, instance_id, "analyze_tab_health"):

            @mcp.tool(name=analyze_tab_health_name)
            async def _analyze_tab_health(
                database_name: str,
                schema_name: str | None = None,
                table_name: str | None = None,
                include_indexes: bool = True,
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
                try:
                    db_name = validate_database_name(database_name)
                    if schema_name is not None:
                        schema_name = validate_identifier(schema_name, "schema_name")
                    if table_name is not None:
                        table_name = validate_identifier(table_name, "table_name")
                    size = validate_positive_int(top_n, "top_n", 1, 500)

                    state.session_manager.touch(actor, request_id)
                    state.rate_limiter.allow(actor)
                    state.write_guard.enforce(_tool, "SELECT 1")

                    table_sizes = state.connection_manager.execute_catalog_query(_instance, db_name, table_size_query(size), size)
                    fragmented = {"rows": []}
                    if include_indexes:
                        fragmented = state.connection_manager.execute_catalog_query(
                            _instance,
                            db_name,
                            fragmented_indexes_query(size),
                            size,
                        )
                    missing_pk = state.connection_manager.execute_catalog_query(_instance, db_name, missing_pk_query(), size)

                    filtered_sizes = table_sizes["rows"]
                    if schema_name:
                        filtered_sizes = [r for r in filtered_sizes if str(r.get("schema_name")).lower() == schema_name.lower()]
                    if table_name:
                        filtered_sizes = [r for r in filtered_sizes if str(r.get("table_name")).lower() == table_name.lower()]

                    findings: list[dict[str, Any]] = []
                    recommendations: list[dict[str, Any]] = []
                    if include_indexes and fragmented["rows"]:
                        top_frag = fragmented["rows"][0]
                        findings.append(
                            build_finding(
                                code="TAB_HEALTH_FRAGMENTED_INDEXES",
                                severity="high",
                                title="High index fragmentation detected",
                                detail="One or more indexes exceed healthy fragmentation levels.",
                                evidence=fragmented["rows"][:10],
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority="high",
                                action="Rebuild/reorganize top fragmented indexes during maintenance windows.",
                                rationale=f"Highest observed fragmentation: {top_frag.get('avg_fragmentation_in_percent')}%",
                            )
                        )

                    if missing_pk["rows"]:
                        findings.append(
                            build_finding(
                                code="TAB_HEALTH_MISSING_PRIMARY_KEY",
                                severity="medium",
                                title="Tables without primary keys",
                                detail="Detected tables lacking primary key constraints.",
                                evidence=missing_pk["rows"][:10],
                            )
                        )
                        recommendations.append(
                            build_recommendation(
                                priority="medium",
                                action="Define primary keys for unconstrained tables.",
                                rationale="Primary keys improve integrity, optimizer quality, and replication behavior.",
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

                    rows = len(filtered_sizes) + len(fragmented["rows"]) + len(missing_pk["rows"])
                    return build_report_envelope(
                        instance_number=_instance_number,
                        database_name=db_name,
                        tool_name=_tool,
                        summary={
                            "table_count_scanned": len(filtered_sizes),
                            "fragmented_index_rows": len(fragmented["rows"]),
                            "missing_primary_key_tables": len(missing_pk["rows"]),
                            "table_size_preview": filtered_sizes[:10],
                        },
                        findings=findings,
                        recommendations=recommendations,
                    )
                except ValueError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    raise
                except PermissionError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    raise
                except Exception as exc:
                    decision = "deny"
                    error_code = f"SQL_EXECUTION_ERROR: {exc}"
                    state.denied_requests += 1
                    raise RuntimeError(error_code) from exc
                finally:
                    latency_ms = int((time.time() - started) * 1000)
                    REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                    REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                    state.audit_logger.log_event(
                        request_id=request_id,
                        actor=actor,
                        tool=_tool,
                        instance=_instance,
                        sql=sql_marker,
                        decision=decision,
                        latency_ms=latency_ms,
                        rows=rows,
                        error_code=error_code,
                    )
                    if ctx is not None:
                        await ctx.info(f"{_tool} completed with decision={decision} latency_ms={latency_ms}")

            registered.append(analyze_tab_health_name)

        analyze_db_data_model_name = f"db_{instance_number}_sql2019_analyze_db_data_model"
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
                try:
                    db_name = validate_database_name(database_name)
                    if schema_filter is not None:
                        schema_filter = validate_identifier(schema_filter, "schema_filter")
                    edge_limit = validate_positive_int(max_edges, "max_edges", 1, 5000)

                    state.session_manager.touch(actor, request_id)
                    state.rate_limiter.allow(actor)
                    state.write_guard.enforce(_tool, "SELECT 1")

                    graph_rows = state.connection_manager.execute_catalog_query(_instance, db_name, fk_graph_query(), edge_limit)
                    filtered_rows = graph_rows["rows"]
                    if schema_filter:
                        filtered_rows = [
                            row
                            for row in filtered_rows
                            if str(row.get("parent_schema", "")).lower() == schema_filter.lower()
                            or str(row.get("referenced_schema", "")).lower() == schema_filter.lower()
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
                                evidence=[{"table": t} for t in graph["circular_dependency_tables"]],
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

                    if not findings:
                        findings.append(
                            build_finding(
                                code="DATA_MODEL_NO_MAJOR_ISSUES",
                                severity="info",
                                title="No major data model issues detected",
                                detail="Current FK graph checks did not identify high-risk structural anomalies.",
                                evidence=[],
                            )
                        )

                    rows = len(filtered_rows)
                    return build_report_envelope(
                        instance_number=_instance_number,
                        database_name=db_name,
                        tool_name=_tool,
                        summary={
                            "fk_graph": {
                                "node_count": graph["node_count"],
                                "edge_count": graph["edge_count"],
                                "circular_dependency_count": len(graph["circular_dependency_tables"]),
                            },
                            "edge_preview": graph["edges"][:20],
                        },
                        findings=findings,
                        recommendations=recommendations,
                    )
                except ValueError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    raise
                except PermissionError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    raise
                except Exception as exc:
                    decision = "deny"
                    error_code = f"SQL_EXECUTION_ERROR: {exc}"
                    state.denied_requests += 1
                    raise RuntimeError(error_code) from exc
                finally:
                    latency_ms = int((time.time() - started) * 1000)
                    REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                    REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                    state.audit_logger.log_event(
                        request_id=request_id,
                        actor=actor,
                        tool=_tool,
                        instance=_instance,
                        sql=sql_marker,
                        decision=decision,
                        latency_ms=latency_ms,
                        rows=rows,
                        error_code=error_code,
                    )
                    if ctx is not None:
                        await ctx.info(f"{_tool} completed with decision={decision} latency_ms={latency_ms}")

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
                try:
                    db_name = validate_database_name(database_name)

                    state.session_manager.touch(actor, request_id)
                    state.rate_limiter.allow(actor)
                    state.write_guard.enforce(_tool, "SELECT 1")

                    orphan_users = state.connection_manager.execute_catalog_query(_instance, db_name, orphan_user_query(), 200)
                    elevated_roles = state.connection_manager.execute_catalog_query(_instance, db_name, elevated_roles_query(), 500)
                    backup_rows = state.connection_manager.execute_catalog_query(_instance, "master", backup_recency_query(), 200)

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
                            xp_cmdshell_enabled = bool(xp_rows["rows"] and int(xp_rows["rows"][0].get("value_in_use", 0)) == 1)
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
                                evidence=redact_sensitive_fields(orphan_users["rows"][:20]),
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
                                evidence=redact_sensitive_fields(elevated_roles["rows"][:30]),
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

                    rows = len(orphan_users["rows"]) + len(elevated_roles["rows"]) + len(backup_rows["rows"])
                    return build_report_envelope(
                        instance_number=_instance_number,
                        database_name=db_name,
                        tool_name=_tool,
                        summary={
                            "orphan_user_count": len(orphan_users["rows"]),
                            "elevated_role_memberships": len(elevated_roles["rows"]),
                            "backup_recency_rows": len(backup_rows["rows"]),
                            "xp_cmdshell_enabled": xp_cmdshell_enabled,
                            "xp_cmdshell_check_error": xp_cmdshell_error,
                        },
                        findings=findings,
                        recommendations=recommendations,
                    )
                except ValueError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    raise
                except PermissionError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    raise
                except Exception as exc:
                    decision = "deny"
                    error_code = f"SQL_EXECUTION_ERROR: {exc}"
                    state.denied_requests += 1
                    raise RuntimeError(error_code) from exc
                finally:
                    latency_ms = int((time.time() - started) * 1000)
                    REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                    REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                    state.audit_logger.log_event(
                        request_id=request_id,
                        actor=actor,
                        tool=_tool,
                        instance=_instance,
                        sql=sql_marker,
                        decision=decision,
                        latency_ms=latency_ms,
                        rows=rows,
                        error_code=error_code,
                    )
                    if ctx is not None:
                        await ctx.info(f"{_tool} completed with decision={decision} latency_ms={latency_ms}")

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
                """Generate session activity dashboard payload with lock chain details."""
                request_id = str(uuid.uuid4())
                started = time.time()
                decision = "allow"
                error_code = None
                rows = 0
                sql_marker = "SESSIONS_DASHBOARD"
                try:
                    db_name = validate_database_name(database_name)
                    validate_positive_int(lookback_minutes, "lookback_minutes", 1, 1440)

                    state.session_manager.touch(actor, request_id)
                    state.rate_limiter.allow(actor)
                    state.write_guard.enforce(_tool, "SELECT 1")

                    sessions = state.connection_manager.execute_catalog_query(_instance, db_name, active_sessions_query(200), 200)
                    lock_rows = {"rows": []}
                    if include_locks:
                        lock_rows = state.connection_manager.execute_catalog_query(_instance, db_name, lock_chain_query(200), 200)

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

                    rows = len(sessions["rows"]) + len(lock_rows["rows"])
                    payload = build_sessions_dashboard(
                        instance_number=_instance_number,
                        database_name=db_name,
                        sessions=sessions["rows"],
                        lock_chains=lock_rows["rows"],
                    )
                    payload["data"]["lookback_minutes"] = lookback_minutes
                    payload["data"]["head_blockers"] = head_blockers[:25]
                    payload["data"]["recommendations"] = [
                        {
                            "priority": "high" if head_blockers else "info",
                            "action": "Investigate head blockers and long wait chains." if head_blockers else "No immediate lock chain action required.",
                            "rationale": f"Detected {len(head_blockers)} unique blocking session(s).",
                        }
                    ]
                    return payload
                except ValueError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    raise
                except PermissionError as exc:
                    decision = "deny"
                    error_code = str(exc)
                    state.denied_requests += 1
                    raise
                except Exception as exc:
                    decision = "deny"
                    error_code = f"SQL_EXECUTION_ERROR: {exc}"
                    state.denied_requests += 1
                    raise RuntimeError(error_code) from exc
                finally:
                    latency_ms = int((time.time() - started) * 1000)
                    REQUEST_COUNT.labels(_tool, _instance, decision).inc()
                    REQUEST_LATENCY.labels(_tool, _instance).observe(latency_ms)
                    state.audit_logger.log_event(
                        request_id=request_id,
                        actor=actor,
                        tool=_tool,
                        instance=_instance,
                        sql=sql_marker,
                        decision=decision,
                        latency_ms=latency_ms,
                        rows=rows,
                        error_code=error_code,
                    )
                    if ctx is not None:
                        await ctx.info(f"{_tool} completed with decision={decision} latency_ms={latency_ms}")

            registered.append(sessions_dashboard_name)

    return registered
