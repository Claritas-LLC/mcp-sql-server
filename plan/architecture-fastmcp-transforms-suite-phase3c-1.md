---
goal: Implement full FastMCP transform suite and provider-level layering patterns for MCP SQL Server
version: 1.0
date_created: 2026-04-09
last_updated: 2026-04-09
owner: Harry Valdez
status: Completed
tags: [architecture, fastmcp, transforms, visibility, namespace, tooltransformation, resources-as-tools, prompts-as-tools, codemode, provider-layering, phase-3c]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan defines a deterministic implementation of the broader FastMCP transform suite (Namespace, ToolTransformation, Visibility, ResourcesAsTools, PromptsAsTools, CodeMode) with explicit provider-level transform layering, preserving backward compatibility and default-safe behavior.

## 1. Requirements & Constraints

- **REQ-001**: Implement server startup wiring for Visibility, Namespace, ToolTransformation, ResourcesAsTools, PromptsAsTools, and CodeMode in `mcp_sqlserver/server.py`.
- **REQ-002**: Implement provider-level transform layering using deterministic ordering with explicit pipeline stages.
- **REQ-003**: Maintain backward compatibility when all new transform toggles are disabled.
- **REQ-004**: Add explicit environment variables in `.env.example` for each transform and each provider-layer pipeline stage.
- **REQ-005**: Add startup diagnostics that report active transforms, stage order, and compatibility fallback events.
- **REQ-006**: Add test coverage for default-off behavior and enabled behavior for every transform family.
- **REQ-007**: Add deterministic transform-application entrypoints and helper functions with exact names:
  - `_configure_visibility_transform`
  - `_configure_namespace_transform`
  - `_configure_tool_transformation_transform`
  - `_configure_resources_as_tools_transform`
  - `_configure_prompts_as_tools_transform`
  - `_configure_code_mode_transform`
  - `_build_provider_transform_layers`
  - `_apply_provider_transform_layers`
- **SEC-001**: Visibility rules must be applied before write-capable tool exposure logic and must never expand write access by default.
- **SEC-002**: ResourcesAsTools and PromptsAsTools must remain disabled by default and require explicit enable flags.
- **SEC-003**: CodeMode must be disabled by default and gated by explicit feature flag and safe prompt-policy configuration.
- **OPS-001**: If a transform API is unavailable in installed FastMCP version, startup must log deterministic fallback and continue with remaining enabled transforms.
- **OPS-002**: Provider-layer ordering must be deterministic and stable across restarts.
- **CON-001**: Existing HTTP and stdio startup flows must remain functional with no required deployment changes when toggles are unset.
- **CON-002**: Existing test suites in `tests/test_server_startup_config.py`, `tests/test_blackbox_http.py`, and `tests/test_hardening_controls.py` must continue to pass in default-off configuration.
- **GUD-001**: Apply server-level transforms only after provider-level transform layers are resolved and validated.
- **PAT-001**: Use a fixed layer order:
  - Layer 1: Visibility
  - Layer 2: Namespace
  - Layer 3: ToolTransformation
  - Layer 4: ResourcesAsTools
  - Layer 5: PromptsAsTools
  - Layer 6: CodeMode

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Establish transform configuration contract and deterministic provider-layer resolution.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-001 | Add transform configuration constants and environment parsing in `mcp_sqlserver/server.py` for all six transform families and provider-layer toggle controls. | Yes | 2026-04-09 |
| TASK-002 | Implement `_build_provider_transform_layers` to construct ordered layer metadata from validated configuration values. | Yes | 2026-04-09 |
| TASK-003 | Implement `_apply_provider_transform_layers` to apply enabled layers in strict order and emit startup diagnostics for each applied layer. | Yes | 2026-04-09 |

### Implementation Phase 2

- GOAL-002: Implement core transform wiring functions with default-safe behavior.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-004 | Implement `_configure_visibility_transform` with allowlist and denylist support by exact tool name and deterministic precedence rules. | Yes | 2026-04-09 |
| TASK-005 | Implement `_configure_namespace_transform` with explicit namespace prefix mapping and opt-in activation flag. | Yes | 2026-04-09 |
| TASK-006 | Implement `_configure_tool_transformation_transform` for deterministic rename and description rewrite maps loaded from environment-backed JSON settings. | Yes | 2026-04-09 |

### Implementation Phase 3

- GOAL-003: Implement resource, prompt, and code-mode transforms with strict safety gates.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-007 | Implement `_configure_resources_as_tools_transform` guarded by `MCP_TRANSFORM_RESOURCES_AS_TOOLS_ENABLED` and runtime capability detection. | Yes | 2026-04-09 |
| TASK-008 | Implement `_configure_prompts_as_tools_transform` guarded by `MCP_TRANSFORM_PROMPTS_AS_TOOLS_ENABLED` and runtime capability detection. | Yes | 2026-04-09 |
| TASK-009 | Implement `_configure_code_mode_transform` guarded by `MCP_TRANSFORM_CODE_MODE_ENABLED` and constrained policy settings for safe operation. | Yes | 2026-04-09 |

### Implementation Phase 4

- GOAL-004: Integrate transforms into startup path and preserve compatibility defaults.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-010 | Update server startup sequence in `mcp_sqlserver/server.py` so transform pipeline assembly executes in one canonical path before `run_server_entrypoint` starts transport. | Yes | 2026-04-09 |
| TASK-011 | Ensure default-off behavior produces identical tool exposure and endpoint behavior compared to current baseline. | Yes | 2026-04-09 |
| TASK-012 | Add explicit startup log summary listing enabled transforms, skipped transforms, and fallback reasons. | Yes | 2026-04-09 |

### Implementation Phase 5

- GOAL-005: Validate transform coverage and update operator documentation.

| Task | Description | Completed | Date |
| -------- | -------- | --------- | ---------- |
| TASK-013 | Add unit tests to `tests/test_server_startup_config.py` for layer builder, layer applier, and each transform function default-on/default-off permutations. | Yes | 2026-04-09 |
| TASK-014 | Add blackbox behavior tests in `tests/test_blackbox_http.py` to verify MCP endpoint tool visibility and naming under configured transforms. | Yes | 2026-04-09 |
| TASK-015 | Update `README.md`, `DEPLOYMENT.md`, and `.env.example` with full transform matrix, provider-layer order, and rollout guidance. | Yes | 2026-04-09 |

## 3. Alternatives

- **ALT-001**: Keep constrained Phase 3b only (Visibility required, others optional). Rejected because the request requires broader suite implementation.
- **ALT-002**: Implement all transforms only at server level without provider-layer abstraction. Rejected because provider-level layering patterns are explicitly requested.
- **ALT-003**: Enable ResourcesAsTools, PromptsAsTools, and CodeMode by default. Rejected because current runtime posture requires explicit opt-in safety controls.

## 4. Dependencies

- **DEP-001**: Existing startup and transform infrastructure in `mcp_sqlserver/server.py`.
- **DEP-002**: Existing startup and blackbox test harness in `tests/test_server_startup_config.py` and `tests/test_blackbox_http.py`.
- **DEP-003**: FastMCP package support for transform APIs used by this plan.
- **DEP-004**: Existing auth and hardening behavior validated in `tests/test_hardening_controls.py`.
- **DEP-005**: Prior plan artifacts `plan/architecture-fastmcp-transforms-routes-phase3-1.md` and `plan/architecture-fastmcp-transforms-phase3b-1.md`.

## 5. Files

- **FILE-001**: `mcp_sqlserver/server.py` - implement six transform configurators, provider-layer builder/applier, and startup integration.
- **FILE-002**: `tests/test_server_startup_config.py` - add deterministic startup and transform-layer tests.
- **FILE-003**: `tests/test_blackbox_http.py` - add endpoint behavior verification with transform permutations.
- **FILE-004**: `tests/test_hardening_controls.py` - verify transform behavior does not weaken write/auth controls.
- **FILE-005**: `README.md` - document full transform suite and provider-level layering pattern.
- **FILE-006**: `DEPLOYMENT.md` - document rollout, fallback, and compatibility policy.
- **FILE-007**: `.env.example` - add explicit variables for all transform toggles and provider-layer options.
- **FILE-008**: `plan/architecture-fastmcp-transforms-suite-phase3c-1.md` - canonical plan for broader transform suite implementation.

## 6. Testing

- **TEST-001**: Verify default-off transform configuration preserves baseline tool list and endpoint behavior.
- **TEST-002**: Verify each transform can be independently enabled and produces deterministic expected behavior.
- **TEST-003**: Verify provider-layer ordering is stable and matches PAT-001 in startup diagnostics.
- **TEST-004**: Verify unsupported transform APIs produce fallback logs without startup failure.
- **TEST-005**: Run startup/auth/transform/integration gate bundles and confirm all pass after implementation.

## 7. Risks & Assumptions

- **RISK-001**: Transform interactions may create unexpected tool-name collisions when Namespace and ToolTransformation are both enabled.
- **RISK-002**: ResourcesAsTools and PromptsAsTools may increase surface area and response payload size when enabled.
- **RISK-003**: CodeMode activation can introduce elevated behavioral variability if guardrails are incomplete.
- **RISK-004**: FastMCP version changes can alter transform API signatures and require compatibility shims.
- **ASSUMPTION-001**: Provider-layer transform APIs are available or can be emulated with deterministic wrappers.
- **ASSUMPTION-002**: Runtime operators prefer default-safe posture with explicit opt-in for high-impact transforms.

## 8. Related Specifications / Further Reading

https://gofastmcp.com/servers/transforms/transforms
https://gofastmcp.com/servers/transforms/namespace
https://gofastmcp.com/servers/transforms/tool-transformation
https://gofastmcp.com/servers/visibility
https://gofastmcp.com/servers/transforms/resources-as-tools
https://gofastmcp.com/servers/transforms/prompts-as-tools
https://gofastmcp.com/servers/transforms/code-mode
plan/architecture-fastmcp-plan-index-1.md
plan/architecture-fastmcp-server-alignment-1.md
plan/architecture-fastmcp-transforms-routes-phase3-1.md
plan/architecture-fastmcp-transforms-phase3b-1.md
