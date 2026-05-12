# Run MCP Server with Docker

## Files

- `.env.example` -> copy to `.env`
- `config/instances.runtime.example.yaml` -> copy values into `config/instances.yaml`
- `docker/docker-compose.runtime.yml` -> runtime compose file

## Steps

1. Copy `.env.example` to `.env` and set SQL credentials.
2. Update `config/instances.yaml` using `config/instances.runtime.example.yaml` as the template.
3. Start the server:

```powershell
docker compose -f docker/docker-compose.runtime.yml up -d
```

4. Optional Redis-backed rate limiting:

```powershell
docker compose -f docker/docker-compose.runtime.yml --profile local-redis up -d
```

5. Verify:

- `http://localhost:8085/`
- `http://localhost:8085/diagnostics/health`
- `http://localhost:8085/diagnostics/security`

## Important Notes

- The container listens on port `8080`; host port is mapped to `8085`.
- Use `host.docker.internal` instead of `localhost` when the SQL Server runs on the Docker host.
- Credential env vars must match the `auth_secret_ref` names in `config/instances.yaml`.

## Procedure Execution Security (exec_proc Tool)

The `db_{instance_number}_sql2019_exec_proc` tool allows execution of **approved stored procedures only**. Procedure execution is governed by an allowlist defined in `config/runtime-policy.yaml` under the `allowed_tools` section.

### Configuring the Procedure Allowlist

Only procedures explicitly listed in the allowlist may be executed. By default, all procedures are **denied**:

```yaml
allowed_tools:
  db_primary_sql2019_exec_proc:
    allowed_procedures:
      - dbo.usp_RunApprovedMaintenance
      - dbo.usp_RefreshMaterializedView
  db_secondary_sql2019_exec_proc:
    allowed_procedures: []  # Empty = deny all on secondary
```

### Key Security Properties

- **Fail-safe default**: If a procedure is not in the allowlist, it is **denied**.
- **Case-insensitive**: Procedure names are matched case-insensitively per SQL Server convention.
- **Schema-qualified**: Both `dbo.usp_MyProc` and `usp_MyProc` formats are supported.
- **Per-tool isolation**: Each tool has its own independent allowlist.
- **Audit trail**: All procedure execution attempts (approved and denied) are logged with the decision.

### Example: Adding a Procedure to the Allowlist

1. Edit `config/runtime-policy.yaml`
2. Add the procedure to the appropriate tool's `allowed_procedures` list:

```yaml
allowed_tools:
  db_primary_sql2019_exec_proc:
    allowed_procedures:
      - dbo.usp_RunApprovedMaintenance
      - dbo.usp_RefreshMaterializedView
      - dbo.usp_MyNewProcedure  # <- Add here
```

3. Restart the container:

```powershell
docker compose -f docker/docker-compose.runtime.yml restart mcp-sqlserver
```

4. Test the execution via the MCP tool (Inspector or your client).

### Important: What This Does NOT Allow

- **DML/DDL statements**: Direct `CREATE`, `ALTER`, `DROP`, `TRUNCATE` are blocked by the denylist, regardless of the exec_proc allowlist.
- **Unsafe procedures**: The allowlist controls *which* procedures execute, but procedures that contain DML/DDL will execute those statements. Ensure approved procedures are audited for safety.
- **Unapproved procedures**: Any procedure not in the allowlist is rejected with a `PermissionError` before execution.



## Interactive App (Sessions Dashboard)

The Sessions Dashboard is exposed by `db_{instance_number}_sql2019_sessions_dashboard`. The tool call returns a `dashboard_url` that points to a generated webpage route hosted by the same service.

### Develop and test the app locally (without Docker)

```bash
# Install and launch with MCP Inspector (hot reload)
uv run mcp dev src/server.py
```

Then open the MCP Inspector at `http://localhost:5173` and call `db_1_sql2019_sessions_dashboard` (or `db_2_sql2019_sessions_dashboard`). The response includes `dashboard_url` and `request_id`.

### Test the app via the HTTP transport (Docker)

```powershell
# Start the server
docker compose -f docker/docker-compose.runtime.yml up -d

# Confirm the /mcp endpoint is available
Invoke-WebRequest -Uri http://localhost:8085/mcp -Method Get | Select-Object StatusCode
```

### Open generated dashboard link

After invoking `db_{instance_number}_sql2019_sessions_dashboard`, open the returned link:

```text
http://localhost:8085/diagnostics/dashboards/{request_id}
```

The page is TTL-backed in memory (default 15 minutes). Expired or unknown IDs return `404`.

### Session Dashboard tool parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `database_name` | string | `master` | Target database |
| `lookback_minutes` | int | 15 | History window for session data |
| `include_locks` | bool | true | Include `sys.dm_tran_locks` and `sys.dm_os_waiting_tasks` queries |
| `actor` | string | `system` | Actor ID used by audit/session/rate-limit middleware |

Use the hard-bound tool name for the instance you want:

- `db_1_sql2019_sessions_dashboard`
- `db_2_sql2019_sessions_dashboard`

### State sections returned

When `include_locks=true`, the tool response includes:

- **dashboard_url** — link to generated HTML page: `/diagnostics/dashboards/{request_id}`
- **request_id** — unique request key used by the dashboard route
- **expires_at_utc** — UTC expiration for the generated page

And the payload populates these state sections:

- **sessions** — `sys.dm_exec_sessions` + `sys.dm_exec_requests`
- **locks** — `sys.dm_tran_locks` (active lock holders)
- **blockers** — `sys.dm_os_waiting_tasks` (all waiting tasks)
- **blocking_chains** — blocked session rows from `sys.dm_exec_requests` where `blocking_session_id > 0`
- **head_blockers** — derived list of root blocking session IDs
- **recommendations** — auto-generated mitigation guidance
