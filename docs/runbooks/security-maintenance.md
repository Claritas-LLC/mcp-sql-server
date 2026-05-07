# Security Maintenance Runbook

## Weekly

- Verify secret freshness for both SQL instances and rotate on schedule.
- Review denied-write and failed-auth trends from `/var/log/mcp/audit.log`.
- Confirm diagnostics security checksum matches expected policy revision.

## Monthly

- Review allowlist/denylist and remove stale privileged entries.
- Validate rate-limit thresholds against observed traffic patterns.
- Reconcile actor identity mappings used for quota enforcement.

## Quarterly

- Run access recertification for SQL credentials used by MCP.
- Execute dual-instance failover simulation (`primary` disabled, then `secondary` disabled).
- Validate SIEM forwarding and immutable retention controls.

## Annual

- Conduct disaster recovery exercise with rollback and restore verification.
- Review compliance controls mapping and update evidence checklist.
