# Security Maintenance Runbook

## Weekly

- Verify secret freshness for both SQL instances and rotate on schedule.
- Review denied-write and failed-auth trends from `/var/log/mcp/audit.log`.
- Confirm diagnostics security checksum matches expected policy revision.
- Review `/diagnostics/security` auth posture summary and confirm expected `auth_mode`, required scopes, and group counts.

## Monthly

- Review allowlist/denylist and remove stale privileged entries.
- Validate Azure Entra configuration when enabled:
  - Confirm `azure_auth_enabled` matches intended deployment state.
  - Confirm configured read/write group IDs still map to the correct operator groups.
  - Verify required scopes still match the app registration exposure.
- **Review procedure allowlist** (`allowed_tools.{tool_name}.allowed_procedures` in runtime-policy.yaml):
  - Audit each approved procedure for unexpected DML/DDL operations.
  - Remove procedures no longer required by operational workflows.
  - Document business justification for each approved procedure in a separate registry.
  - Verify procedures are not proxies to other unapproved procedures.
- Validate rate-limit thresholds against observed traffic patterns.
- Reconcile actor identity mappings used for quota enforcement.

## Quarterly

- Run access recertification for SQL credentials used by MCP.
- Execute dual-instance failover simulation (`primary` disabled, then `secondary` disabled).
- Validate SIEM forwarding and immutable retention controls.

## Annual

- Conduct disaster recovery exercise with rollback and restore verification.
- Review compliance controls mapping and update evidence checklist.

## Entra Rollback

If Entra token verification or group authorization causes an access outage:

1. Set `auth.azure_auth_enabled: false` in [config/runtime-policy.yaml](config/runtime-policy.yaml) and restart the service to return to non-Entra mode.
2. If token validation should remain enabled but group mapping is the issue, set `auth.azure_group_authorization_enabled: false` and restart the service.
3. Verify recovery using `/diagnostics/health` and `/diagnostics/security`.
4. Review recent audit entries for `AUTH_FAILED` decisions before re-enabling auth controls.
