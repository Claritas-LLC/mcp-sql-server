---
goal: Extend analyze_tab_health to Detect Table and Index Statistics Issues and Provide Recommendations
version: 1.0
date_created: 2026-05-27
last_updated: 2026-05-27
owner: Cloud Solutions Architecture
status: Planned
tags: [feature, sqlserver, diagnostics, statistics, mcp, analysis]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This plan defines the changes required to extend `db_<instance #>_sql2019_analyze_tab_health` so it identifies SQL Server table and index statistics issues and returns actionable recommendations alongside the existing table-size, fragmented-index, and missing-primary-key findings. The plan preserves the tool's read-only posture and uses metadata- and DMV-based analysis to avoid introducing write behavior or execution-plan dependencies.

## 1. Requirements & Constraints

- **REQ-001**: Extend `db_<instance #>_sql2019_analyze_tab_health` to analyze statistics health in addition to current table and index checks.
- **REQ-002**: The tool must identify stale statistics using SQL Server metadata available from `sys.stats` and `sys.dm_db_stats_properties`.
- **REQ-003**: The tool must identify statistics that have never been updated, where such state is observable from metadata.
- **REQ-004**: The tool must identify tables lacking usable user-table statistics coverage using deterministic metadata rules.
- **REQ-005**: The tool must provide actionable recommendations for each statistics issue class it detects.
- **REQ-006**: The tool must incorporate optional histogram-based analysis only when explicitly enabled by a new input parameter; the default behavior must remain metadata-only.
- **REQ-007**: The tool output must preserve the current report envelope structure returned by `build_report_envelope`.
- **REQ-008**: The tool summary must include statistics-related counts and previews in addition to existing table health summary fields.
- **REQ-009**: The tool must continue supporting `schema_name`, `table_name`, `include_indexes`, and `top_n`.
- **REQ-010**: Any new statistics findings must respect `schema_name` and `table_name` filters consistently.
- **REQ-011**: The implementation must support both concrete numeric bindings `db_1_sql2019_analyze_tab_health` and `db_2_sql2019_analyze_tab_health` without behavioral drift.
- **SEC-001**: The implementation must remain read-only and must not issue `UPDATE STATISTICS`, `sp_updatestats`, index rebuilds, or any other write or maintenance command.
- **SEC-002**: Any histogram inspection query must be implemented using read-only SQL and must not expose raw sensitive values in logs or report evidence.
- **SEC-003**: Audit logging, authorization, session touch, and rate limiting behavior in `src/tools/sql_tools.py` must remain unchanged.
- **SEC-004**: The implementation must continue using deterministic validation and deterministic error contracts.
- **CON-001**: The existing tool name and baseline input contract must not be broken.
- **CON-002**: The implementation must fit within the current architecture boundaries: query helper generation in `src/tools/query_catalog.py`, tool orchestration in `src/tools/sql_tools.py`, documentation in `docs/`, and unit coverage in `tests/`.
- **CON-003**: Histogram-based logic must not depend on query plans, Query Store, or privileged operational features not already assumed by this repository.
- **CON-004**: If SQL Server metadata cannot reliably prove a "missing statistics" condition for a given case, the tool must classify it as a heuristic finding and label it accordingly.
- **GUD-001**: Prefer metadata- and DMV-based checks first because they are cheap, deterministic, and safe for remote diagnostics.
- **GUD-002**: Treat histogram analysis as an optional second-order enhancement for high-signal recommendations only.
- **PAT-001**: Reuse existing analysis patterns: query helpers in `src/tools/query_catalog.py`, findings via `build_finding`, recommendations via `build_recommendation`, and final output via `build_report_envelope`.
- **PAT-002**: Add discrete finding codes for each statistics issue class so clients can automate handling.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Define the statistics issue model, thresholds, and input contract additions for `analyze_tab_health`.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Define exact statistics issue classes for `analyze_tab_health`: `stale_statistics`, `never_updated_statistics`, `low_sampled_statistics`, `auto_update_disabled_database`, `auto_create_disabled_database`, and `missing_statistics_coverage_candidates`. |  |  |
| TASK-002 | Define deterministic thresholds in `src/tools/sql_tools.py` or a nearby helper for stale statistics classification using `modification_counter`, `rows`, and `last_updated`. |  |  |
| TASK-003 | Define one new optional input parameter `include_statistics: bool = True` for `db_<instance #>_sql2019_analyze_tab_health`. |  |  |
| TASK-004 | Define one new optional input parameter `include_histogram_analysis: bool = False` so histogram inspection is opt-in. |  |  |
| TASK-005 | Define one new optional input parameter `histogram_top_n: int = 10` with bounded validation so histogram analysis has deterministic limits. |  |  |
| TASK-006 | Define exact finding codes and severities for each statistics issue class in the tool logic. |  |  |

### Implementation Phase 2

- GOAL-002: Add SQL catalog query helpers required for statistics analysis.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-007 | Extend `src/tools/query_catalog.py` by reusing `stale_statistics_query(top_n)` for stale-statistics inventory in `analyze_tab_health`. |  |  |
| TASK-008 | Add a new helper in `src/tools/query_catalog.py` named `statistics_never_updated_query(top_n: int) -> str` that returns user-table statistics where `last_updated` is `NULL` or equivalent metadata indicates no update history. |  |  |
| TASK-009 | Add a new helper in `src/tools/query_catalog.py` named `low_sampled_statistics_query(top_n: int) -> str` that returns stats with low `rows_sampled` relative to `rows`, ordered by weakest sampling ratio. |  |  |
| TASK-010 | Add a new helper in `src/tools/query_catalog.py` named `database_statistics_settings_query() -> str` that returns `AUTO_CREATE_STATISTICS`, `AUTO_UPDATE_STATISTICS`, and `AUTO_UPDATE_STATISTICS_ASYNC` settings for the selected database. |  |  |
| TASK-011 | Add a new helper in `src/tools/query_catalog.py` named `missing_statistics_coverage_candidate_query(top_n: int) -> str` that identifies user tables with no non-hypothetical stats entries or otherwise minimal stats coverage, clearly labeled as heuristic. |  |  |
| TASK-012 | Add a new helper in `src/tools/query_catalog.py` named `statistics_histogram_query(schema_name: str, table_name: str, stat_name: str) -> str` or an equivalent safe wrapper strategy for opt-in histogram inspection. |  |  |

### Implementation Phase 3

- GOAL-003: Extend `analyze_tab_health` orchestration and output composition in `src/tools/sql_tools.py`.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-013 | Update the `_analyze_tab_health` handler in `src/tools/sql_tools.py` to accept `include_statistics`, `include_histogram_analysis`, and `histogram_top_n` with deterministic validation. |  |  |
| TASK-014 | Execute statistics helper queries in `_analyze_tab_health` when `include_statistics=True`, alongside the existing table-size, fragmentation, and missing-primary-key queries. |  |  |
| TASK-015 | Apply `schema_name` and `table_name` filtering consistently to statistics rows before generating findings and recommendations. |  |  |
| TASK-016 | Add high-severity or medium-severity findings for stale statistics when thresholds indicate materially outdated stats on large or heavily modified objects. |  |  |
| TASK-017 | Add findings for never-updated statistics and low-sampled statistics, including rationales that explain optimizer risk. |  |  |
| TASK-018 | Add a finding when database statistics settings show `AUTO_CREATE_STATISTICS` or `AUTO_UPDATE_STATISTICS` disabled for the analyzed database. |  |  |
| TASK-019 | Add a heuristic finding for missing statistics coverage candidates, clearly labeled as metadata-based and not execution-plan-verified. |  |  |
| TASK-020 | Add histogram-based findings only when `include_histogram_analysis=True`, limited to the top candidate stats rows from the stale or low-sampled sets. |  |  |
| TASK-021 | Ensure histogram evidence is summarized safely, for example by bucket counts, skew indicators, or step-density warnings, rather than dumping full sensitive histogram payloads unnecessarily. |  |  |
| TASK-022 | Extend the tool summary in `build_report_envelope` inputs to include `stale_statistics_count`, `never_updated_statistics_count`, `low_sampled_statistics_count`, `database_statistics_settings`, and `statistics_preview`. |  |  |

### Implementation Phase 4

- GOAL-004: Generate recommendations that are specific, actionable, and still read-only.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-023 | For stale statistics findings, add recommendations such as `Update statistics for the identified objects during a maintenance window` with rationale tied to `modification_counter` and row volume. |  |  |
| TASK-024 | For never-updated statistics findings, add recommendations to review auto stats creation and update the identified stats if the objects are active. |  |  |
| TASK-025 | For low-sampled statistics findings, add recommendations to consider fullscan or higher-quality sampling during planned maintenance for critical objects. |  |  |
| TASK-026 | For disabled auto-create or auto-update database settings, add configuration review recommendations that explain optimizer and maintenance risk. |  |  |
| TASK-027 | For histogram-based skew findings, add recommendations to refresh statistics and review workload patterns rather than attempting direct tool-side remediation. |  |  |

### Implementation Phase 5

- GOAL-005: Add deterministic unit coverage and refresh documentation.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-028 | Extend `tests/test_advanced_analysis_tools.py` with structural tests for all new query helpers in `src/tools/query_catalog.py`. |  |  |
| TASK-029 | Add unit tests in `tests/test_advanced_analysis_tools.py` that validate new finding-code generation and recommendation text for stale, never-updated, and low-sampled statistics scenarios using fabricated result sets. |  |  |
| TASK-030 | Add tests that verify `schema_name` and `table_name` filters are applied consistently to statistics-related findings. |  |  |
| TASK-031 | Add tests that verify histogram analysis remains disabled by default and executes only when explicitly requested. |  |  |
| TASK-032 | Update `docs/mcp-tool-catalog.md` to describe the new statistics-related behavior and any new input parameters for `db_<instance #>_sql2019_analyze_tab_health`. |  |  |
| TASK-033 | Update `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` to document new output highlights such as stale statistics, database stats settings, and optional histogram-derived recommendations. |  |  |

### Implementation Phase 6

- GOAL-006: Validate safety, performance bounds, and rollout readiness.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-034 | Validate that all added SQL remains read-only and does not require write privileges beyond existing read diagnostics assumptions. |  |  |
| TASK-035 | Validate that statistics analysis respects the existing `top_n` cap and that histogram analysis uses a smaller capped `histogram_top_n` to avoid expensive calls. |  |  |
| TASK-036 | Validate that no new evidence payload leaks sensitive values or excessively verbose histogram detail. |  |  |
| TASK-037 | Run `ruff check .` and `pytest -q` after implementation and fix any issues specific to the new statistics analysis feature. |  |  |

## 3. Alternatives

- **ALT-001**: Add statistics findings to a new separate tool instead of extending `analyze_tab_health`. Not chosen because users already expect table and index health checks to be centralized in this tool.
- **ALT-002**: Implement execution-plan-based missing statistics analysis. Not chosen because it increases privilege requirements, complexity, and nondeterminism compared with metadata-driven analysis.
- **ALT-003**: Implement histogram analysis by default for all candidate statistics. Not chosen because it increases query cost and response size; optional bounded analysis is safer.
- **ALT-004**: Recommend and execute `UPDATE STATISTICS` directly from the tool. Not chosen because it violates the current read-only diagnostic posture.

## 4. Dependencies

- **DEP-001**: Existing `analyze_tab_health` handler in `src/tools/sql_tools.py`.
- **DEP-002**: Existing statistics helper `stale_statistics_query(top_n)` in `src/tools/query_catalog.py`.
- **DEP-003**: Existing analysis envelope helpers in `src/tools/analysis_contracts.py`.
- **DEP-004**: Existing input validation utilities in `src/tools/input_validation.py`.
- **DEP-005**: Existing unit coverage scaffold in `tests/test_advanced_analysis_tools.py`.
- **DEP-006**: SQL Server metadata objects `sys.stats`, `sys.dm_db_stats_properties`, and optional histogram inspection primitives supported by the target SQL Server version.

## 5. Files

- **FILE-001**: `plan/feature-analyze-tab-health-statistics-1.md` - This implementation plan.
- **FILE-002**: `src/tools/sql_tools.py` - Extend `_analyze_tab_health` orchestration, inputs, findings, and summary output.
- **FILE-003**: `src/tools/query_catalog.py` - Add or extend statistics-focused metadata query helpers.
- **FILE-004**: `tests/test_advanced_analysis_tools.py` - Add structural and behavior tests for statistics analysis.
- **FILE-005**: `docs/mcp-tool-catalog.md` - Document added statistics analysis behavior and new tool parameters.
- **FILE-006**: `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` - Update purpose, inputs, and output highlights for the enhanced tool.

## 6. Testing

- **TEST-001**: Verify the tool still returns the existing fragmented-index and missing-primary-key findings.
- **TEST-002**: Verify stale statistics rows produce the correct finding code, severity, and recommendation.
- **TEST-003**: Verify never-updated statistics rows produce the correct finding code and recommendation.
- **TEST-004**: Verify low-sampled statistics rows produce the correct finding code and recommendation.
- **TEST-005**: Verify disabled auto-create or auto-update settings produce configuration findings.
- **TEST-006**: Verify histogram analysis is opt-in and does not execute when `include_histogram_analysis=False`.
- **TEST-007**: Verify `schema_name` and `table_name` filters apply consistently to statistics-related evidence and counts.
- **TEST-008**: Verify the report summary includes new statistics counts and preview fields.
- **TEST-009**: Verify all new SQL helper generators are structurally correct and bounded by `top_n` or `histogram_top_n`.

## 7. Risks & Assumptions

- **RISK-001**: SQL Server metadata can identify stale and poorly maintained statistics, but cannot perfectly infer optimizer-impacting missing statistics without deeper workload context.
- **RISK-002**: Histogram analysis can become expensive or noisy if not tightly bounded to a small candidate set.
- **RISK-003**: The concept of "missing statistics" is partially heuristic when based only on catalog metadata.
- **RISK-004**: Adding too many findings to `analyze_tab_health` may dilute the signal of the most important issues unless summary ranking is clear.
- **ASSUMPTION-001**: The SQL login used by this tool has sufficient read access to `sys.stats` and `sys.dm_db_stats_properties` in the selected database.
- **ASSUMPTION-002**: Optional histogram inspection can be implemented with read-only SQL supported by the target SQL Server environment.
- **ASSUMPTION-003**: Users prefer recommendations that identify maintenance actions without having the tool execute those actions.

## 8. Related Specifications / Further Reading

- `src/tools/sql_tools.py`
- `src/tools/query_catalog.py`
- `tests/test_advanced_analysis_tools.py`
- `docs/mcp-tool-catalog.md`
- `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md`