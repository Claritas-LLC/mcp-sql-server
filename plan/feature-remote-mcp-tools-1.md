---
goal: Add New MCP Tools to Remote SQL Server MCP Deployments with Secure Dual-Instance Controls
version: 1.1
date_created: 2026-05-05
last_updated: 2026-05-06
owner: Cloud Solutions Architecture
status: Completed
tags: [feature, mcp, remote-server, sqlserver, security, operations]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This plan defines how to add new MCP tools to the remote FastMCP SQL Server service in a deterministic, security-first way. It is aligned to the current codebase structure, existing naming standard, dual-instance routing model, Redis-enabled rate limiting, and CI/CD signing pipeline.

## 1. Requirements & Constraints

- **REQ-001**: Add new MCP tools using naming convention `db_<instance>_sql2019_<toolname>`.
- **REQ-002**: Ensure each tool is instance-bound and cannot execute against an unintended SQL instance.
- **REQ-003**: Add tool contracts with explicit request/response schema and deterministic error codes.
- **REQ-004**: Enforce write guard, rate limit, session checks, and audit logging for all newly added tools.
- **REQ-005**: Expose new tools through the existing remote MCP endpoint mount path `/mcp`.
- **REQ-006**: Extend diagnostics and reporting to surface usage and denial behavior for newly added tools.
- **REQ-007**: Add tests for naming, policy enforcement, and tool behavior before remote rollout.
- **REQ-008**: Roll out in staged mode with canary enablement and rollback safety.
- **SEC-001**: New tools must respect deny-by-default write policy in `config/runtime-policy.yaml`.
- **SEC-002**: Any write-capable tool must be explicitly allowlisted in `allowed_write_tools`.
- **SEC-003**: New tools must emit immutable audit records with `tool`, `instance`, `decision`, `sql_hash`, and latency.
- **SEC-004**: New tools must be rate-limited through active backend (`local` or `redis`) with actor and global quota enforcement.
- **SEC-005**: No tool may expose credentials, raw secret refs, or full SQL text in unsecured logs.
- **CON-001**: Preserve compatibility with existing tool registration in `src/tools/sql_tools.py`.
- **CON-002**: Preserve existing instance generation model in `src/tools/tool_registry.py`.
- **CON-003**: Preserve existing server bootstrap and mount strategy in `src/server.py`.
- **CON-004**: Do not introduce breaking changes in existing tool names.
- **GUD-001**: Add tools in categories to minimize regression risk: read-only diagnostics first, controlled execute tools second.
- **PAT-001**: Follow existing closure-safe registration pattern (`_tool=tool_name`, `_instance=instance`) for each generated handler.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Define and approve the exact new remote MCP tool catalog and contracts.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Create tool catalog spec in `docs/mcp-tool-catalog.md` with each tool name, purpose, input schema, output schema, SQL privilege profile, and failure codes. |  |  |
| TASK-002 | Classify each proposed tool as `read_only`, `controlled_write`, or `diagnostic`. |  |  |
| TASK-003 | For each `controlled_write` tool, define approval owner and add explicit allowlist mapping requirements. |  |  |
| TASK-004 | Define actor identity expectations for each tool call path (human DBA, automation job, system actor). |  |  |

### Implementation Phase 2

- GOAL-002: Extend tool registry generation and deterministic naming for newly added tool types.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-005 | Update `generate_tool_specs()` in `src/tools/tool_registry.py` to include each approved new tool type for every enabled instance. |  |  |
| TASK-006 | Add unit test coverage in `tests/test_tool_naming.py` for each new generated tool name on both `primary` and `secondary`. |  |  |
| TASK-007 | Validate no existing tool names are modified or removed. |  |  |

### Implementation Phase 3

- GOAL-003: Implement tool handlers with mandatory middleware enforcement and auditable behavior.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-008 | Add new handler branches in `src/tools/sql_tools.py` with explicit enforcement order: session -> rate limit -> write guard -> DB execution -> audit log. |  |  |
| TASK-009 | Ensure each handler logs deterministic decision state (`allow` or `deny`) and maps exceptions to stable error codes. |  |  |
| TASK-010 | Route all SQL actions through `ConnectionManager` methods in `src/db/connection_manager.py` and add new manager methods if needed. |  |  |
| TASK-011 | Add safe row/result bounds honoring `max_result_rows` and `max_query_duration_ms` for each new read tool. |  |  |

### Implementation Phase 4

- GOAL-004: Update policy, configuration, and diagnostics for production-safe remote operation.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-012 | Update `config/runtime-policy.yaml` to include only approved write-capable tools in `allowed_write_tools`. |  |  |
| TASK-013 | Update `policy/sql-allowlist.yaml` and `policy/sql-denylist.yaml` with specific procedure/query controls for new tools. |  |  |
| TASK-014 | Extend `src/diagnostics/routes.py` with new counters or summary fields for added tool categories and denial statistics. |  |  |
| TASK-015 | Update `scripts/report-latency.ps1` and `scripts/report-latency.sh` parsing logic if additional metrics labels are introduced. |  |  |

### Implementation Phase 5

- GOAL-005: Validate, canary deploy, and promote new MCP tools to all remote server environments.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-016 | Add and run tests in `tests/test_write_restrictions.py`, `tests/test_rate_limiting.py`, and new tool-specific test files. |  |  |
| TASK-017 | Deploy canary image to one remote environment with subset tool enablement via policy/config toggles. |  |  |
| TASK-018 | Collect evidence using `scripts/collect-evidence.ps1` and `scripts/collect-evidence.sh` and verify audit completeness. |  |  |
| TASK-019 | Promote to full production after canary acceptance gates pass; rollback on gate failure using previous signed digest. |  |  |

## 3. Alternatives

- **ALT-001**: Add tools as generic SQL passthrough endpoints. Not chosen because it weakens policy enforcement, safety guarantees, and auditability.
- **ALT-002**: Deploy separate MCP server per tool family. Not chosen because operational overhead and duplicate policy surfaces increase complexity.
- **ALT-003**: Add tools without dual-instance naming. Not chosen because it breaks existing operational conventions and increases routing ambiguity.

## 4. Dependencies

- **DEP-001**: Existing FastMCP/FastAPI runtime in `src/server.py`.
- **DEP-002**: Existing `ConnectionManager` methods and SQL credentials secret resolution.
- **DEP-003**: Existing write guard, session manager, and rate limiter implementations.
- **DEP-004**: Redis backend availability for horizontally scaled deployments when `FASTMCP_RATE_LIMIT_BACKEND=redis`.
- **DEP-005**: CI workflow `.github/workflows/ci.yml` for lint, tests, container build, publish, and signing.

## 5. Files

- **FILE-001**: `src/tools/tool_registry.py` - Add new generated tool specs.
- **FILE-002**: `src/tools/sql_tools.py` - Add concrete tool handlers and enforcement wiring.
- **FILE-003**: `src/db/connection_manager.py` - Add DB methods required by new tools.
- **FILE-004**: `config/runtime-policy.yaml` - Update write allowlist and runtime safety limits.
- **FILE-005**: `policy/sql-allowlist.yaml` - Add approved proc/query mappings.
- **FILE-006**: `policy/sql-denylist.yaml` - Expand blocked patterns if required.
- **FILE-007**: `src/diagnostics/routes.py` - Add diagnostics and metrics visibility for new tools.
- **FILE-008**: `tests/test_tool_naming.py` - Verify generated naming for new tools.
- **FILE-009**: `tests/test_write_restrictions.py` - Verify write guard behavior for new handlers.
- **FILE-010**: `tests/test_rate_limiting.py` - Verify limiter behavior remains consistent with increased tool volume.
- **FILE-011**: `docs/mcp-tool-catalog.md` - Tool contract and ownership specification.

## 6. Testing

- **TEST-001**: Unit test all newly generated names for both instances.
- **TEST-002**: Unit test each new read tool for result schema and row bound enforcement.
- **TEST-003**: Unit test each controlled-write tool for deny-by-default behavior when not allowlisted.
- **TEST-004**: Unit test allowlisted write path and audit event generation.
- **TEST-005**: Integration test diagnostics endpoints include new tool metrics and denial counts.
- **TEST-006**: Integration test rate-limit behavior under concurrent tool calls in local and Redis backend modes.
- **TEST-007**: Canary test in remote environment with evidence bundle generation and checksum validation.

## 7. Risks & Assumptions

- **RISK-001**: New tools may increase SQL load and latency on remote instances.
- **RISK-002**: Misconfigured allowlist may cause unintended write denials during operational events.
- **RISK-003**: Redis unavailability may impact shared quota enforcement in horizontal deployments.
- **RISK-004**: Additional tool branches can introduce closure-binding bugs if defaults are not captured correctly.
- **ASSUMPTION-001**: Remote SQL instances expose required views/procedures for proposed tools.
- **ASSUMPTION-002**: CI signing and GHCR publish permissions remain valid for release branches/tags.
- **ASSUMPTION-003**: Existing DBA workflows can absorb new tool outputs without schema translation.

## 8. Related Specifications / Further Reading

- `plan/remote-sql2019-fastmcp3-deployment-plan.md`
- `src/server.py`
- `src/tools/sql_tools.py`
- `src/tools/tool_registry.py`
- `.github/workflows/ci.yml`

## 9. Completion Notes

- Completed implementation of numbered instance tools:
	- `db_1_sql2019_ping`, `db_2_sql2019_ping`
	- `db_1_sql2019_list_tools`, `db_2_sql2019_list_tools`
	- `db_1_sql2019_list_object`, `db_2_sql2019_list_object`
	- `db_1_sql2019_execute_query`, `db_2_sql2019_execute_query`
- Provisioned dual SQL Server 2019 Docker testbed with seeded dummy databases:
	- `USGISPRO_800` on instance 1
	- `CITYGIS_810` on instance 2
- Captured unit and integration artifacts:
	- `testing/artifacts/unit/unit-pytest.txt`
	- `testing/artifacts/unit/unit-instance1.json`
	- `testing/artifacts/unit/unit-instance2.json`
	- `testing/artifacts/integration/integration-summary.json`
	- `testing/artifacts/integration/integration-phase-status.txt`
