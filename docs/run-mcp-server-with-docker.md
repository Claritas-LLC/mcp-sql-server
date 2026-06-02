# Run MCP Server with Docker

## Files

- `.env.example` -> copy to `.env`
- `config/instances.runtime.example.yaml` -> copy values into `config/instances.yaml`
- `docker/docker-compose.runtime.yml` -> runtime compose file
- `config/runtime-policy.yaml` -> authoritative runtime policy for controlled-write tools
- `policy/sql-allowlist.yaml` -> review/reference mirror of approved procedures (not runtime enforced)

## Steps

1. Copy `.env.example` to `.env` and set SQL credentials.
2. Update `config/instances.yaml` using `config/instances.runtime.example.yaml` as the template.
3. Start the server (Redis is included by default in the runtime compose file):

```powershell
docker compose -f docker/docker-compose.runtime.yml up -d
```

4. Verify service health:

- `http://localhost:8085/`
- `http://localhost:8085/diagnostics/health`
- `http://localhost:8085/diagnostics/security`

5. Verify active rate-limit backend and Redis URL from inside the container:

```powershell
docker exec mcp-sqlserver printenv FASTMCP_RATE_LIMIT_BACKEND
docker exec mcp-sqlserver printenv FASTMCP_REDIS_URL
```

Expected values for Redis-backed runtime:

- `FASTMCP_RATE_LIMIT_BACKEND=redis`
- `FASTMCP_REDIS_URL=redis://mcp-sqlserver-redis:6379`

## Important Notes

- The container listens on port `8080`; host port is mapped to `8085`.
- Use `host.docker.internal` instead of `localhost` when the SQL Server runs on the Docker host.
- Credential env vars must match the `auth_secret_ref` names in `config/instances.yaml`.
- Runtime compose uses `env_file: ../.env`; keep Redis/auth variables in `.env` for deterministic startup.

## MCP Streamable HTTP Call Pattern

When invoking tools directly over HTTP, use MCP initialize + session headers.

1. Send `initialize` with:
   - `Accept: application/json, text/event-stream`
2. Read `Mcp-Session-Id` from response headers.
3. Send tool calls with the same `Mcp-Session-Id` header.

Example (PowerShell):

```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$headers = @{
  'Accept' = 'application/json, text/event-stream'
  'Content-Type' = 'application/json'
}

$initBody = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"debug","version":"1.0"}}}'
$init = Invoke-WebRequest -Uri 'http://localhost:8085/mcp/' -Method Post -Body $initBody -Headers $headers -WebSession $session
$sid = $init.Headers['Mcp-Session-Id']

$callHeaders = @{
  'Accept' = 'application/json, text/event-stream'
  'Content-Type' = 'application/json'
  'Mcp-Session-Id' = $sid
}

$callBody = '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"db_2_sql2019_top_statements","arguments":{"database_name":"master","top_n":5,"lookback_minutes":60,"view_mode":"FULL","actor":"demo"}}}'
Invoke-WebRequest -Uri 'http://localhost:8085/mcp/' -Method Post -Body $callBody -Headers $callHeaders -WebSession $session
```

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

### SQL Permission Requirement

Policy allowlisting and SQL permissions are separate gates. After allowlisting a procedure, ensure the SQL login used by MCP has EXECUTE permission on that procedure (or on a tightly scoped approved schema).

Example:

```sql
GRANT EXECUTE ON OBJECT::USGISPRO_800.dbo.usp_CaptureProcOutput TO [mcp_service_login];
```

Without this grant, SQL Server can still return permission errors (for example, error 229) even when runtime policy allows the call.

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
