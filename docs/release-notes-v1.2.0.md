# Release Notes - v1.2.0

Release date: 2026-05-09

## Highlights

- Interactive sessions dashboard support for FastMCP clients with HTML payloads and URL-backed retrieval.
- CMMI-aligned requirements traceability automation in GitHub workflows.
- Security hardening and policy enforcement improvements for controlled write execution.
- Operational documentation improvements and explicit MIT licensing.

## New Features

- Added interactive sessions dashboard tooling and delivery path:
  - Session activity and lock-chain visualization payloads.
  - URL-backed dashboard page retrieval with expiry behavior.
  - Expanded dashboard and analysis test coverage.
- Added CMMI-oriented automation:
  - PR traceability checks in CI.
  - Scheduled traceability matrix generation.

## Fixes and Improvements

- Workflow reliability and traceability:
  - Added missing `reopened` PR trigger handling for traceability checks.
  - Clarified traceability failure guidance for PR authors.
  - Hardened traceability matrix workflow execution and commit flow.
- Analysis and runtime robustness:
  - Added pagination and stronger error handling to traceability matrix generation script.
  - Fixed duplicate-safe column normalization behavior in DB connection handling.
  - Added request ID format validation for diagnostics dashboard endpoints and storage.
  - Added head-blocker count tracking in dashboard table output.
  - Ensured exception paths consistently mark decision outcome as `deny` in SQL tools.
- Documentation and repository hygiene:
  - Added direct runbook links in README.
  - Added MIT LICENSE file and updated README license section.

## Test and Quality Status

- Unit test suite passing: `116 passed`.

## Compatibility Notes

- FastMCP 3 + FastAPI runtime for SQL Server 2019 dual-instance operation remains the baseline.
- No new controlled-write tools were introduced in this release.