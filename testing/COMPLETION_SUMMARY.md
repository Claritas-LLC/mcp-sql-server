# MCP SQL Server - Dual-Instance Scope Refactor Completion Summary

**Date:** May 1, 2026  
**Status:** COMPLETE AND VALIDATED

---

## What Was Completed

### 1. Scoped Database Execution

- Added database-scoped execution through `EXEC [db].sys.sp_executesql ...` in the shared execution helper.
- Preserved identifier validation and bound-parameter execution.
- Kept the direct path for operations that intentionally remain on the instance-default database.

### 2. Tool Path Migration

Updated the affected dual-instance execution paths so target-database work no longer depends on raw session-level `USE` switching.

This includes:

- list and schema metadata paths
- query execution paths
- logical model, fragmentation, index health, table health, and stats paths
- write-path helpers for create/alter/drop object and create/drop user flows

### 3. Pooling Preservation

- pools remain keyed by instance
- target database switching moved into SQL execution instead of pool keys
- replacement direct connections still use the instance-default database when the pool is exhausted

### 4. Dual-Instance Harness Updates

- instance 1 now targets `test1`
- instance 2 now targets `test2`
- matrix generation and serial execution artifacts were updated to validate suffix pairs in deterministic order
- per-pair artifacts are written and reread before the next suffix proceeds

---

## Validation Evidence

### Focused Regression Tests

Command:

```text
python -m pytest tests/test_execute_in_database.py tests/test_run_query_internal.py tests/test_get_connection_retry_cleanup.py -q
```

Outcome:

- 10 passed
- 0 failed

### HTTP Blackbox Tests

Recorded in [testing/blackbox_results.txt](testing/blackbox_results.txt)

Outcome:

- 2 passed
- 0 failed

### End-to-End Dual-Instance Run

Recorded in [testing/tool_execution_summary.json](testing/tool_execution_summary.json)

Outcome:

- total tools: 50
- passed: 50
- failed: 0
- halted suffix: null

### Artifact Audit

Evidence location: [testing/tool_results](testing/tool_results)

Outcome:

- all final suffix pairs report `SUCCESS`
- final pair summaries have zero `validation_errors`
- raw artifacts attribute results to `test1` and `test2`
- no open defects remain in [testing/defect_register.json](testing/defect_register.json)

---

## Final Assessment

The dual-instance database-scope refactor is complete. The implementation now uses scoped `sp_executesql` for named-database work, preserves instance-local pooling, and has passing focused regression, blackbox, and end-to-end validation evidence.

**Release decision:** Ready for deployment.
