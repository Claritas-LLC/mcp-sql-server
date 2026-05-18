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

1. Create timestamped backups before making changes.

```powershell
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item config/runtime-policy.yaml "config/runtime-policy.yaml.bak-$ts"
Copy-Item policy/sql-allowlist.yaml "policy/sql-allowlist.yaml.bak-$ts"
```

2. Edit `config/runtime-policy.yaml`.
3. Optionally update `policy/sql-allowlist.yaml` to keep review metadata in sync.
4. Validate YAML syntax before applying the change (before restart).

```powershell
python -c "import pathlib, yaml; [yaml.safe_load(pathlib.Path(p).read_text(encoding='utf-8')) for p in ['config/runtime-policy.yaml','policy/sql-allowlist.yaml']]; print('YAML OK')"
```

5. Restart the runtime container so policy is reloaded.

Note: restarting `mcp-sqlserver` causes brief service disruption (short unavailability and dropped in-flight connections).

```powershell
docker compose -f docker/docker-compose.runtime.yml restart mcp-sqlserver
```

6. Validate diagnostics:

- `http://localhost:8085/diagnostics/health`
- `http://localhost:8085/diagnostics/security`

7. Execute a smoke test against an allowlisted procedure using `db_primary_sql2019_exec_proc`.
8. If apply fails, roll back and restart:

```powershell
Copy-Item "config/runtime-policy.yaml.bak-<timestamp>" config/runtime-policy.yaml -Force
Copy-Item "policy/sql-allowlist.yaml.bak-<timestamp>" policy/sql-allowlist.yaml -Force
docker compose -f docker/docker-compose.runtime.yml restart mcp-sqlserver
```

After rollback, run diagnostics (`/diagnostics/health`, `/diagnostics/security`) and the same `db_primary_sql2019_exec_proc` smoke test again.

## Update Procedure (Local Python Runtime)

1. Create a timestamped backup before making changes.

```powershell
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item config/runtime-policy.yaml "config/runtime-policy.yaml.bak-$ts"
```

2. Edit `config/runtime-policy.yaml`.
3. Validate YAML syntax before applying the change (before restart).

```powershell
python -c "import pathlib, yaml; yaml.safe_load(pathlib.Path('config/runtime-policy.yaml').read_text(encoding='utf-8')); print('YAML OK')"
```

4. Restart the process.

```powershell
python -m src.server
```

5. Run diagnostics and smoke tests with your MCP client:

- `http://localhost:8085/diagnostics/health`
- `http://localhost:8085/diagnostics/security`
- `db_primary_sql2019_exec_proc` allowlisted-procedure smoke test

6. If apply fails, roll back by restoring the backup and restarting:

```powershell
Copy-Item "config/runtime-policy.yaml.bak-<timestamp>" config/runtime-policy.yaml -Force
python -m src.server
```

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