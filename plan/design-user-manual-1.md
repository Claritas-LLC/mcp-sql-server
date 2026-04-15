---
goal: Create a comprehensive user manual for mcp-sql-server
version: 1.0
date_created: 2026-04-15
last_updated: 2026-04-15
owner: Repository Maintainers
status: Completed
tags: [design, documentation, mcp, user-manual]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan defines deterministic steps to produce a complete user manual that documents available MCP tools, how to run and use the server, how to issue tool calls from MCP clients, and the exact operational scope and limitations of this server.

## 1. Requirements & Constraints

- **REQ-001**: Create a single canonical manual file at `docs/users-manual.md`.
- **REQ-002**: Document all canonical tool families exposed by dual-instance registration in `mcp_sqlserver/server.py`.
- **REQ-003**: Include practical run instructions for local Python and Docker execution.
- **REQ-004**: Include explicit instructions for issuing tools through MCP clients (name format, arguments, examples).
- **REQ-005**: Document scope boundaries and limitations (read/write controls, auth, rate limits, environment prerequisites, Generative UI dependency).
- **DOC-001**: Add a “User Manual” link in `README.md`.
- **SEC-001**: The manual must explicitly state that secrets are never to be committed and `.env` must remain local.
- **SEC-002**: The manual must explicitly describe write-mode safety controls (`MCP_ALLOW_WRITE`, `MCP_CONFIRM_WRITE`, auth requirement over HTTP).
- **OPS-001**: Tool inventory source of truth must be `tool_map` in `_register_dual_instance_tools` and `_register_generative_dashboard_tools` in `mcp_sqlserver/server.py`.
- **CON-001**: Do not alter server runtime behavior; documentation-only changes for this work item.
- **CON-002**: Avoid documenting aliases as primary usage; aliases can be listed in an appendix as compatibility-only names.
- **GUD-001**: Use canonical tool names (`db_01_*`, `db_02_*`) in all main examples.
- **PAT-001**: Structure examples as copy/paste-ready blocks with deterministic input and expected output fields.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Build a complete, verifiable inventory of tools, endpoints, and controls from code.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Read `mcp_sqlserver/server.py` and extract all keys from `tool_map` in `_register_dual_instance_tools` into `docs/users-manual.md` Section “Tool Catalog”. | ✅ | 2026-04-15 |
| TASK-002 | Read `mcp_sqlserver/server.py` and extract all keys from `tool_map` in `_register_generative_dashboard_tools` into `docs/users-manual.md` Section “Generative Dashboard Tools”. | ✅ | 2026-04-15 |
| TASK-003 | Capture web routes from `@mcp.custom_route` definitions (`/sessions-monitor`, `/data-model-analysis`) and add route usage details to the manual. | ✅ | 2026-04-15 |
| TASK-004 | Capture runtime controls from `_load_settings()` (transport, write, rate-limit, audit, tool execution logging) and map to “Configuration Reference” section. | ✅ | 2026-04-15 |

### Implementation Phase 2

- GOAL-002: Author the user manual core content with usage-first structure.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-005 | Create `docs/users-manual.md` with sections: Overview, Architecture, Prerequisites, Setup, Running Modes, MCP Tool Invocation, Tool Catalog, Scope & Limitations, Troubleshooting, FAQ. | ✅ | 2026-04-15 |
| TASK-006 | Add “How to issue tools” with canonical naming rules: `db_01_<tool>` for instance 1 and `db_02_<tool>` for instance 2; include at least 6 concrete examples. | ✅ | 2026-04-15 |
| TASK-007 | Add transport usage guidance for `MCP_TRANSPORT=http|sse|stdio` and include endpoint examples for HTTP/SSE clients where applicable. | ✅ | 2026-04-15 |
| TASK-008 | Add a table mapping each tool family to intent: discovery, query, performance, security, data model, admin/write, generative dashboards. | ✅ | 2026-04-15 |
| TASK-009 | Add compatibility appendix listing alias patterns (`db_sql2019_*`, `db_db2019_*`, `db_01_sql2019_*`, `db_02_sql2019_*`) with warning that canonical names should be preferred. | ✅ | 2026-04-15 |

### Implementation Phase 3

- GOAL-003: Document scope, limitations, and safety boundaries explicitly.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-010 | Add explicit scope statement: SQL Server-oriented MCP server with dual-instance support and optional dashboards; no cross-DB engine support documented. | ✅ | 2026-04-15 |
| TASK-011 | Add limitation statement for Generative UI tools requiring `fastmcp[apps]`; provide fallback behavior note when unavailable. | ✅ | 2026-04-15 |
| TASK-012 | Add limitation statement for write operations: disabled by default and gated by confirmation and auth controls. | ✅ | 2026-04-15 |
| TASK-013 | Add operational limits section for query timeout, max rows, and rate-limiting controls from environment variables. | ✅ | 2026-04-15 |
| TASK-014 | Add non-goals section clarifying unsupported workflows (for example, repository administration, external orchestration logic, and non-SQL-Server dialect guarantees). | ✅ | 2026-04-15 |

### Implementation Phase 4

- GOAL-004: Integrate, validate, and publish the manual entry points.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-015 | Update `README.md` to add a “User Manual” link near the top-level usage/navigation section. | ✅ | 2026-04-15 |
| TASK-016 | Validate manual completeness by checking every canonical tool in `tool_map` appears at least once in `docs/users-manual.md`. | ✅ | 2026-04-15 |
| TASK-017 | Run markdown quality checks: heading continuity, code-fence correctness, and link validity for local links (`README.md`, `docs/users-manual.md`). | ✅ | 2026-04-15 |
| TASK-018 | Perform final review pass ensuring scope/limitations section matches runtime constraints currently implemented in `mcp_sqlserver/server.py`. | ✅ | 2026-04-15 |

## 3. Alternatives

- **ALT-001**: Keep all user guidance only in `README.md`. Rejected because `README.md` should remain concise and cannot safely hold full operational and tool-reference detail.
- **ALT-002**: Auto-generate tool documentation from AST/runtime introspection only. Rejected for initial rollout due to complexity and reduced editorial clarity for users.
- **ALT-003**: Split manual into many small docs immediately. Rejected for first delivery because a single canonical manual improves discoverability and onboarding.

## 4. Dependencies

- **DEP-001**: Source-of-truth tool registration in `mcp_sqlserver/server.py`.
- **DEP-002**: Existing run instructions and environment conventions in `README.md`.
- **DEP-003**: Existing governance/documentation baseline in `docs/` and `CONTRIBUTING.md`.

## 5. Files

- **FILE-001**: `docs/users-manual.md` - new comprehensive user manual.
- **FILE-002**: `README.md` - add navigation link to user manual.
- **FILE-003**: `mcp_sqlserver/server.py` - read-only source for tool and limitation extraction (no runtime edits expected).

## 6. Testing

- **TEST-001**: Verify all canonical tools from `_register_dual_instance_tools.tool_map` are documented in `docs/users-manual.md`.
- **TEST-002**: Verify all canonical generative tools from `_register_generative_dashboard_tools.tool_map` are documented.
- **TEST-003**: Verify manual includes explicit sections for “How to issue tools” and “Scope & Limitations”.
- **TEST-004**: Verify `README.md` includes a working relative link to `docs/users-manual.md`.
- **TEST-005**: Run markdown lint/readability pass (or equivalent manual checklist) with zero broken local links.

## 7. Risks & Assumptions

- **RISK-001**: Tool inventory can drift if code changes after manual publication.
- **RISK-002**: Over-documenting aliases may confuse users about canonical tool names.
- **RISK-003**: Runtime behavior may differ by environment when optional dependencies (Generative UI stack) are missing.
- **ASSUMPTION-001**: `mcp_sqlserver/server.py` remains the authoritative registration source for user-facing tools.
- **ASSUMPTION-002**: Current branch policy allows documentation additions without changing runtime APIs.
- **ASSUMPTION-003**: Users primarily need practical invocation guidance over low-level implementation details.

## 8. Related Specifications / Further Reading

[Comprehensive Best-Practices Plan](plan/process-repository-best-practices-1.md)
[Current Repository README](README.md)
[Tool Registration Source](mcp_sqlserver/server.py)
[GitHub Repository Best Practices Article](https://dev.to/pwd9000/github-repository-best-practices-23ck)