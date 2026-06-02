# Disaster Recovery and Rollback

## Scope

This runbook covers service-level recovery for the MCP server and rollback to a known-good release.

## Recovery Objectives

- Target RTO: 30 minutes
- Target RPO: Configuration-level only (service does not own SQL data persistence)

## Disaster Scenarios

1. Failed rollout causing service outage.
2. Authentication outage (token validation or group mapping).
3. SQL connectivity outage to one or both instances.
4. Redis outage affecting distributed rate limiting.

## Recovery Procedure

1. Declare incident and open incident channel.
2. Freeze non-essential changes.
3. Validate current state:
   - `/diagnostics/health`
   - `/diagnostics/security`
   - `/diagnostics/pool`
4. Choose mitigation path:
   - Rollback image
   - Rollback policy/config
   - Temporary auth simplification (as approved)

## Rollback Procedure

1. Redeploy previously stable image tag.
2. Restore approved runtime policy backup if policy change caused incident.
3. Restart service/revision.
4. Validate:
   - diagnostics endpoints
   - MCP initialize + session tool call
   - `db_1_sql2019_ping` and `db_2_sql2019_ping`

## Redis Degradation Strategy

If Redis backend fails and multi-replica consistency is not required temporarily:

1. Switch `FASTMCP_RATE_LIMIT_BACKEND` to `local`.
2. Restart affected service.
3. Track temporary risk: per-replica rate-limit counters become independent.
4. Restore Redis backend after service recovery.

## Post-Recovery Tasks

1. Confirm monitoring and alerts are normal.
2. Publish incident summary and timeline.
3. Create corrective actions for root cause.
