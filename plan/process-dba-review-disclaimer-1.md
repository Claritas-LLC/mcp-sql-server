---
goal: Add a DBA Review Disclaimer to Tool Recommendations and Remediation Guidance
version: 1.1
date_created: 2026-05-27
last_updated: 2026-05-27
owner: MCP SQL Server Team
status: Completed
tags: [process, safety, governance, recommendations, mcp, sqlserver]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-green)

This plan adds a standard DBA review disclaimer to every tool output that contains recommendations. The disclaimer is injected at the shared `build_report_envelope` level in `src/tools/analysis_contracts.py`, which is the single choke point used by all three recommendation-producing tools: `analyze_tab_health`, `analyze_db_data_model`, and `analyze_db_security`. This ensures one canonical message applies uniformly without per-tool edits to `sql_tools.py`.

## 1. Requirements & Constraints

- **REQ-001**: Add a standard DBA review disclaimer to every tool output that includes recommendations, remediation guidance, or suggested changes.
- **REQ-002**: Make the disclaimer wording consistent across tools so users receive one canonical message rather than tool-specific variants.
- **REQ-003**: Ensure the disclaimer applies to current recommendation-producing tools in `src/tools/` and to any new tools added later through the shared output helpers.
- **REQ-004**: Preserve existing finding, recommendation, and report envelope structures so clients do not break when the disclaimer is added.
- **REQ-005**: Ensure the disclaimer is visible in the final response payload and, where applicable, in summary text that users are most likely to read.
- **REQ-006**: Keep the current read-only posture of diagnostic tools unchanged; the disclaimer is informational and does not relax or alter write guardrails.
- **REQ-007**: Keep the disclaimer deterministic and non-conditional unless a tool explicitly returns no recommendations.
- **REQ-008**: Avoid duplicating the disclaimer inside every individual recommendation item if a shared top-level field or summary note can carry the same message cleanly.
- **REQ-009**: Update documentation so the tool catalog and diagnostics spec describe the new DBA review requirement.
- **REQ-010**: Add tests that verify the disclaimer appears whenever recommendations are present and remains absent only when a tool returns no recommendation content.
- **SEC-001**: The disclaimer must not weaken, bypass, or replace existing authorization, rate limiting, session tracking, or controlled-write enforcement.
- **SEC-002**: The implementation must not expose secrets, connection details, or privileged operational instructions in the disclaimer text.
- **CON-001**: The implementation must fit within the existing MCP server architecture and should prefer one shared helper over repetitive per-tool edits.
- **CON-002**: The disclaimer text should be short enough to remain visible in common client renderers and not materially increase response payload size.
- **CON-003**: The project’s current deterministic report envelope and redaction behavior must remain intact.
- **GUD-001**: Prefer adding the disclaimer in a shared analysis/output helper so the policy is enforced uniformly.
- **GUD-002**: Use clear, operational language such as “review and approve with a DBA before applying changes” rather than vague cautionary phrasing.
- **PAT-001**: Reuse existing output composition patterns in `src/tools/analysis_contracts.py` and `src/tools/sql_tools.py` rather than introducing a parallel formatting path.

## 2. Implementation Steps

### Implementation Phase 1 — Single-file change in `analysis_contracts.py`

- GOAL-001: Add the disclaimer constant and conditional injection in the shared envelope builder.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Add `DBA_REVIEW_DISCLAIMER` string constant to `src/tools/analysis_contracts.py`. | [x] | 2026-05-27 |
| TASK-002 | Modify `build_report_envelope` to conditionally include a `"disclaimer"` key when `recommendations` is non-empty. | [x] | 2026-05-27 |
| TASK-003 | Verify no other source files need changes — `build_report_envelope` is the single choke point for all three tools. | [x] | 2026-05-27 |

### Implementation Phase 2

- GOAL-002: Add regression tests and refresh documentation.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-004 | Add a test in `tests/` that asserts the disclaimer is present when `build_report_envelope` receives a non-empty recommendations list. | [x] | 2026-05-27 |
| TASK-005 | Add a test that asserts the disclaimer is absent when recommendations is empty. | [x] | 2026-05-27 |
| TASK-006 | Update `docs/mcp-tool-catalog.md` to document the `disclaimer` field. | [x] | 2026-05-27 |
| TASK-007 | Update `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` with the new output contract and sample payloads. | [x] | 2026-05-27 |

### Implementation Phase 3

- GOAL-003: Run lint, tests, and manual verification.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-008 | Run `ruff check .`. | [x] | 2026-05-27 |
| TASK-009 | Run `pytest -q`. | [x] | 2026-05-27 |
| TASK-010 | Confirm no recommendation-bearing tools are missed (all three flow through `build_report_envelope`). | [x] | 2026-05-27 |

## 3. Alternatives

- **ALT-001**: Append the disclaimer directly to every recommendation string. Not chosen because it duplicates text, makes testing harder, and risks inconsistent phrasing.
- **ALT-002**: Add the disclaimer only in documentation. Not chosen because the user asked for the warning to appear in tool outputs.
- **ALT-003**: Edit each tool individually. Not chosen because all three tools already funnel through `build_report_envelope`, making a single change cleaner and automatically future-proof.

## 4. Dependencies

- **DEP-001**: `src/tools/analysis_contracts.py` — sole code change location.
- **DEP-002**: `tests/` — add regression coverage for the disclaimer behavior.
- **DEP-003**: `docs/mcp-tool-catalog.md` and `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` — documentation updates.

## 5. Files

- **FILE-001**: `plan/process-dba-review-disclaimer-1.md` — This implementation plan.
- **FILE-002**: `src/tools/analysis_contracts.py` — Add disclaimer constant and conditional envelope injection.
- **FILE-003**: `tests/test_advanced_analysis_tools.py` — Add disclaimer regression tests.
- **FILE-004**: `docs/mcp-tool-catalog.md` — Document the new `disclaimer` field.
- **FILE-005**: `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` — Update output contract.

## 6. Testing

- **TEST-001**: `build_report_envelope` with non-empty recommendations includes `"disclaimer"` key with the canonical text.
- **TEST-002**: `build_report_envelope` with empty recommendations omits the `"disclaimer"` key entirely.
- **TEST-003**: The disclaimer text matches `DBA_REVIEW_DISCLAIMER` exactly (single source of truth).
- **TEST-004**: Existing envelope keys (`instance_number`, `database_name`, `tool`, `generated_at_utc`, `summary`, `severity_counts`, `findings`, `recommendations`) remain unchanged.

## 7. Risks & Assumptions

- **RISK-001**: Adding a new top-level output key may require client updates if consumers strictly validate the report schema. Mitigation: the key is additive and backwards-compatible.
- **ASSUMPTION-001**: All current and future recommendation-producing tools use `build_report_envelope` as their output composer. Verified: `analyze_tab_health`, `analyze_db_data_model`, and `analyze_db_security` all call it.
- **ASSUMPTION-002**: Users want a practical operational warning, not a legal disclaimer, so the wording stays concise.

## 8. Related Specifications / Further Reading

- `src/tools/analysis_contracts.py`
- `src/tools/sql_tools.py`
- `docs/mcp-tool-catalog.md`
- `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md`