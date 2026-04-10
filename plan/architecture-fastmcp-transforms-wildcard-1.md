---
goal: Align MCP SQL Server runtime with the full FastMCP transforms catalog under /servers/transforms/*
version: 1.0
date_created: 2026-04-09
last_updated: 2026-04-09
owner: Harry Valdez
status: 'Completed'
tags: [architecture, fastmcp, transforms, namespace, tool-transformation, tool-search, resources-as-tools, prompts-as-tools, code-mode]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan defines deterministic implementation and validation steps to align runtime behavior with FastMCP transforms documentation across all built-in transform pages under `/servers/transforms/*`, while preserving default-safe behavior and existing production compatibility.

## 1. Requirements & Constraints

- **REQ-001**: Validate and enforce transform pipeline mental model (provider-level first, server-level second) in `mcp_sqlserver/server.py` using `_build_provider_transform_layers` and `_apply_provider_transform_layers`.
- **REQ-002**: Validate and enforce fixed transform order for server runtime: Visibility, Namespace, ToolTransformation, ToolSearch, ResourcesAsTools, PromptsAsTools, CodeMode.
- **REQ-003**: Ensure startup toggles remain explicit opt-in for high-surface transforms (`MCP_TRANSFORM_RESOURCES_AS_TOOLS_ENABLED`, `MCP_TRANSFORM_PROMPTS_AS_TOOLS_ENABLED`, `MCP_TRANSFORM_CODE_MODE_ENABLED`).
- **REQ-004**: Ensure tool search behavior supports both `regex` and `bm25` strategies through `_configure_tool_search_transform` and existing `MCP_TOOL_SEARCH_*` settings.
- **REQ-005**: Ensure transforms that generate synthetic tools (`search_tools`, `call_tool`, `list_resources`, `read_resource`, `list_prompts`, `get_prompt`) route through middleware/auth/visibility pipeline.
- **REQ-006**: Ensure startup diagnostics expose active transforms, skipped transforms, and compatibility fallback events for unavailable symbols.
- **REQ-007**: Ensure all transform defaults preserve current behavior when no transform enable flags are set.
- **SEC-001**: No transform may broaden write capability beyond existing `ALLOW_WRITE` and confirmation controls.
- **SEC-002**: Auth and visibility filtering must apply consistently to synthetic tool listings and proxy executions.
- **SEC-003**: CodeMode remains experimental and must be gated by explicit policy in `MCP_TRANSFORM_CODE_MODE_POLICY` with safe default.
- **OPS-001**: Runtime must continue startup when optional transform APIs are unavailable, with deterministic fallback logs.
- **OPS-002**: Documentation must define staging-first rollout and rollback steps for each transform family.
- **CON-001**: Preserve existing public tool names and behavior in default-off transform configuration.
- **CON-002**: Do not remove existing environment variables from `.env.example`.
- **CON-003**: Do not change transport defaults or startup entrypoint contract.
- **GUD-001**: Keep transform configuration single-sourced through startup settings construction.
- **PAT-001**: Apply transforms through explicit configurator functions: `_configure_visibility_transform`, `_configure_namespace_transform`, `_configure_tool_transformation_transform`, `_configure_resources_as_tools_transform`, `_configure_prompts_as_tools_transform`, `_configure_code_mode_transform`, `_configure_tool_search_transform`.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Establish deterministic wildcard transforms configuration contract.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-001 | Audit `mcp_sqlserver/server.py` `_build_startup_config` to verify all `MCP_TRANSFORM_*` and `MCP_TOOL_SEARCH_*` variables are parsed with explicit defaults and type normalization. | ✅ | 2026-04-09 |
| TASK-002 | Audit `mcp_sqlserver/server.py` `_build_provider_transform_layers` to verify transform-layer metadata contains stable ordering and explicit enable flags for each transform family. | ✅ | 2026-04-09 |
| TASK-003 | Audit `mcp_sqlserver/server.py` `_apply_provider_transform_layers` to verify startup emits deterministic summary output for enabled, skipped, and fallback transform states. | ✅ | 2026-04-09 |

### Implementation Phase 2

- GOAL-002: Align transform configurators with documented FastMCP semantics.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-004 | Validate `_configure_namespace_transform` behavior against docs: underscore prefix for tool/prompt names and URI path segment behavior for resources/templates. | ✅ | 2026-04-09 |
| TASK-005 | Validate `_configure_tool_transformation_transform` supports deterministic name/description mapping from `MCP_TRANSFORM_TOOL_NAME_MAP` and `MCP_TRANSFORM_TOOL_DESCRIPTION_MAP`. | ✅ | 2026-04-09 |
| TASK-006 | Validate `_configure_tool_search_transform` supports strategy selection (`regex`, `bm25`), max result control, pinned tools, and synthetic tool-name overrides. | ✅ | 2026-04-09 |
| TASK-007 | Validate `_configure_resources_as_tools_transform` and `_configure_prompts_as_tools_transform` pass FastMCP server instance (not raw provider) to generated bridge transforms. | ✅ | 2026-04-09 |
| TASK-008 | Validate `_configure_code_mode_transform` keeps default-safe behavior and records experimental gating status in startup diagnostics. | ✅ | 2026-04-09 |

### Implementation Phase 3

- GOAL-003: Implement deterministic automated verification for wildcard transforms behavior.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-009 | Extend `tests/test_server_startup_config.py` with assertions for layer ordering, enable flags, missing-symbol fallback, and startup summary content for all transform families. | ✅ | 2026-04-09 |
| TASK-010 | Extend `tests/test_blackbox_http.py` with synthetic tool exposure checks for tool-search, resources-as-tools, and prompts-as-tools under enabled and disabled configurations. | ✅ | 2026-04-09 |
| TASK-011 | Add assertions in `tests/test_blackbox_http.py` that transformed discovery endpoints respect auth and visibility controls under HTTP transport. | ✅ | 2026-04-09 |
| TASK-012 | Execute regression gates `tests/test_hardening_controls.py` and `tests/test_readonly_sql.py` to verify transform enablement does not weaken security posture. | ✅ | 2026-04-09 |

### Implementation Phase 4

- GOAL-004: Complete operator-facing documentation for transforms/* rollout and troubleshooting.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-013 | Update `.env.example` with grouped transform settings and deterministic descriptions of defaults, safety impact, and activation precedence. | ✅ | 2026-04-09 |
| TASK-014 | Update `README.md` with transform matrix covering Namespace, Tool Transformation, Tool Search, Resources as Tools, Prompts as Tools, and Code Mode behaviors. | ✅ | 2026-04-09 |
| TASK-015 | Update `DEPLOYMENT.md` with staged rollout procedure, smoke checks, rollback toggles, and production-safe enablement order. | ✅ | 2026-04-09 |

### Implementation Phase 5

- GOAL-005: Publish release evidence and update plan index linkage.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-016 | Generate transform validation artifacts under `testing/` with timestamped filenames for startup, auth, transform, and integration gates. | ✅ | 2026-04-09 |
| TASK-017 | Update `plan/architecture-fastmcp-plan-index-1.md` to register this plan as the wildcard transforms reference and execution dependency. | ✅ | 2026-04-09 |
| TASK-018 | Update `plan/process-fastmcp-execution-checklist-1.md` with owner/date mapping for TASK-001 through TASK-017. | ✅ | 2026-04-09 |

## 3. Alternatives

- **ALT-001**: Keep transform coverage split across multiple phase plans without a wildcard consolidation artifact. Rejected because wildcard request requires one deterministic cross-transform execution contract.
- **ALT-002**: Enable all transforms by default to maximize feature surface. Rejected because default-safe operational posture is required.
- **ALT-003**: Implement custom transform wrappers for all built-ins. Rejected because it increases maintenance burden and diverges from upstream FastMCP behavior.

## 4. Dependencies

- **DEP-001**: `mcp_sqlserver/server.py` existing transform configurators and provider-layer functions.
- **DEP-002**: Existing runtime settings and environment parsing path.
- **DEP-003**: Existing tests in `tests/test_server_startup_config.py`.
- **DEP-004**: Existing blackbox tests in `tests/test_blackbox_http.py`.
- **DEP-005**: Existing hardening and read-only safety tests in `tests/test_hardening_controls.py` and `tests/test_readonly_sql.py`.
- **DEP-006**: Existing plan suite references in `plan/architecture-fastmcp-plan-index-1.md`.

## 5. Files

- **FILE-001**: `mcp_sqlserver/server.py` - enforce wildcard transforms runtime contract and diagnostics.
- **FILE-002**: `tests/test_server_startup_config.py` - startup and layer-order verification for all transform families.
- **FILE-003**: `tests/test_blackbox_http.py` - synthetic tool visibility and runtime behavior checks.
- **FILE-004**: `tests/test_hardening_controls.py` - security regression verification.
- **FILE-005**: `tests/test_readonly_sql.py` - write-protection regression verification.
- **FILE-006**: `.env.example` - transform and tool-search environment variable documentation.
- **FILE-007**: `README.md` - transform behavior matrix and client compatibility guidance.
- **FILE-008**: `DEPLOYMENT.md` - rollout, fallback, and incident response guidance.
- **FILE-009**: `plan/architecture-fastmcp-plan-index-1.md` - wildcard plan registration.
- **FILE-010**: `plan/process-fastmcp-execution-checklist-1.md` - execution tracking updates.

## 6. Testing

- **TEST-001**: `pytest tests/test_server_startup_config.py` validates transform configuration parsing, layer ordering, and fallback logs.
- **TEST-002**: `pytest tests/test_blackbox_http.py` validates HTTP behavior for transformed and non-transformed tool listings.
- **TEST-003**: `pytest tests/test_hardening_controls.py` validates auth and hardening invariants with transforms toggled.
- **TEST-004**: `pytest tests/test_readonly_sql.py` validates write-protection invariants with transforms toggled.
- **TEST-005**: Manual smoke validates `search_tools`/`call_tool`, `list_resources`/`read_resource`, and `list_prompts`/`get_prompt` visibility under staged toggle activation.

## 7. Risks & Assumptions

- **RISK-001**: FastMCP version drift may change transform symbol names or constructor signatures.
- **RISK-002**: Multiple synthetic tool generators can introduce naming conflicts if custom names are misconfigured.
- **RISK-003**: CodeMode experimental behavior may evolve and require compatibility shims.
- **RISK-004**: Overly broad visibility rules can hide required synthetic discovery tools.
- **ASSUMPTION-001**: Existing transform functions in `mcp_sqlserver/server.py` remain the canonical integration points.
- **ASSUMPTION-002**: Operators prefer explicit feature flags for transforms with larger surface area.
- **ASSUMPTION-003**: Staging environment exists for transform rollout and gate verification.

## 8. Related Specifications / Further Reading

https://gofastmcp.com/servers/transforms/transforms
https://gofastmcp.com/servers/transforms/namespace
https://gofastmcp.com/servers/transforms/tool-transformation
https://gofastmcp.com/servers/transforms/tool-search
https://gofastmcp.com/servers/transforms/resources-as-tools
https://gofastmcp.com/servers/transforms/prompts-as-tools
https://gofastmcp.com/servers/transforms/code-mode
plan/architecture-fastmcp-plan-index-1.md
plan/architecture-fastmcp-transforms-routes-phase3-1.md
plan/architecture-fastmcp-transforms-phase3b-1.md
plan/architecture-fastmcp-transforms-suite-phase3c-1.md
plan/feature-prompts-as-tools-bridge-1.md
plan/process-wildcard-transforms-audit-phase1-1.md