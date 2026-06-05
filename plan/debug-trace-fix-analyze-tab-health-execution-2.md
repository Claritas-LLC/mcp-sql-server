---
goal: Debug, trace, and fix errors when executing db_2_sql2019_analyze_tab_health(database_name=US_RT_User_800, top_n=5) and displaying results
version: 1.0
date_created: 2026-06-03
last_updated: 2026-06-04
owner: Cloud Solutions Architecture
status: Completed
tags: [debug, trace, sqlserver, analyze-tab-health, execution, mcp, redis]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan covers the execution of `db_2_sql2019_analyze_tab_health(database_name=US_RT_User_800, top_n=5)` with the previously implemented transient retry fix (see [debug-trace-fix-08s01-transient-transport-error-1.md](debug-trace-fix-08s01-transient-transport-error-1.md)). The plan includes: starting the MCP server, invoking the tool, capturing the report envelope, displaying structured findings, and verifying that no new errors surfaced from the tool call.

A previous transient **08S01 TCP transport error** was already fixed via automatic retry in `ConnectionManager._run_read_operation`. However, during execution two additional errors were discovered:

1. **Redis rate-limiter error** — Environment variables `FASTMCP_RATE_LIMIT_BACKEND=redis` and `FASTMCP_REDIS_URL=redis://mcp-sqlserver-redis:6379` are set in the user/machine environment (from Docker deployment config). When running locally without Docker, the server attempts to connect to a Redis host that only exists in Docker, causing `SQL_ERROR_HY000: Error 11001 connecting to mcp-sqlserver-redis:6379`.
2. **Long SQL execution time** — With `command_timeout_sec: 30` and 7+ catalog queries (each with retry), the tool can take 2-7 minutes to complete against remote SQL instances.

## 1. Requirements & Constraints

- **REQ-001**: Start the MCP server successfully using `python src/server.py` (or equivalent entry point).
- **REQ-002**: Invoke `db_2_sql2019_analyze_tab_health(database_name="US_RT_User_800", top_n=5)` via the MCP protocol.
- **REQ-003**: Capture the full tool response—a `build_report_envelope` containing `instance_number`, `database_name`, `tool_name`, `summary`, `findings`, and `recommendations`.
- **REQ-004**: Handle any remaining errors (non-transient) with clear logging and re-raise with the correct error contract.
- **REQ-005**: Display the results in a human-readable format showing severity counts, each finding with evidence, and each recommendation with remediation T-SQL.
- **CON-001**: All database interaction is read-only—no writes should be attempted.
- **CON-002**: The tool must respect rate limiting, session management, and SQL denylist enforcement.
- **CON-003**: Instance `db_2` = the *secondary* instance (10.125.1.8:1433) by the `enumerate(instance_ids, start=1)` ordering in `register_sql_tools`.
- **CON-004**: `top_n=5` limits each internal catalog query to 5 rows, so the report is bounded and fast.
- **CON-005**: When running locally (outside Docker), the environment variables `FASTMCP_RATE_LIMIT_BACKEND` and `FASTMCP_REDIS_URL` may be set to Docker-only values. Override with `$env:FASTMCP_RATE_LIMIT_BACKEND = "local"` before starting the server.
- **CON-006**: The MCP server uses SSE (text/event-stream) transport. curl must send `Accept: application/json, text/event-stream` and a valid `mcp-session-id` header.

## 2. Implementation Steps

### Implementation Phase 1 — Start MCP Server and Verify Readiness

- GOAL-001: Start the MCP SQL Server, verify all diagnostic endpoints respond, and confirm that the secondary instance (db_2) is reachable.

| Task     | Description           | Completed | Date       |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Activate the Python virtual environment and verify pip dependencies are installed (`pip list \| findstr fastmcp`). | ✅ | 2026-06-03 |
| TASK-002 | **Override Docker env vars**: `$env:FASTMCP_RATE_LIMIT_BACKEND = "local"; $env:FASTMCP_REDIS_URL = ""` before starting the server. Without this, the rate limiter tries to connect to a non-existent Redis host. | ✅ | 2026-06-03 |
| TASK-003 | Start the server: `$env:PYTHONPATH = "c:\Users\HarryValdez\OneDrive\Documents\trae\mcp-sql-server"; python src/server.py`. | ✅ | 2026-06-04 |
| TASK-004 | Verify the root endpoint lists `db_2_sql2019_analyze_tab_health`. | ✅ | 2026-06-03 |
| TASK-005 | Verify health diagnostics shows both instances healthy. | ✅ | 2026-06-03 |

**Validation criteria**: All endpoints return HTTP 200 and the tool appears in the tool list.

### Implementation Phase 2 — Execute Tool Call and Capture Response

- GOAL-002: Call `db_2_sql2019_analyze_tab_health(database_name="US_RT_User_800", top_n=5)` via the MCP endpoint and capture the full report envelope.

| Task     | Description           | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-006 | Initialize an MCP session via `POST /mcp/` with `Accept: application/json, text/event-stream`. Extract `mcp-session-id` from response headers. | ✅ | 2026-06-03 |
| TASK-007 | Call the tool: `POST /mcp/` with header `mcp-session-id: {session_id}` and body `{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"db_2_sql2019_analyze_tab_health","arguments":{"database_name":"US_RT_User_800","top_n":5}}}`. | 🔲 | |
| TASK-008 | **Wait for SQL completion** — the tool runs 7+ catalog queries with `command_timeout_sec: 30`. Each query may retry once. Total expected time: 1-7 minutes depending on SQL Server responsiveness and network latency. | 🔲 | |
| TASK-009 | Parse the SSE response for `event: message` with `data: {"jsonrpc":"2.0","id":3,"result":{...}}` containing the `build_report_envelope`. | 🔲 | |
| TASK-010 | **Error handling**: If the call fails with a Redis connection error (`HY000: Error 11001 connecting to mcp-sqlserver-redis`), ensure `FASTMCP_RATE_LIMIT_BACKEND=local` is set before starting the server (TASK-002). | ✅ | 2026-06-03 |
| TASK-011 | **Error handling**: If the call fails with an 08S01 transient error, the retry-mechanism in `ConnectionManager._run_read_operation` (from prior fix) should handle it transparently. | N/A | |
| TASK-012 | **Error handling**: If the call fails with a non-transient error (invalid database name, permission error), capture the full error payload, diagnose, and retry with corrected parameters. | 🔲 | |

**Validation criteria**: The tool returns a valid JSON-RPC response with the report envelope, OR a structured error is captured and diagnosed.

### Implementation Phase 3 — Display Results with Remediation

- GOAL-003: Display the captured findings in a structured format with severity badges, evidence tables, and corresponding T-SQL remediation commands.

| Task     | Description           | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-013 | Extract the `summary` section and display as a markdown table. | 🔲 | |
| TASK-014 | Extract the `findings` array and display each finding with severity, code, title, detail, and evidence preview. | 🔲 | |
| TASK-015 | Extract the `recommendations` array and map each to a concrete T-SQL remediation command. | 🔲 | |
| TASK-016 | Log the execution summary. | 🔲 | |

**Validation criteria**: All findings and recommendations displayed in readable markdown with T-SQL commands.

### Implementation Phase 4 — Verify Diagnostics and Audit Trail

- GOAL-004: Confirm that the tool call was properly audited and the security/diagnostics endpoints reflect the execution.

| Task     | Description           | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-017 | Check server stdout logs for audit entry. | 🔲 | |
| TASK-018 | Run regression tests: `pytest -q tests/test_connection_pooling.py`. | 🔲 | |

**Validation criteria**: Audit event logged and all tests pass.

## 3. Alternatives

- **ALT-001** — Use a dedicated MCP client instead of raw HTTP POST to `/mcp`. Rejected because: raw curl is simpler for debugging.
- **ALT-002** — Run Redis locally to match the Docker environment. Valid alternative but adds complexity.
- **ALT-003** — Set `FASTMCP_RATE_LIMIT_BACKEND=local` as a permanent system env var. Rejected because: the project expects Redis for production deployments; local override is only for development.

## 4. Dependencies

- **DEP-001**: The MCP server must be running on `localhost:8080`.
- **DEP-002**: The secondary SQL instance (10.125.1.8:1433) must be reachable and `US_RT_User_800` must exist.
- **DEP-003**: `FASTMCP_RATE_LIMIT_BACKEND` must be set to `local` (or Redis must be running on `mcp-sqlserver-redis:6379`).
- **DEP-004**: The transient retry fix from [debug-trace-fix-08s01-transient-transport-error-1.md] is merged.

## 5. Files

| File | Role |
|---|---|
| **FILE-001** | `src/server.py` — Reads `FASTMCP_RATE_LIMIT_BACKEND` and `FASTMCP_REDIS_URL` env vars. Must use "local" backend when Redis is unavailable. |
| **FILE-002** | `src/tools/sql_tools.py` — Contains `_analyze_tab_health` closure. No changes needed. |
| **FILE-003** | `src/db/connection_manager.py` — Contains the transient retry fix. No changes needed. |
| **FILE-004** | `src/middleware/rate_limiter.py` — `build_rate_limiter()` creates `RedisSlidingWindowRateLimiter` when backend="redis". |
| **FILE-005** | `docs/demo-narration-script.md` — Reference for expected tool behavior. |

## 6. Testing

| Test | Description | Status |
|---|---|---|
| **TEST-001** | Server starts and all diagnostic endpoints return HTTP 200. | ✅ Passed |
| **TEST-002** | `db_2_sql2019_analyze_tab_health` listed in tool inventory. | ✅ Passed |
| **TEST-003** | Tool call with `FASTMCP_RATE_LIMIT_BACKEND=local` bypasses Redis and reaches SQL Server. | ✅ Passed |
| **TEST-004** | Tool call returns a valid report envelope with findings. | 🔲 |
| **TEST-005** | `pytest -q tests/test_connection_pooling.py` — all tests pass. | 🔲 |

## 7. Risks & Assumptions

- **RISK-001** — The `US_RT_User_800` database may not exist on the secondary instance. Mitigation: if the tool returns an error about an invalid database name, use `db_2_sql2019_list_object` or `db_2_sql2019_execute_query` to verify the database exists first.
- **RISK-002** — The secondary instance may be unreachable. Mitigation: `/diagnostics/health` will show `"accessible": false`. Fall back to `db_1` (primary).
- **RISK-003** — Redis env vars are set at user/machine level from Docker setup. Mitigation: always set `FASTMCP_RATE_LIMIT_BACKEND=local` before starting the server locally.
- **RISK-004** — Tool execution time may exceed the curl `--max-time` limit (e.g., 120 seconds) if SQL queries are slow. Mitigation: increase timeout or set lower `command_timeout_sec` in `instances.yaml`.
- **ASSUMPTION-001** — The MCP server runs on port 8080 (default), not 8000.
- **ASSUMPTION-002** — The SSE transport requires `Accept: application/json, text/event-stream` and a valid session ID for all tool calls.

## 8. Related Specifications / Further Reading

- [debug-trace-fix-08s01-transient-transport-error-1.md](debug-trace-fix-08s01-transient-transport-error-1.md) — Prior plan for transient 08S01 fix.
- [feature-analyze-tab-health-statistics-1.md](feature-analyze-tab-health-statistics-1.md) — Original implementation plan.
- [run-mcp-server-with-docker.md](../docs/run-mcp-server-with-docker.md) — Documents the Redis dependency for Docker deployments.
- [production-configuration-matrix.md](../docs/production-configuration-matrix.md) — Production config reference.
