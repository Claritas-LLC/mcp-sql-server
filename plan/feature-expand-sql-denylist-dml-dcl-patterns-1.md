---
goal: Expand SQL denylist to block DML (INSERT, UPDATE, DELETE, MERGE) and DCL (GRANT, REVOKE, DENY) commands for all tools while preserving controlled-write exec_proc path
version: 1.0
date_created: 2026-06-10
last_updated: 2026-06-10
owner: MCP SQL Server Team
status: Implemented
tags: [feature, security, denylist, dml, dcl, sql-server, fastmcp, controlled-write]
---

# Introduction

![Status: Implemented](https://img.shields.io/badge/status-Implemented-green)

This plan expands the SQL denylist regex patterns to block **DML** commands (INSERT, UPDATE, DELETE, MERGE) and **DCL** commands (GRANT, REVOKE, DENY) for all tools, reinforcing the server read-only posture. Currently, only DDL patterns (DROP, ALTER, TRUNCATE, CREATE) and dangerous system procedures (xp_cmdshell, sp_oacreate) are in the denylist. DML verbs are only blocked via the verb-based write check, which only applies to non-allowlisted tools. Adding these patterns to the regex denylist provides defense-in-depth.

The exec_proc controlled-write path is preserved by changing its internal probe from UPDATE __policy_probe__ SET x = 1 to EXEC __policy_probe__, which still tests write-permission membership without containing DML/DCL keywords.

## Background: Current Enforcement Layers

The WriteGuard.enforce() method in src/middleware/write_guard.py has two sequential checks:

| Layer | Scope | Mechanism | Current blocked patterns |
|-------|-------|-----------|--------------------------|
| Regex denylist | All tools (including allowlisted) | re.compile(pattern).search(sql) | DROP, ALTER, TRUNCATE, CREATE, xp_cmdshell, sp_oacreate |
| Verb-based write check | Non-allowlisted tools only | _first_verb(sql) in {INSERT, UPDATE, DELETE, MERGE, EXEC, EXECUTE, CREATE, ALTER, DROP, TRUNCATE} | Blocks write verbs unless tool is in allowed_write_tools |

The gap: INSERT, UPDATE, DELETE, MERGE, GRANT, REVOKE, DENY are NOT in the regex denylist.

## 1. Requirements and Constraints

- REQ-001: Add INSERT, UPDATE, DELETE, MERGE, GRANT, REVOKE, and DENY to the blocked SQL patterns in both policy/sql-denylist.yaml and config/runtime-policy.yaml.
- REQ-002: The exec_proc controlled-write tool must continue to function after the denylist expansion.
- REQ-003: The dual-source configuration (YAML denylist file + runtime-policy.yaml) must remain in sync.
- REQ-004: All existing tests in tests/test_write_restrictions.py must pass after changes.
- SEC-001: Regex patterns must use word-boundary matching to avoid false positives.
- SEC-002: The exec_proc path must still pass through enforce() to validate the tool is in allowed_write_tools.
- CON-001: Do not modify validate_procedure() or the procedure allowlist flow.
- CON-002: Do not change _first_verb() or the verb-based write check logic.

## 2. Implementation Steps

### Implementation Phase 1: Update Configuration Files

- GOAL-001: Add DML and DCL patterns to both denylist configuration sources.

| Task     | Description           | Completed | Date       |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Update policy/sql-denylist.yaml: add INSERT, UPDATE, DELETE, MERGE, GRANT, REVOKE, DENY as individual patterns after CREATE and before xp_cmdshell. | ✅ | 2026-06-10 |
| TASK-002 | Update config/runtime-policy.yaml blocked_sql_patterns: expand the combined DDL regex to include all new keywords. | ✅ | 2026-06-10 |

### Implementation Phase 2: Fix exec_proc Probe

- GOAL-002: Change the exec_proc write-permission probe to use EXEC instead of UPDATE.

| Task     | Description           | Completed | Date       |
| -------- | --------------------- | --------- | ---------- |
| TASK-003 | In src/tools/sql_tools.py at line 1311, change the probe string from UPDATE __policy_probe__ SET x = 1 to EXEC __policy_probe__. | ✅ | 2026-06-10 |

### Implementation Phase 3: Update Tests

- GOAL-003: Add test coverage for all newly blocked DML/DCL patterns.

| Task     | Description           | Completed | Date       |
| -------- | --------------------- | --------- | ---------- |
| TASK-004 | In tests/test_write_restrictions.py, update _guard() fixture with expanded denylist regex. | ✅ | 2026-06-10 |
| TASK-005 | Add parametrized test test_denies_dml_dcl_patterns for all 7 new keywords. | ✅ | 2026-06-10 |
| TASK-006 | Update test_denies_ddl_pattern to verify DDL still blocked. | ✅ | 2026-06-10 |
| TASK-007 | Add test_exec_proc_probe_uses_exec_not_update for the new EXEC-based probe. | ✅ | 2026-06-10 |
| TASK-008 | Add regression test test_write_probe_with_update_is_blocked. | ✅ | 2026-06-10 |
| TASK-009 | Update test_allows_allowlisted_write_tool to use EXEC pattern. | ✅ | 2026-06-10 |
| TASK-010 | Add test_false_positives_avoided for word-boundary matching. | ✅ | 2026-06-10 |

### Implementation Phase 4: Validation

- GOAL-004: Run linting and full test suite.

| Task     | Description           | Completed | Date       |
| -------- | --------------------- | --------- | ---------- |
| TASK-011 | Run ruff check . and fix any issues. | ✅ | 2026-06-10 |
| TASK-012 | Run pytest -q and verify all tests pass. | ✅ | 2026-06-10 |
| TASK-013 | Run targeted write-guard tests. | ✅ | 2026-06-10 |

## 3. Alternatives

- ALT-001: Split enforce() into two methods. Rejected: adds API surface; probe change is simpler.
- ALT-002: Add skip_denylist parameter to enforce(). Rejected: weakens security contract.
- ALT-003: Keep DML/DCL only in verb check. Rejected: user requires regex denylist for defense-in-depth.

## 4. Dependencies

- DEP-001: src/middleware/write_guard.py — the enforce() method; no changes needed.
- DEP-002: src/tools/sql_tools.py — exec_proc tool at line 1310; probe change only.
- DEP-003: src/models.py — RuntimePolicy.blocked_sql_patterns; no changes needed.
- DEP-004: config/runtime-policy.yaml and policy/sql-denylist.yaml — both updated in sync.

## 5. Files

- FILE-001: policy/sql-denylist.yaml — Add 7 new patterns (lines 1-6).
- FILE-002: config/runtime-policy.yaml — Expand combined regex in blocked_sql_patterns (line 7).
- FILE-003: src/tools/sql_tools.py — Change exec_proc probe at line 1311.
- FILE-004: tests/test_write_restrictions.py — Update fixture and add tests (lines 1-50).

## 6. Testing

- TEST-001: Each new keyword blocked by denylist for all tools including exec_proc.
- TEST-002: exec_proc tool functions with new EXEC __policy_probe__ probe.
- TEST-003: Old UPDATE-based probe correctly blocked (regression guard).
- TEST-004: Existing DDL denylist behavior preserved.
- TEST-005: False positives avoided for identifiers containing blocked keywords as substrings.
- TEST-006: Full test suite (pytest -q) passes with zero regressions.
- TEST-007: ruff check . passes with zero issues.

## 7. Risks and Assumptions

- RISK-001: Other code paths passing DML/DCL SQL through enforce() will break. Mitigation: audited all 10 call sites; only exec_proc passes DML SQL.
- RISK-002: Future allowed procedures with blocked-keyword names would be blocked. Mitigation: validate procedure names at allowlist-registration time.
- ASSUMPTION-001: exec_proc probe only needs write-permission test, not denylist pass-through.
- ASSUMPTION-002: Word-boundary matching correctly distinguishes keywords from identifier substrings.

## 8. Related Specifications

- docs/access-levels-and-controlled-write.md
- docs/mcp-tool-catalog.md
- config/runtime-policy.yaml
- policy/sql-denylist.yaml
