# Access Levels and Controlled-Write Model

This document describes the MCP server access model and how controlled-write is enforced.

## Access Levels

### 1. Read-only execution

- Standard query/report tools execute through the read path.
- Requests are still evaluated by policy guardrails before execution.

Implementation references:
- `src/tools/sql_tools.py`
- `src/middleware/write_guard.py`

### 2. Read-only analysis

- Analysis tools (for example, table health/data-model/security analysis) return deterministic report payloads.
- These tools are non-mutating from a SQL data-change perspective.

Reference:
- `docs/mcp-tool-catalog.md`

### 3. Interactive dashboard

- Dashboard tools return HTML/data payloads for diagnostics and visualization.
- These tools do not introduce SQL data mutation behavior.

Reference:
- `docs/mcp-tool-catalog.md`

### 4. Controlled-write

- Controlled-write is explicit and deny-by-default.
- Only allowlisted stored-procedure execution tools may perform write actions.

Primary policy reference:
- `config/runtime-policy.yaml`

Procedure allowlist reference:
- `policy/sql-allowlist.yaml`

## How Controlled-Write Is Enforced

Controlled-write is enforced in layers:

### Layer 1: Tool-level write gate

- `write_mode_default: deny` is the baseline policy.
- Any write-like SQL verb is blocked unless the calling tool is listed in `allowed_write_tools`.
- Blocked SQL regex patterns (denylist) are enforced before execution.

Code path:
- `WriteGuard.enforce(...)` in `src/middleware/write_guard.py`

### Layer 2: Instance-level enablement

- Even if a tool is in `allowed_write_tools`, it must also be enabled per instance in `instance_tool_enable_flags`.

Policy path:
- `config/runtime-policy.yaml`

### Layer 3: Procedure-level allowlist

- For `exec_proc` tools, the requested procedure must be allowlisted for that exact tool.
- Names are normalized for comparison (schema-qualified names supported).

Code path:
- `WriteGuard.validate_procedure(...)` in `src/middleware/write_guard.py`

Policy paths:
- `config/runtime-policy.yaml` (allowed_tools section)
- `policy/sql-allowlist.yaml`

### Layer 4: Runtime controls and observability

Each request is wrapped with:

- Session tracking
- Rate limiting
- Decision logging (`allow`/`deny`)
- Audit event persistence
- Request count/latency metrics

Code path:
- `src/tools/sql_tools.py`

## Current Controlled-Write Configuration

As currently configured:

- Controlled-write tools enabled:
  - `db_primary_sql2019_exec_proc`
  - `db_secondary_sql2019_exec_proc`
- Both primary and secondary have `exec_proc: true` in instance tool flags.
- Both tools map to allowlisted procedures:
  - `dbo.usp_RunApprovedMaintenance`
  - `dbo.usp_RefreshMaterializedView`

## Security Posture Summary

- Default is deny for write operations.
- Access is granted only when all gates pass:
  1. Tool is allowlisted for write
  2. Instance/tool flag is enabled
  3. Procedure is allowlisted for that tool
  4. SQL denylist patterns are not matched

Failure at any gate returns a policy denial.
