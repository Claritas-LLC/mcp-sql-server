---
goal: Execute constrained Phase 3b transform coverage for Visibility with optional Namespace and ToolTransformation
version: 1.0
date_created: 2026-04-09
last_updated: 2026-04-09
owner: Harry Valdez
status: On Hold
tags: [architecture, fastmcp, transforms, visibility, namespace, tooltransformation, phase-3b]
---

# Introduction

![Status: On Hold](https://img.shields.io/badge/status-On%20Hold-orange)

This plan defines a constrained Phase 3b extension to increase FastMCP transform guidance coverage without changing the current runtime scope that excludes resources and prompts. This plan is on hold and superseded for active implementation by `plan/architecture-fastmcp-transforms-suite-phase3c-1.md`.

## 1. Requirements & Constraints

- **REQ-001**: Implement server-level Visibility controls for tool exposure using deterministic tags and/or names.
- **REQ-002**: Keep Namespace and ToolTransformation implementation optional and feature-flagged.
- **REQ-003**: Preserve existing tool names and behavior by default when optional transforms are disabled.
- **REQ-004**: Maintain compatibility with existing startup path and environment variables.
- **REQ-005**: Add tests that verify Visibility behavior and optional-transform no-op defaults.
- **SEC-001**: Visibility defaults must not broaden access to write-capable tools beyond current behavior.
- **SEC-002**: Any optional transform activation must be explicit via configuration and logged at startup.
- **OPS-001**: Keep runtime resilient when transform APIs are unavailable in the installed FastMCP version.
- **CON-001**: ResourcesAsTools and PromptsAsTools are optional-only and out of active scope for implementation because the current runtime does not expose resources/prompts in the active server path.
- **CON-002**: CodeMode remains optional and out of scope for this phase.
- **GUD-001**: Preserve plan-only incremental delivery: implement Visibility first, then evaluate optional transforms.
- **PAT-001**: Apply transforms at server level unless provider-level layering is intentionally introduced.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Add constrained Visibility transform support with deterministic defaults.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-001 | Add a startup-visible transform wiring function in `mcp_sqlserver/server.py` that can apply Visibility-based filtering via explicit config values. |  |  |
| TASK-002 | Define environment-variable controls for allowlist/blocklist behavior and document deterministic precedence. |  |  |
| TASK-003 | Ensure default configuration does not alter current tool exposure behavior. |  |  |

### Implementation Phase 2

- GOAL-002: Add optional Namespace and ToolTransformation scaffolding with no default behavior change.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-004 | Add optional Namespace transform wiring guarded by explicit environment toggle and namespace value. |  |  |
| TASK-005 | Add optional ToolTransformation mapping support for selected tool rename/description updates under explicit configuration. |  |  |
| TASK-006 | Add startup logs that indicate which optional transforms are active for a given run. |  |  |

### Implementation Phase 3

- GOAL-003: Validate constrained transform behavior and maintain backward compatibility.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-007 | Add/update tests in `tests/test_server_startup_config.py` for Visibility and optional transform activation paths. |  |  |
| TASK-008 | Add/update tests in `tests/test_blackbox_http.py` for expected MCP endpoint behavior with transforms disabled and enabled. |  |  |
| TASK-009 | Run compatibility checks to confirm existing tool calls remain valid in default configuration. |  |  |

### Implementation Phase 4

- GOAL-004: Document scope boundaries and optional transform policy.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-010 | Update `README.md` transform section to declare Visibility as covered and Namespace/ToolTransformation as optional toggles. |  |  |
| TASK-011 | Update `DEPLOYMENT.md` with operational guidance for transform toggles and safe rollout order. |  |  |
| TASK-012 | Explicitly document that ResourcesAsTools and PromptsAsTools remain optional and not enabled by default due current runtime scope. |  |  |

## 3. Alternatives

- **ALT-001**: Implement full transform suite at once (Visibility, Namespace, ToolTransformation, ResourcesAsTools, PromptsAsTools, CodeMode). Rejected to avoid scope expansion and regression risk.
- **ALT-002**: Leave transform coverage unchanged and accept partial guidance alignment. Rejected because full guidance coverage is desired.
- **ALT-003**: Enable Namespace and ToolTransformation by default. Rejected because default behavior stability is required.

## 4. Dependencies

- **DEP-001**: Existing transform setup in `mcp_sqlserver/server.py` from Phase 3.
- **DEP-002**: Existing startup tests and blackbox HTTP tests.
- **DEP-003**: FastMCP runtime version support for selected transforms.

## 5. Files

- **FILE-001**: `mcp_sqlserver/server.py` - add constrained Visibility and optional transform wiring.
- **FILE-002**: `tests/test_server_startup_config.py` - add transform startup-path unit tests.
- **FILE-003**: `tests/test_blackbox_http.py` - verify endpoint behavior under transform toggles.
- **FILE-004**: `README.md` - document constrained transform coverage.
- **FILE-005**: `DEPLOYMENT.md` - add rollout guidance for transform toggles.
- **FILE-006**: `.env.example` - add visibility/optional transform environment variable docs.

## 6. Testing

- **TEST-001**: Validate default no-op behavior for all new transform toggles.
- **TEST-002**: Validate Visibility filtering behavior for selected tool names/tags.
- **TEST-003**: Validate optional Namespace transform behavior when explicitly enabled.
- **TEST-004**: Validate optional ToolTransformation behavior when explicitly enabled.
- **TEST-005**: Run integration bundle and confirm no regressions in startup/auth/readonly behavior.

## 7. Risks & Assumptions

- **RISK-001**: Incorrect Visibility configuration may unintentionally hide required operational tools.
- **RISK-002**: Optional name transformations can break downstream clients if enabled without migration communication.
- **RISK-003**: FastMCP version drift may require defensive import guards for some transform APIs.
- **ASSUMPTION-001**: Current runtime remains tool-centric and does not require resource/prompt exposure by default.
- **ASSUMPTION-002**: Optional transform toggles are acceptable for incremental rollout.

## 8. Related Specifications / Further Reading

https://gofastmcp.com/servers/transforms/transforms
https://gofastmcp.com/servers/visibility
https://gofastmcp.com/servers/transforms/namespace
https://gofastmcp.com/servers/transforms/tool-transformation
https://gofastmcp.com/servers/transforms/resources-as-tools
https://gofastmcp.com/servers/transforms/prompts-as-tools
plan/architecture-fastmcp-plan-index-1.md
plan/architecture-fastmcp-server-alignment-1.md
plan/architecture-fastmcp-transforms-routes-phase3-1.md
