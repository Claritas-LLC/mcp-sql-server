---
goal: Define Deterministic Thresholds and Calibration for analyze_tab_health Statistics Findings
version: 1.0
date_created: 2026-05-27
last_updated: 2026-05-27
owner: Cloud Solutions Architecture
status: 'Planned'
tags: [design, feature, sqlserver, diagnostics, thresholds, tuning]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This plan defines deterministic numeric thresholds, severity mapping, and calibration procedures for statistics-related findings in `db_<instance #>_sql2019_analyze_tab_health`. It is a companion to `feature-analyze-tab-health-statistics-1.md` and ensures consistent behavior across databases while preserving read-only diagnostics and predictable outputs.

## 1. Requirements & Constraints

- **REQ-001**: Define default numeric thresholds for stale statistics classification using `modification_counter`, `rows`, and staleness age.
- **REQ-002**: Define default numeric thresholds for low sampling quality classification using `rows_sampled / rows` ratio.
- **REQ-003**: Define severity levels (`low`, `medium`, `high`) for each statistics finding class using deterministic conditions.
- **REQ-004**: Define ranking/scoring logic so the tool surfaces highest-impact findings first in previews and recommendations.
- **REQ-005**: Define bounded threshold override inputs for future extensibility without breaking existing behavior.
- **REQ-006**: Define deterministic fallback behavior when DMV fields are `NULL`, missing, or zero.
- **REQ-007**: Define calibration workflow that uses representative metadata snapshots without requiring write operations.
- **REQ-008**: Define dual-instance consistency checks so `db_1` and `db_2` produce equivalent classification behavior.
- **SEC-001**: Threshold evaluation must remain metadata-only and read-only.
- **SEC-002**: Threshold evaluation must not require execution plans, query capture, or privileged maintenance commands.
- **SEC-003**: Threshold values and rationale must be documented without leaking sensitive object names in examples.
- **CON-001**: Keep baseline tool invocation simple; threshold overrides must be optional and bounded.
- **CON-002**: Preserve existing analysis envelope and deterministic error contracts.
- **CON-003**: Avoid introducing environment-specific hard dependencies for threshold computation.
- **GUD-001**: Prefer simple piecewise rules over opaque formulas for explainability.
- **GUD-002**: Ensure every threshold maps to a user-facing recommendation rationale.
- **PAT-001**: Implement thresholds via constants or a structured config object in `src/tools/sql_tools.py` with single-source-of-truth usage.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Specify baseline threshold constants and severity matrices.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Define baseline stale-statistics rules: classify as stale when `modification_counter >= max(500, 0.20 * rows)` or `days_since_last_update >= 30` with minimum `rows >= 1000`. |  |  |
| TASK-002 | Define severe stale-statistics rule: classify as high severity when `modification_counter >= max(20000, 0.35 * rows)` or `days_since_last_update >= 90` with `rows >= 100000`. |  |  |
| TASK-003 | Define low-sampling rule: classify as low sample when `rows_sampled / rows < 0.10` for `rows >= 10000`; medium severity at `< 0.05`; high severity at `< 0.01`. |  |  |
| TASK-004 | Define never-updated rule: classify as medium severity when `last_updated IS NULL`; high severity when table `rows >= 100000` and stat is user-visible/non-hypothetical. |  |  |
| TASK-005 | Define database-settings findings: `AUTO_UPDATE_STATISTICS=OFF` as high severity; `AUTO_CREATE_STATISTICS=OFF` as medium severity; async mode only informational. |  |  |
| TASK-006 | Define missing-coverage heuristic severity rules based on table size and write intensity proxies from metadata where available. |  |  |

### Implementation Phase 2

- GOAL-002: Define scoring and ordering to prioritize high-impact findings.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-007 | Create a deterministic impact score formula for each finding class, for example `score = severity_weight + size_weight + change_weight`. |  |  |
| TASK-008 | Define severity weights: `high=100`, `medium=60`, `low=30`, `info=10`. |  |  |
| TASK-009 | Define size weight tiers using `rows` bands: `<10k=5`, `10k-100k=15`, `100k-1m=30`, `>1m=50`. |  |  |
| TASK-010 | Define change weight tiers using `modification_counter/rows`: `<5%=5`, `5-20%=15`, `20-35%=30`, `>35%=45`. |  |  |
| TASK-011 | Define tie-break ordering: severity desc, score desc, row_count desc, schema asc, table asc, stat_name asc. |  |  |

### Implementation Phase 3

- GOAL-003: Add threshold constants and application logic in code with bounded override hooks.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-012 | Add a constants block in `src/tools/sql_tools.py` for all statistics thresholds and score weights with clear names and units. |  |  |
| TASK-013 | Implement helper functions in `src/tools/sql_tools.py` such as `_classify_stale_stats`, `_classify_sampling_quality`, and `_compute_stats_impact_score`. |  |  |
| TASK-014 | Ensure helper functions gracefully handle `NULL` and zero-division conditions with deterministic fallback outcomes. |  |  |
| TASK-015 | Add optional input overrides for threshold tuning with strict min/max bounds and defaults bound to constants. |  |  |
| TASK-016 | Apply the same helper path for both `db_1_sql2019_analyze_tab_health` and `db_2_sql2019_analyze_tab_health` registration flow. |  |  |

### Implementation Phase 4

- GOAL-004: Validate thresholds against representative scenarios and adjust only if measurable criteria fail.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-017 | Create synthetic metadata fixtures in `tests/test_advanced_analysis_tools.py` covering small, medium, and very large table scenarios. |  |  |
| TASK-018 | Add tests validating stale classification boundaries at exact threshold edges to prevent off-by-one errors. |  |  |
| TASK-019 | Add tests validating sampling classification boundaries and severity transitions. |  |  |
| TASK-020 | Add tests validating deterministic score/order output for mixed finding sets. |  |  |
| TASK-021 | Add tests validating override bounds rejection and default fallback behavior. |  |  |
| TASK-022 | Add tests verifying dual-instance consistency: identical inputs across instance bindings produce equivalent classified findings. |  |  |

### Implementation Phase 5

- GOAL-005: Publish calibration and operational guidance.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-023 | Update `docs/mcp-tool-catalog.md` with threshold table, default values, and override bounds. |  |  |
| TASK-024 | Update `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` with severity/score explanation and ranking semantics. |  |  |
| TASK-025 | Add a short calibration section to `docs/runbooks/scaling-strategy.md` describing when threshold overrides are justified. |  |  |
| TASK-026 | Define acceptance criteria for tuning changes: no regression to existing findings, deterministic ordering preserved, and runtime overhead within planned bounds. |  |  |

## 3. Alternatives

- **ALT-001**: Use machine-learned anomaly detection for thresholds. Not chosen due to nondeterminism and operational complexity.
- **ALT-002**: Use static single threshold for all object sizes. Not chosen because large-table and small-table risk profiles differ significantly.
- **ALT-003**: No override support. Not chosen because environment variability requires bounded tuning flexibility.
- **ALT-004**: Derive severity only from age (`days_since_last_update`). Not chosen because modification volume and row count are stronger risk signals.

## 4. Dependencies

- **DEP-001**: `plan/feature-analyze-tab-health-statistics-1.md` companion feature plan.
- **DEP-002**: `src/tools/sql_tools.py` analyze handler and recommendation builders.
- **DEP-003**: `src/tools/query_catalog.py` stale/never-updated/low-sample metadata query outputs.
- **DEP-004**: `tests/test_advanced_analysis_tools.py` testing harness and fixtures.
- **DEP-005**: Existing report envelope and finding/recommendation contracts.

## 5. Files

- **FILE-001**: `plan/design-analyze-tab-health-statistics-thresholds-1.md` - Companion threshold and calibration plan.
- **FILE-002**: `src/tools/sql_tools.py` - Add threshold constants, classifiers, scoring, and bounded override handling.
- **FILE-003**: `tests/test_advanced_analysis_tools.py` - Add threshold boundary and scoring determinism tests.
- **FILE-004**: `docs/mcp-tool-catalog.md` - Document defaults and bounds.
- **FILE-005**: `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` - Document severity and ranking semantics.
- **FILE-006**: `docs/runbooks/scaling-strategy.md` - Add threshold calibration guidance.

## 6. Testing

- **TEST-001**: Boundary tests for stale-statistics classification at exact ratio/count limits.
- **TEST-002**: Boundary tests for low-sampling severity tiers.
- **TEST-003**: Tests for never-updated classification with varied table sizes.
- **TEST-004**: Tests for disabled auto-stats settings mapping to expected severities.
- **TEST-005**: Tests for deterministic scoring and ordering across mixed findings.
- **TEST-006**: Tests for override input validation and min/max bound enforcement.
- **TEST-007**: Tests for dual-instance consistency under identical fixture input.
- **TEST-008**: Regression tests confirming existing non-statistics findings remain unchanged.

## 7. Risks & Assumptions

- **RISK-001**: Default thresholds may be too sensitive in write-heavy OLTP workloads, causing alert fatigue.
- **RISK-002**: Conservative thresholds may under-report issues in low-churn but latency-sensitive systems.
- **RISK-003**: Metadata-only heuristics for missing coverage may produce false positives without workload context.
- **RISK-004**: Override complexity may increase support burden if not documented with strict bounds.
- **ASSUMPTION-001**: `sys.dm_db_stats_properties` data quality is sufficient for stable classification.
- **ASSUMPTION-002**: Users prefer deterministic explainable heuristics over adaptive black-box models.
- **ASSUMPTION-003**: Dual SQL Server instances expose compatible DMV semantics in this deployment.

## 8. Related Specifications / Further Reading

- `plan/feature-analyze-tab-health-statistics-1.md`
- `src/tools/sql_tools.py`
- `src/tools/query_catalog.py`
- `tests/test_advanced_analysis_tools.py`
- `docs/mcp-tool-catalog.md`
- `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md`