---
goal: Remove request_datetime_utc input parameter from execute_query tool and set view_mode default to COMPACT
version: 1.1
date_created: 2026-05-26
last_updated: 2026-05-26
owner: MCP SQL Server Team
status: Completed
tags: [feature, refactor, execute-query, api-change, sql-server]
---

# Introduction

This plan removes request_datetime_utc from the db_{instance_number}_sql2019_execute_query tool contract and sets view_mode to default to COMPACT when omitted. The implementation applies to both instance 1 and instance 2 because both are registered from the same tool factory loop.

## 1. Requirements and Constraints

- REQ-001: Remove request_datetime_utc from the _execute_query function signature.
- REQ-002: Remove request_datetime_utc from TOOL_INFO["execute_query"]["required_parameters"].
- REQ-003: Remove request_datetime_utc from execute_query output payload.
- REQ-004: Make view_mode optional with default "COMPACT".
- REQ-005: Move view_mode metadata from required_parameters to optional_parameters.
- REQ-006: Ensure behavior applies to both db_1_sql2019_execute_query and db_2_sql2019_execute_query.
- REQ-007: Update tool docstring for the new parameter contract.
- REQ-008: Update docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md examples and parameter table.
- CON-001: Keep FULL/COMPACT validation in place.
- CON-002: Do not alter write-guard, rate-limiting, session, audit, or redaction behavior.

## 2. Implementation Steps

### Phase 1: Source Code

- TASK-001 [x]: Update execute_query required_parameters to ["database_name", "sql_statement"].
- TASK-002 [x]: Update execute_query optional_parameters to ["actor", "view_mode"].
- TASK-003 [x]: Remove request_datetime_utc from execute_query output_fields metadata.
- TASK-004 [x]: Change _execute_query signature to remove request_datetime_utc and set view_mode: str = "COMPACT".
- TASK-005 [x]: Update execute_query docstring input bullets accordingly.
- TASK-006 [x]: Remove request_datetime_utc from returned output dict.
- TASK-007 [x]: Verify no remaining request_datetime_utc references in src/tools/sql_tools.py.

### Phase 2: Documentation

- TASK-008 [x]: In section 4.4 input parameters, remove request_datetime_utc and mark view_mode optional with COMPACT default.
- TASK-009 [x]: Verify output JSON sample does not include request_datetime_utc.
- TASK-010 [x]: Update list_tools example to required_parameters ["database_name", "sql_statement"] and optional_parameters ["actor", "view_mode"].

### Phase 3: Validation

- TASK-011 [x]: Run ruff check .
- TASK-012 [x]: Run pytest -q
- TASK-013 [x]: Confirm write restriction coverage remains intact (tool-name based tests still pass).
- TASK-014 [x]: Confirm default view_mode behavior and removed request_datetime_utc contract in code.

## 3. Alternatives

- ALT-001: Keep request_datetime_utc as optional. Rejected to simplify contract and remove redundant caller input.
- ALT-002: Default view_mode to FULL. Rejected due extra overhead; COMPACT is safer and cheaper default.
- ALT-003: Refactor to shared validate_view_mode helper. Rejected to keep this change set minimal.

## 4. Dependencies

- DEP-001: No external dependencies.
- DEP-002: No config or policy file changes.

## 5. Files Changed

- src/tools/sql_tools.py
- docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md

## 6. Validation Results

- ruff check . -> passed
- pytest -q -> 150 passed

## 7. Risks and Assumptions

- RISK-001: Clients still sending request_datetime_utc will need to remove that argument.
- RISK-002: Behavior changes for omitted view_mode now default to COMPACT.
- ASSUMPTION-001: No external in-repo callers depended on request_datetime_utc in tests or runtime wrappers.

## 8. Notes

- Dual-instance coverage is guaranteed by shared registration loop usage in src/tools/sql_tools.py.
