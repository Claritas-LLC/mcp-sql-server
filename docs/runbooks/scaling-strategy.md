# Scaling Strategy

## Vertical Scaling Triggers

- CPU above 70% for 15 minutes.
- Memory pressure with frequent GC pauses or OOM risk.
- Connection pool saturation above 80% for sustained periods.

## Horizontal Scaling Triggers

- Sustained request volume above 900 rpm.
- P95 latency above SLO after tuning pool and SQL plans.
- Rate-limit rejections due to global pressure rather than abusive actors.

## Horizontal Pattern

- Run multiple FastMCP replicas behind a reverse proxy.
- Use shared rate-limit storage (Redis or equivalent) for consistent enforcement.
- Keep audit output centralized using log forwarding sidecar/agent.

## Database-Side Considerations

- Maintain index health and statistics update cadence.
- Separate reporting-heavy operations to secondary instance where possible.
- Limit result sets and enforce command timeout ceilings from policy.

## Interactive App Architecture (FastMCPApp)

The Sessions Dashboard is delivered as a **FastMCPApp** — an interactive front end running inside the MCP server process:

| Concern | Detail |
|---|---|
| **Entry tool** | `db_{instance_number}_sql2019_sessions_dashboard` — the MCP tool an LLM calls to get a dashboard URL. |
| **App backend** | `fetch_sessions_dashboard_data` (app-tool) — executes all four DMV queries and populates state. |
| **State model** | `DASHBOARD_STATE_SCHEMA` in `src/tools/dashboard_payloads.py` — validated sections: `sessions`, `locks`, `blockers`, `blocking_chains`, `head_blockers`, `recommendations`, `ui_meta`. |
| **Page delivery** | Generated pages are retrievable at `/diagnostics/dashboards/{request_id}` via in-memory TTL-backed storage. |
| **Registration** | `register_sessions_dashboard_app_provider(mcp, state)` called once in `server.py`. |
| **Scaling note** | FastMCPApp state is per-process. Under horizontal scaling, each replica maintains its own live state; there is no shared app state needed because queries are stateless DMV snapshots. |

## Docker Runtime Validation

To validate the full server stack (including interactive app routing) using the runtime Docker Compose:

```powershell
# Start stack
docker compose -f docker/docker-compose.runtime.yml up -d

# Confirm FastMCP app route is served
Invoke-WebRequest -Uri http://localhost:8085/diagnostics/health | Select-Object -ExpandProperty StatusCode

# Stop stack
docker compose -f docker/docker-compose.runtime.yml down
```

Expected: HTTP 200 on `/diagnostics/health`. The dashboard URL is returned in the `dashboard_url` field of the `db_{instance_number}_sql2019_sessions_dashboard` tool response and is served by `/diagnostics/dashboards/{request_id}` until TTL expiry.
