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
