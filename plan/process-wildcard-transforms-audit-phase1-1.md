---
goal: Phase 1 audit findings for wildcard transforms configuration contract — FastMCP 3.2.2 alignment gaps
version: 1.0
date_created: 2026-04-09
last_updated: 2026-04-09
owner: Harry Valdez
status: 'Completed'
tags: [process, audit, transforms, wildcard, phase1, findings, gap-analysis]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This document records the deterministic findings from WLD TASK-001 through TASK-003 (Phase 1) of `architecture-fastmcp-transforms-wildcard-1.md`. It audited `mcp_sqlserver/server.py` against FastMCP 3.2.2 (installed in `.venv`) and documents every gap, with exact class name mismatches, module path errors, and constructor signature deviations.

All six transform configurators were inspected. **All five non-visibility transforms currently produce silent failures when enabled** — they return `None` from their factory so the layer is unconditionally skipped by `_apply_provider_transform_layers`. No RuntimeError is raised. No user-visible error is surfaced. Only a `WARNING`-level log entry identifies the failure.

---

## 1. Requirements & Constraints

- **REQ-001**: Record the exact verified state of `_build_startup_config`, `_build_provider_transform_layers`, and `_apply_provider_transform_layers` against expected FastMCP 3.2.2 behavior.
- **REQ-002**: Identify all gaps, risks, or alignment deviations with exact file locations and FastMCP API evidence.
- **REQ-003**: Produce actionable TASK entries for every gap or deviation identified.
- **CON-001**: Audit must not change any runtime code; observe and record only.
- **CON-002**: Findings must be verifiable by re-running the inspection commands documented in Section 8.

---

## 2. Audit Findings

### Finding Group A — `_build_startup_config` (WLD-TASK-001)

**Server location**: `mcp_sqlserver/server.py` lines 355–382  
**Audit status: PASS**

All twenty (20) `MCP_TRANSFORM_*` and `MCP_TOOL_SEARCH_*` environment variables are present with correct types and defaults. Layer order default string is deterministic. All six transform families are explicitly opt-in (default `False`). No gaps found.

---

### Finding Group B — `_build_provider_transform_layers` (WLD-TASK-002)

**Server location**: `mcp_sqlserver/server.py` lines 1351–1394  
**Audit status: PASS with advisories**

Layer ordering logic, known-set validation, and append-missing-defaults pattern are all correct. Two advisories identified:

- **GAP-B1 (advisory)**: Unknown values in `MCP_TRANSFORM_LAYER_ORDER` are silently dropped. No `logger.warning` is emitted. An operator typo produces a dropped layer with zero diagnostic output.
- **GAP-B2 (advisory)**: `tool_search` is not in the provider layer pipeline — it is wired separately via `_configure_tool_search_transform`. This split is not documented in `.env.example`, making the pipeline mental model opaque for operators.

---

### Finding Group C — `_apply_provider_transform_layers` (WLD-TASK-003)

**Server location**: `mcp_sqlserver/server.py` lines 1396–1441  
**Audit status: PASS with advisory**

Idempotency guard, per-layer enable/disable gate, factory-callable guard, and exception guard are all correct. Structured log on completion is present.

- **GAP-C1 (advisory)**: `logger.info("Provider transform layering resolved", extra={...})` emits applied/skipped layer names only in the `extra` dict. Plain-text log handlers (e.g., `logging.StreamHandler` without a JSON formatter) do not surface the `extra` dict. Operators using default logging cannot see which layers were applied.

---

### Finding Group D — Transform Configurator Alignment (WLD-TASK-004 preview)

Six configurator functions were inspected. **Five of six have blocking gaps** that produce silent failure when enabled.

#### D1. `_configure_visibility_transform` — BLOCKING: Wrong class name + wrong kwargs

| Item | Current | Actual (FastMCP 3.2.2) |
| --- | --- | --- |
| Module | `fastmcp.server.transforms.visibility` | Same — OK |
| Class candidate | `["VisibilityTransform"]` | `Visibility` |
| First required param | *(not passed)* | `enabled: bool` (positional, required) |
| Filter params | `allowlist`, `denylist` | `names`, `keys`, `tags`, `components`, `match_all` |

**Failure mode**: `_instantiate_transform` logs `"Visibility transform unavailable: none of VisibilityTransform found in fastmcp.server.transforms.visibility"` and returns `None`. Layer is skipped.

#### D2. `_configure_namespace_transform` — BLOCKING: Wrong class name

| Item | Current | Actual (FastMCP 3.2.2) |
| --- | --- | --- |
| Module | `fastmcp.server.transforms.namespace` | Same — OK |
| Class candidate | `["NamespaceTransform"]` | `Namespace` |
| `prefix` kwarg | `kwargs["prefix"] = namespace_prefix` | Correct once class name is fixed (`Namespace(prefix: str)`) |

**Failure mode**: `_instantiate_transform` logs `"Namespace transform unavailable: none of NamespaceTransform found in ..."` and returns `None`. Layer is skipped.

#### D3. `_configure_tool_transformation_transform` — BLOCKING: Wrong module + wrong kwargs

| Item | Current | Actual (FastMCP 3.2.2) |
| --- | --- | --- |
| Module | `fastmcp.server.transforms.tool_transformation` | `fastmcp.server.transforms.tool_transform` |
| Class candidates | `["ToolTransformationTransform", "ToolTransformation", "ToolTransform"]` | `ToolTransform` (third candidate correct) |
| Constructor kwargs | `name_map`, `description_map` | `transforms: dict[str, ToolTransformConfig]` |

**Failure mode**: `ImportError` on `fastmcp.server.transforms.tool_transformation`. Logs import warning and returns `None`. Layer is skipped.

#### D4. `_configure_resources_as_tools_transform` — BLOCKING: Missing required constructor argument

| Item | Current | Actual (FastMCP 3.2.2) |
| --- | --- | --- |
| Module | `fastmcp.server.transforms.resources_as_tools` | Same — OK |
| Class candidates | `["ResourcesAsToolsTransform", "ResourcesAsTools"]` | `ResourcesAsTools` (second candidate correct) |
| Constructor call | `ResourcesAsTools(**{})` | `ResourcesAsTools(provider: FastMCP)` — requires active server instance |

**Constructor behavior**: `ResourcesAsTools.__init__` performs `isinstance(provider, FastMCP)` check and raises `TypeError` with a clear message if `provider` is not a FastMCP server. Passing `{}` falls through to the no-arg fallback `ResourcesAsTools()`, which also raises `TypeError`. Both failures are caught; function returns `None`.

**Fix required**: Pass the active FastMCP `mcp` server instance directly as the `provider`. Implemented by bypassing `_instantiate_transform` and using an inline `from ... import ResourcesAsTools; return ResourcesAsTools(mcp)` pattern. `mcp` is a module-level global in `server.py` — no threading needed.

#### D5. `_configure_prompts_as_tools_transform` — BLOCKING: Identical to D4

Same failure mode as D4. `PromptsAsTools(provider: FastMCP)` requires the active server instance.

#### D6. `_configure_code_mode_transform` — NON-BLOCKING: Module absent in FastMCP 3.2.2

| Item | Current | Actual (FastMCP 3.2.2) |
| --- | --- | --- |
| Module | `fastmcp.server.transforms.code_mode` | **Module does not exist** |
| Class candidates | `["CodeModeTransform", "CodeMode"]` | N/A |

**Failure mode**: `ImportError` → logs warning → returns `None`. This is expected: CodeMode is documented as experimental and is not yet published in 3.2.2. The graceful ImportError fallback is the correct behavior for now.

**No action required** until FastMCP adds `code_mode` to 3.x stable.

---

## 3. Implementation Steps

### Implementation Phase 2 — Configurator Gap Remediation

- GOAL-001: Correct all blocking class name, module path, kwarg, and constructor argument gaps identified in Finding Group D.

| Task | Description | Completed | Date |
| -------- | ----- | --------- | ---- |
| TASK-001 | In `_configure_visibility_transform`: change class candidate list from `["VisibilityTransform"]` to `["Visibility"]`. Change kwargs from `allowlist`/`denylist` keys to correct `Visibility` constructor params: add `enabled=True` (required bool), rename filter kwargs to `names` (from allowlist CSV) and drop `denylist` kwarg (no direct equivalent — document in ops guide). | ✅ | 2026-04-09 |
| TASK-002 | In `_configure_namespace_transform`: change class candidate list from `["NamespaceTransform"]` to `["Namespace"]`. `prefix` kwarg is already correct. | ✅ | 2026-04-09 |
| TASK-003 | In `_configure_tool_transformation_transform`: change module path from `fastmcp.server.transforms.tool_transformation` to `fastmcp.server.transforms.tool_transform`. Change kwargs from `name_map`/`description_map` to `transforms: dict[str, ToolTransformConfig]` pattern. Add a helper `_build_tool_transform_config` that constructs `ToolTransformConfig` entries from `MCP_TRANSFORM_TOOL_NAME_MAP` and `MCP_TRANSFORM_TOOL_DESCRIPTION_MAP` JSON values. | ✅ | 2026-04-09 |
| TASK-004 | Add `mcp` parameter to `_configure_resources_as_tools_transform` and `_configure_prompts_as_tools_transform`. Update `_build_provider_transform_layers` factory closures to capture the active `mcp` server reference at factory definition time using `functools.partial` or default-arg capture. Update `_apply_provider_transform_layers` to supply `mcp` when calling each factory that requires it. | ✅ | 2026-04-09 |
| TASK-005 | In `_build_provider_transform_layers`: add `logger.warning` for each entry in `raw_order` that is not in the `known` set (`GAP-B1`). | ✅ | 2026-04-09 |
| TASK-006 | In `_apply_provider_transform_layers`: augment `logger.info` call with a plain-text message string (e.g., `"Applied transforms: %s. Skipped: %s"`) in addition to the `extra` dict (`GAP-C1`). | ✅ | 2026-04-09 |
| TASK-007 | Update `.env.example` to: (a) separate `MCP_TRANSFORM_LAYER_ORDER` from `MCP_TOOL_SEARCH_ENABLED` with a comment explaining the two-pipeline model (`GAP-B2`), and (b) document that `MCP_TRANSFORM_TOOL_NAME_MAP` and `MCP_TRANSFORM_TOOL_DESCRIPTION_MAP` accept JSON dicts with `name`/`description` per tool. |  |  |

---

## 4. Alternatives

- **ALT-001**: Keep `_instantiate_transform` generic and add runtime detection of required constructor params via `inspect.signature`. Rejected: adds fragile reflection logic; explicit configurator args are more maintainable.
- **ALT-002**: Replace `allowlist`/`denylist` env var names with `names`/`deny` to match FastMCP param names exactly. Rejected: changing existing env var names is a breaking change for operators already using them; use a mapping layer in the configurator instead.
- **ALT-003**: Treat all BLOCKING gaps as single combined fix. Rejected: separate tasks per transform family allows incremental staging and rollback isolation.

---

## 5. Dependencies

- **DEP-001**: `mcp_sqlserver/server.py` — the file under audit and the remediation target.
- **DEP-002**: `plan/architecture-fastmcp-transforms-wildcard-1.md` — parent plan; TASK-004–008 in that plan correspond to this document's Phase 2 tasks.
- **DEP-003**: FastMCP 3.2.2 installed in `.venv` — confirmed version used for all inspection results.
- **DEP-004**: `fastmcp.server.transforms.tool_transform.ToolTransformConfig` — must be imported and documented in the `_build_tool_transform_config` helper (TASK-003).

---

## 6. Files

- **FILE-001**: `mcp_sqlserver/server.py` — lines 1257–1349 (six configurator functions), 1351–1394 (layer builder), 1396–1441 (layer applier).
- **FILE-002**: `.env.example` — operator documentation for transform env vars.
- **FILE-003**: `plan/architecture-fastmcp-transforms-wildcard-1.md` — parent plan to mark Phase 1 complete.
- **FILE-004**: `plan/process-fastmcp-execution-checklist-1.md` — checklist to mark WLD-TASK-001 through TASK-003 complete.

---

## 7. Risks & Assumptions

- **RISK-001**: `Visibility.enabled` parameter (required bool) has an unintuitive dual-role: it is both the toggle and the class constructor arg. If `enabled=True` is hardcoded in the configurator, the transform cannot be conditionally disabled at the class level — but this is correct behavior since the outer configurator already guards on `MCP_TRANSFORM_VISIBILITY_ENABLED`.
- **RISK-002**: `ToolTransformConfig` import may not be at a stable public path in FastMCP 3.2.2. Verify path before implementing TASK-003.
- **RISK-003**: `functools.partial` capture of `mcp` in `_build_provider_transform_layers` must happen after `mcp` is fully initialized. Verify startup call order before implementing TASK-004.
- **ASSUMPTION-001**: FastMCP 3.2.2 is the target runtime. All inspection outputs in this document are from that installed version.
- **ASSUMPTION-002**: CodeMode (`code_mode` module) is intentionally absent from 3.2.2 and its graceful ImportError fallback is the expected behavior per OPS-001 of the parent plan.

---

## 8. Related Specifications / Further Reading

[plan/architecture-fastmcp-transforms-wildcard-1.md](architecture-fastmcp-transforms-wildcard-1.md)
[plan/feature-prompts-as-tools-bridge-1.md](feature-prompts-as-tools-bridge-1.md)
[plan/process-fastmcp-execution-checklist-1.md](process-fastmcp-execution-checklist-1.md)
https://gofastmcp.com/servers/transforms/
https://gofastmcp.com/servers/transforms/resources-as-tools
https://gofastmcp.com/servers/transforms/prompts-as-tools
