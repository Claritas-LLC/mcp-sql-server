# Production Operations Runbook

## Daily Checks

1. Verify service and diagnostics endpoints are healthy.
2. Review error trends for:
   - auth failures
   - rate limit denials
   - SQL execution errors
3. Confirm both SQL instances remain reachable via `db_1_sql2019_ping` and `db_2_sql2019_ping`.
4. Confirm audit log output is present and current.

## Weekly Checks

1. Validate runtime policy controls are unchanged from approved baseline.
2. Review denied write attempts and procedure allowlist usage.
3. Validate rate-limit backend and Redis connectivity (if configured).

## Incident Triage

### A) MCP session/transport errors

- Symptom: client receives missing Accept/session errors.
- Actions:
  1. Confirm client sends `Accept: application/json, text/event-stream`.
  2. Confirm client performs `initialize` and sends `Mcp-Session-Id`.
  3. Verify no reverse proxy strips required headers.

### B) SQL connectivity issues

- Symptom: tool failures with connectivity errors.
- Actions:
  1. Run `db_1_sql2019_ping` and `db_2_sql2019_ping`.
  2. Check `/diagnostics/pool` for saturation and pool errors.
  3. Validate SQL host/network/firewall reachability.

### C) Authorization failures

- Symptom: unexpected `AUTH_FAILED` or privilege denials.
- Actions:
  1. Validate `/diagnostics/security` posture.
  2. Verify Entra scope and group claims mapping.
  3. Confirm runtime policy auth settings.

### D) Controlled-write denials

- Symptom: denied `exec_proc` requests.
- Actions:
  1. Confirm tool in `allowed_write_tools`.
  2. Confirm procedure in `allowed_tools.<tool>.allowed_procedures`.
  3. Confirm SQL EXECUTE permission exists.

## Operational Rollback

- Revert to prior image when incidents are release-induced.
- Revert runtime policy only through backup restore and restart procedure.
- Capture post-incident report with cause, mitigation, and prevention action.
