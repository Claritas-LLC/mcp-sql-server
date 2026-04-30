---
goal: Validate all MCP tools via blackbox and end-to-end testing against two temporary SQL Server containers, capture real data outputs, and remediate all discovered issues
version: 1.0
date_created: 2026-04-14
last_updated: 2026-04-14
owner: Platform Engineering
status: Planned
tags: [process, testing, blackbox, e2e, docker, sql-server, remediation]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This plan defines an executable workflow to provision two temporary SQL Server 2019 Docker containers, run full blackbox and end-to-end validation across all exposed MCP tools for both instances, capture real response payloads from test databases, fix discovered issues, and produce a final pass report.

## 1. Requirements & Constraints

- **REQ-001**: Execute all registered MCP tools for `db_01_*` and `db_02_*` prefixes from `mcp_sqlserver/server.py` function `_register_dual_instance_tools()`.
- **REQ-002**: Run both blackbox protocol tests and end-to-end tool execution tests.
- **REQ-003**: Provision two isolated temporary SQL Server containers and seed both with sample data.
- **REQ-004**: Persist raw tool responses containing actual data values returned from the test databases.
- **REQ-005**: Produce deterministic machine-readable artifacts under `testing/` and `testing/tool_results/`.
- **REQ-006**: Resolve all encountered defects and re-run the full suite until pass criteria are met.
- **SEC-001**: Do not log secrets in test artifacts; redact passwords and connection strings before persisting reports.
- **SEC-002**: Keep write-mode testing gated behind explicit environment flags (`MCP_ALLOW_WRITE=true` and `MCP_CONFIRM_WRITE=true`) and run only in disposable test containers.
- **OPS-001**: Use Docker image `mcr.microsoft.com/mssql/server:2019-latest` for both temporary SQL instances.
- **OPS-002**: Use non-conflicting host ports for two SQL instances and one MCP server instance.
- **CON-001**: Tests must be executable on Windows PowerShell (`pwsh`) in the current repository root.
- **CON-002**: Existing repository files must not be force-reset or destructively overwritten during remediation.
- **GUD-001**: Reuse existing test assets where possible: `tests/test_blackbox_http.py`, `tests/test_integration_tools.py`, `testing/README.md`, and `setup_test_database.sql`.
- **PAT-001**: Use a red-green-refactor loop per defect: reproduce -> patch -> targeted test -> full regression.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Build deterministic dual-SQL test harness inputs and environment bootstrap.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Create `testing/dual_sql_env.ps1` to set deterministic variables: `DB_01_SERVER=127.0.0.1`, `DB_01_PORT=14331`, `DB_02_SERVER=127.0.0.1`, `DB_02_PORT=14332`, `MCP_TRANSPORT=http`, `MCP_PORT=8085`, and non-secret defaults for test mode. |  |  |
| TASK-002 | Create `testing/provision_dual_sql.ps1` to run two disposable containers: names `mcp_sqlserver_test_01` and `mcp_sqlserver_test_02`, both with `ACCEPT_EULA=Y`, deterministic SA password, and mapped ports `14331:1433` and `14332:1433`. |  |  |
| TASK-003 | Create `testing/seed_dual_sql.ps1` to execute `setup_test_database.sql` in both containers via `sqlcmd` and verify expected seed tables exist in each instance. |  |  |
| TASK-004 | Create `testing/teardown_dual_sql.ps1` to stop/remove both SQL containers and clean temp logs after suite completion. |  |  |

### Implementation Phase 2

- GOAL-002: Generate authoritative tool inventory and execution matrix for all tools on both instances.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | Add `testing/generate_tool_matrix.py` that parses `_register_dual_instance_tools()` in `mcp_sqlserver/server.py` and emits `testing/tool_matrix.json` containing all tool names for `db_01_*` and `db_02_*`. |  |  |
| TASK-006 | Validate matrix count equals `2 * len(tool_map)` from `mcp_sqlserver/server.py`; fail generation if mismatch. |  |  |
| TASK-007 | Add execution metadata in `testing/tool_matrix.json`: required args, read/write classification, and seed-data prerequisites per tool. |  |  |

### Implementation Phase 3

- GOAL-003: Execute blackbox protocol validation against running MCP HTTP service.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Start MCP server using `python server_startup.py` with dual-instance env and capture server logs to `testing/blackbox_server.log`. |  |  |
| TASK-009 | Run `pytest tests/test_blackbox_http.py -v` and persist output to `testing/blackbox_results.txt`. |  |  |
| TASK-010 | Add `testing/blackbox_summary.json` containing pass/fail counts, failed test IDs, first failure traces, and MCP endpoint response status checks. |  |  |

### Implementation Phase 4

- GOAL-004: Execute end-to-end tool validation with real database values for both SQL instances.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-011 | Create `testing/run_all_tools_dual_http.py` that iterates `testing/tool_matrix.json` and calls each tool through MCP JSON-RPC over HTTP for both instances. |  |  |
| TASK-012 | For each tool invocation, persist raw response JSON to `testing/tool_results/<tool_name>.json` including returned rows/items and pagination metadata when present. |  |  |
| TASK-013 | Persist command/result index to `testing/tool_execution_summary.json` with fields: `tool_name`, `instance`, `status`, `http_status`, `duration_ms`, `result_file`, `error`. |  |  |
| TASK-014 | Execute `pytest tests/test_integration_tools.py -v` and `pytest tests/test_stress_tools.py -v` under dual-instance config; store logs in `testing/integration_results.txt` and `testing/stress_results.txt`. |  |  |

### Implementation Phase 5

- GOAL-005: Fix all discovered issues and converge to full green regression.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-015 | Create `testing/defect_register.json` listing each failure with `id`, `tool`, `test_case`, `symptom`, `root_cause_file`, and `root_cause_function`. |  |  |
| TASK-016 | For each defect, patch source in `mcp_sqlserver/server.py` and/or tests under `tests/` with minimal-change commits in working tree; avoid unrelated refactors. |  |  |
| TASK-017 | After each patch, run targeted test(s) first, then rerun full blackbox + E2E suite; update `testing/defect_register.json` status to `resolved` only after full regression pass. |  |  |
| TASK-018 | Repeat remediation loop until `testing/defect_register.json` has zero `open` entries and all required suites pass. |  |  |

### Implementation Phase 6

- GOAL-006: Publish auditable final report with actual retrieved data samples.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-019 | Generate `testing/TEST_REPORT.md` with final pass/fail totals, executed tool count, timing summary, and links to every raw result JSON file. |  |  |
| TASK-020 | Include representative actual data excerpts from both instance result files (minimum 3 tools per instance, including one query tool and one analysis tool). |  |  |
| TASK-021 | Add reproducibility block to `testing/TEST_REPORT.md` listing exact commands and environment variables used. |  |  |
| TASK-022 | Run `testing/teardown_dual_sql.ps1` and verify both temporary SQL containers are removed. |  |  |

## 3. Alternatives

- **ALT-001**: Use a single SQL container with two databases instead of two containers. Rejected because it does not validate independent host/port instance wiring for `DB_01_*` and `DB_02_*`.
- **ALT-002**: Mock all tools instead of real E2E execution. Rejected because the requirement mandates actual data retrieval from provisioned test databases.
- **ALT-003**: Execute only `pytest` suites without tool-matrix coverage. Rejected because not all dynamically registered tools are guaranteed to be exercised.

## 4. Dependencies

- **DEP-001**: Docker Desktop or Docker Engine with permission to run Linux containers.
- **DEP-002**: SQL Server image `mcr.microsoft.com/mssql/server:2019-latest`.
- **DEP-003**: Python environment with repository dependencies from `requirements.txt` and test dependencies from `testing/requirements-test.txt`.
- **DEP-004**: ODBC driver availability compatible with `pyodbc` for local MCP execution.
- **DEP-005**: Existing SQL seed script `setup_test_database.sql`.

## 5. Files

- **FILE-001**: `mcp_sqlserver/server.py` - defect remediation target for MCP tool behavior issues.
- **FILE-002**: `tests/test_blackbox_http.py` - blackbox validation suite.
- **FILE-003**: `tests/test_integration_tools.py` - integration E2E validation suite.
- **FILE-004**: `tests/test_stress_tools.py` - stress/regression validation suite.
- **FILE-005**: `setup_test_database.sql` - sample data seed script for both SQL containers.
- **FILE-006**: `testing/provision_dual_sql.ps1` - new dual-container provisioning script.
- **FILE-007**: `testing/seed_dual_sql.ps1` - new dual-instance seed execution script.
- **FILE-008**: `testing/teardown_dual_sql.ps1` - new cleanup script.
- **FILE-009**: `testing/generate_tool_matrix.py` - new authoritative tool inventory generator.
- **FILE-010**: `testing/run_all_tools_dual_http.py` - new full tool execution orchestrator.
- **FILE-011**: `testing/tool_matrix.json` - generated tool inventory and argument metadata.
- **FILE-012**: `testing/tool_execution_summary.json` - generated per-tool run summary.
- **FILE-013**: `testing/defect_register.json` - generated defect lifecycle tracker.
- **FILE-014**: `testing/TEST_REPORT.md` - final consolidated report with actual data excerpts.
- **FILE-015**: `testing/tool_results/` - raw result payloads for each tool invocation.

## 6. Testing

- **TEST-001**: Provisioning validation: both SQL containers reachable and seeded table checks succeed.
- **TEST-002**: Blackbox protocol validation: `pytest tests/test_blackbox_http.py -v` returns full pass.
- **TEST-003**: Full tool coverage validation: every tool in `testing/tool_matrix.json` has an execution record and output file.
- **TEST-004**: E2E integration validation: `pytest tests/test_integration_tools.py -v` returns full pass.
- **TEST-005**: Stress validation: `pytest tests/test_stress_tools.py -v` returns full pass.
- **TEST-006**: Write-tool gating validation: write tools fail safely when write mode disabled and execute only in explicit write-enabled test run.
- **TEST-007**: Final regression gate: all required suites pass after final remediation loop with zero open defects.

## 7. Risks & Assumptions

- **RISK-001**: SQL container startup delays can cause false negatives. Mitigation: add readiness polling before seed/test phases.
- **RISK-002**: Some tools may require feature prerequisites (e.g., Query Store). Mitigation: ensure seed/setup script enables required database options.
- **RISK-003**: Write/admin tools can mutate test state and break deterministic assertions. Mitigation: run write tests last or reseed before each write-case batch.
- **RISK-004**: Large payload tools can produce oversized artifacts. Mitigation: compress archived artifacts and cap non-essential fields only in summary files, not raw payload captures.
- **ASSUMPTION-001**: Host has sufficient resources to run two SQL Server containers concurrently.
- **ASSUMPTION-002**: Current MCP server HTTP transport is operational via `server_startup.py` in local environment.
- **ASSUMPTION-003**: Existing test harness can authenticate to local SQL instances with disposable SA credentials.

## 8. Related Specifications / Further Reading

[README.md](README.md)
[testing/README.md](testing/README.md)
[tests/test_blackbox_http.py](tests/test_blackbox_http.py)
[tests/test_integration_tools.py](tests/test_integration_tools.py)
[tests/test_stress_tools.py](tests/test_stress_tools.py)
[setup_test_database.sql](setup_test_database.sql)