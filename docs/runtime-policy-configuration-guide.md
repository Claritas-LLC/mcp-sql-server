# Runtime Policy Configuration Guide

This guide explains how controlled-write policy is configured, which files are authoritative, and how to safely apply and validate policy changes.

## Source of Truth

- Runtime-enforced policy: `config/runtime-policy.yaml`
- Reference mirror for review/evidence: `policy/sql-allowlist.yaml`

The service enforces `config/runtime-policy.yaml` via `FASTMCP_POLICY_PATH`.

## YAML File Roles

- `config/runtime-policy.yaml`: write-mode default, allowed write tools, blocked SQL patterns, per-tool allowed procedures, and tool/instance enablement flags.
- `config/instances.yaml`: SQL instance connectivity and pool settings.
- `config/instances.runtime.example.yaml`: template for runtime instances configuration.
- `config/rate-limit.yaml`: actor/global/session rate limit settings.
- `config/runtime-policy-entra-example.yaml`: Entra-oriented policy/auth example.
- `policy/sql-denylist.yaml`: shared denylist reference.
- `policy/sql-allowlist.yaml`: mirrored list of approved stored procedures for review and traceability.

## Runtime Enforcement Order

1. Tool auth/authorization and actor checks.
2. Tool and instance enablement checks.
3. Write policy gate (`write_mode_default`, `allowed_write_tools`, denylist patterns).
4. Procedure allowlist validation in `allowed_tools.<tool>.allowed_procedures`.
5. SQL Server permission check (EXECUTE rights for MCP login).
6. Execution and audit/metrics logging.

## Update Procedure (Docker)

1. Edit `config/runtime-policy.yaml`.
2. Optionally update `policy/sql-allowlist.yaml` to keep review metadata in sync.
3. Restart the runtime container so policy is reloaded.

```powershell
docker compose -f docker/docker-compose.runtime.yml restart mcp-sqlserver
```

4. Validate diagnostics:

- `http://localhost:8085/diagnostics/health`
- `http://localhost:8085/diagnostics/security`

5. Execute a smoke test against an allowlisted procedure using `db_primary_sql2019_exec_proc`.

## Update Procedure (Local Python Runtime)

1. Edit `config/runtime-policy.yaml`.
2. Restart the process.

```powershell
python -m src.server
```

3. Run smoke tests with your MCP client.

## Demonstration Example (Non-Production)

The following example uses `write_mode_default: allow` only for demonstration or isolated test environments.

```yaml
write_mode_default: allow
allowed_write_tools:
  - db_primary_sql2019_exec_proc
allowed_tools:
  db_primary_sql2019_exec_proc:
    allowed_procedures:
      - USGISPRO_800.dbo.usp_CaptureProcOutput
```

After applying this config and restarting, call `db_primary_sql2019_exec_proc` with:

- `proc_name: USGISPRO_800.dbo.usp_CaptureProcOutput`

Expected result includes:

- `status: ok`
- `procedure`
- `rowcount`
- `has_result_set`
- `columns`
- `rows`

## Production Guidance

Use a deny-by-default posture in production:

```yaml
write_mode_default: deny
allowed_write_tools:
  - db_primary_sql2019_exec_proc
  - db_secondary_sql2019_exec_proc
allowed_tools:
  db_primary_sql2019_exec_proc:
    allowed_procedures:
      - dbo.usp_RunApprovedMaintenance
```

Keep procedure lists explicit and minimal.

## SQL Server Permission Requirement

Policy allowlisting does not grant SQL rights. Ensure the SQL login used by MCP has EXECUTE permission for each approved procedure (or a tightly scoped approved schema).

```sql
GRANT EXECUTE ON OBJECT::dbo.usp_RunApprovedMaintenance TO [mcp_service_login];
```

If this permission is missing, SQL Server can still reject calls even when policy allows them.