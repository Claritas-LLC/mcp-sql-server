# Release Notes - v1.3.0

Release date: 2026-05-09

## Highlights

- Added bounded SQL connection pooling with runtime diagnostics.
- Added Azure Entra token verification and group-based read/write authorization controls.
- Extended audit and diagnostics surfaces for auth posture and pool observability.
- Completed rollout evidence package and runbook updates for safe enable/rollback operations.

## New Features

- Added SQL connection pooling in runtime path:
  - Per-instance pooled connections with configured cap and acquire timeout.
  - Connection reuse and discard tracking with deterministic pool cleanup on shutdown.
  - Pool diagnostics endpoint at `/diagnostics/pool`.
- Added Azure Entra authentication and authorization primitives:
  - Azure OpenID discovery + JWKS token verification provider.
  - Configurable required scopes and claim extraction.
  - Group-based privilege mapping (`read`, `write`, `none`) with precedence and toggle support.
- Added authorization enforcement across MCP tools:
  - Read privilege required for read/analysis/dashboard tools.
  - Write privilege required for controlled procedure execution tools.

## Fixes and Improvements

- Security and policy controls:
  - Enabled controlled-write policy path on secondary via allowlist and flags.
  - Preserved deny-by-default write model while layering Entra authz checks.
- Diagnostics and observability:
  - Added `/diagnostics/security` auth posture summary fields.
  - Added auth context fields to audit events (`auth_mode`, `auth_subject`, `privilege_level`, `group_match_result`).
- Configuration and docs:
  - Added auth and pool override parsing in config loader.
  - Updated runtime/example configs with pool and auth scaffold fields.
  - Added access-model reference and expanded runbook rollout/rollback guidance.

## Test and Quality Status

- Full regression suite passing: `143 passed`.
- Added focused coverage for:
  - pool lifecycle and metrics
  - Azure token verification behavior
  - group privilege resolution
  - tool-level authorization behavior
  - diagnostics security/pool payload shape

## Evidence Artifacts

- `testing/artifacts/phase5-entra-pooling-summary.md`
- `testing/artifacts/diagnostics-sample-payloads.md`

## Compatibility Notes

- FastMCP 3 + FastAPI runtime for SQL Server 2019 dual-instance operation remains the baseline.
- Default auth posture remains disabled until explicitly enabled in runtime policy.
- Controlled-write remains constrained to allowlisted procedures.
