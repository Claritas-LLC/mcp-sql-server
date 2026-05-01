# MCP SQL Server - Dual-Instance Database Scope Test Report
**Date:** May 1, 2026  
**Version:** v2.0  
**Status:** COMPLETE

---

## Executive Summary

The dual-instance database-scope refactor is complete. Named-database execution now runs through database-scoped `EXEC [db].sys.sp_executesql ...` from stable per-instance pooled sessions, and the current validation set is green.

**Overall Status:** READY FOR DEPLOYMENT

---

## Scope Completed

- Centralized target-database execution in `_execute_in_database()`.
- Replaced ad hoc `USE [database]` switching in the affected tool paths.
- Preserved instance-local connection pooling semantics.
- Updated the dual-instance harness to validate `test1` on instance 1 and `test2` on instance 2.
- Added focused unit coverage for scoped execution and pooling behavior.

---

## Validation Results

### 1. Narrow Regression Suite

Command run:

```text
python -m pytest tests/test_execute_in_database.py tests/test_run_query_internal.py tests/test_get_connection_retry_cleanup.py -q
```

Result:

- 10 tests passed
- 0 failed

Covered behaviors:

- `_execute_in_database()` emits `EXEC [db].sys.sp_executesql ...`
- positional `?` parameters are rewritten to deterministic `@p1`, `@p2`, ... placeholders
- literal question marks inside strings are preserved
- invalid database identifiers are rejected before execution
- `_run_query_internal()` routes named-database execution through the scoped helper
- pool exhaustion still falls back to an instance-default direct connection without changing pool keying

### 2. HTTP Blackbox Validation

Command previously recorded in [testing/blackbox_results.txt](testing/blackbox_results.txt):

```text
pytest tests/test_blackbox_http.py -q
```

Result:

- 2 tests passed
- 0 failed

### 3. Dual-Instance End-to-End Validation

Evidence file: [testing/tool_execution_summary.json](testing/tool_execution_summary.json)

Result:

- Total tools executed: 50
- Passed: 50
- Failed: 0
- Halted suffix: null

Execution model validated:

- `db_01_*` tools ran against database `test1`
- `db_02_*` tools ran against database `test2`
- each logical suffix pair completed serially with artifact rereads and no validation errors

### 4. Artifact Review

Evidence directory: [testing/tool_results](testing/tool_results)

Validated outcomes:

- per-tool raw artifacts exist for both instances
- per-suffix pair summaries exist for the final run
- final pair summaries record zero `validation_errors`
- final artifacts attribute results to `test1` and `test2` rather than a shared `TEST_DB`

---

## Implementation Notes

### Execution Model

- database identifiers continue to pass through existing validation before interpolation
- SQL text remains parameterized through `pyodbc`
- `sp_executesql` parameter declarations are generated deterministically from bound Python values
- write and read tool paths both use the shared scoped execution helper where appropriate

### Pooling Behavior

- pools remain keyed by instance, not by database name
- pooled sessions are reused within an instance even when executing against multiple databases via scoped SQL
- fallback direct connections continue to use the instance-default database when the pool is exhausted

### Dual-Instance Mapping

- instance 1 -> `test1`
- instance 2 -> `test2`

---

## Open Defects

Current defect register: [testing/defect_register.json](testing/defect_register.json)

- No open defects recorded

---

## Deployment Readiness

- [x] Scoped database execution implemented
- [x] Affected tool paths migrated
- [x] Focused unit regressions passing
- [x] HTTP blackbox checks passing
- [x] Dual-instance end-to-end run passing
- [x] Artifact audit clean
- [x] No open defects remaining

**Recommendation:** The dual-instance database-scope change set is complete and validated for release.
