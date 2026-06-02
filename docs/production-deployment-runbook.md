# Production Deployment Runbook

## Trigger

Use this runbook for production rollout of a new MCP SQL Server image/config revision.

## Preconditions

- Deployment window approved.
- Prior stable image tag available.
- Runtime policy reviewed and approved.
- SQL and Entra secrets verified in Key Vault (or equivalent secret store).
- [Observability and alerting baseline](observability-and-alerting-baseline.md) established: health probes, core alerts, and dashboard panels confirmed operational.
- Backup of current runtime configuration created and verified.
- Rollback procedure tested in a non-production environment.
- On-call owner assigned and familiar with rollback steps.

## Inputs

- Target environment: `prod`
- Image tag: `<new-tag>`
- Rollback image tag: `<previous-tag>`
- Service URL: `https://<fqdn>`

## Deployment Steps

1. Confirm prerequisites from [DEPLOYMENT-CHECKLIST.md](DEPLOYMENT-CHECKLIST.md).
2. Deploy image `<new-tag>`.
3. Wait for healthy revision and traffic readiness.
4. Validate diagnostics endpoints:
   - `GET /diagnostics/health`
   - `GET /diagnostics/security`
5. Validate instance connectivity for each configured SQL instance:
   - Pattern: `db_<instance_number>_sql2019_ping` (e.g., `db_1_sql2019_ping`, `db_2_sql2019_ping`)
   - Rule: every instance returned in the initial `tools/list` response must be pingable
6. Validate MCP streamable transport session flow:
   - Send `initialize` with `Accept: application/json, text/event-stream`
   - Capture `Mcp-Session-Id`
   - Call `tools/list` with that session ID
7. Execute smoke tool checks:
   - one read/report tool
   - one analysis tool
   - one dashboard tool
8. Confirm audit log write path and rate-limit behavior.

## Validation Criteria

- All endpoints return successful responses.
- No sustained auth failures in logs.
- No SQL pool saturation or repeated connection failures.
- MCP tool calls complete without session/accept errors.

## Rollback

Trigger rollback immediately if any of the following occur:

- Health checks fail for more than 5 minutes.
- MCP session handshake repeatedly fails.
- SQL connectivity fails on either instance.
- Unauthorized access behavior deviates from policy.

Rollback steps:

1. Redeploy `<previous-tag>`.
2. Re-run diagnostics checks.
3. Re-run MCP initialize + tools/list flow.
4. Document incident timeline and root cause.

## Escalation

- Primary: Platform on-call
- Secondary: DBA on-call
- Security escalation: Security engineering on-call
