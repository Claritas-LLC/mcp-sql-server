# Release Notes — v1.4.0

**Date**: 2026-06-10

## Summary

Expanded the SQL denylist from 4 DDL patterns to 13 patterns covering DDL, DML, DCL, and system procedures, providing defense-in-depth for the server read-only posture.

## Changes

### Expanded SQL Denylist (Feature)

- Added 7 new regex denylist patterns: INSERT, UPDATE, DELETE, MERGE, GRANT, REVOKE, DENY
- The denylist now blocks 13 patterns total:
  - **DDL (4)**: DROP, ALTER, TRUNCATE, CREATE
  - **DML (4)**: INSERT, UPDATE, DELETE, MERGE
  - **DCL (3)**: GRANT, REVOKE, DENY
  - **System procedures (2)**: xp_cmdshell, sp_oacreate
- All patterns use word-boundary matching to avoid false positives on identifier substrings
- Denylist is enforced for ALL tools including allowlisted exec_proc
- DDL patterns were already in the denylist; DML/DCL were only in the verb-based write check (non-allowlisted tools only) — this change moves them to regex-level blocking for defense-in-depth

### Updated exec_proc Write-Permission Probe

- Changed the exec_proc internal probe from UPDATE __policy_probe__ SET x = 1 to EXEC __policy_probe__
- This preserves write-permission validation while avoiding the new DML denylist patterns
- EXEC is a write verb in the verb check but is intentionally absent from the regex denylist

### New Test Coverage

- 12 new test cases in test_write_restrictions.py:
  - Parametrized test for all 7 new DML/DCL keywords blocked for all tools
  - exec_proc EXEC-based probe test
  - UPDATE-based probe regression test
  - False-positive avoidance tests for keyword substrings in identifiers

## Files Changed

| File | Change |
|------|--------|
| policy/sql-denylist.yaml | +7 individual DML/DCL patterns |
| config/runtime-policy.yaml | Expanded combined regex to 11 keywords |
| src/tools/sql_tools.py | Probe UPDATE -> EXEC at line 1311 |
| tests/test_write_restrictions.py | Updated fixture, +12 test cases |
| plan/feature-expand-sql-denylist-dml-dcl-patterns-1.md | Implementation plan |
| docs/demo-narration-script.md | Updated denylist description |
| docs/access-levels-and-controlled-write.md | Expanded denylist section |
| docs/documentation-audit-2026-06-02.md | Updated audit status |

## Verification

- ruff check . — all checks passed
- pytest -q — 196/196 passed
- Docker image built and pushed to harryvaldez/mcp-sql-server:latest
- Container healthy, both SQL instances connected, Redis rate limiting operational
