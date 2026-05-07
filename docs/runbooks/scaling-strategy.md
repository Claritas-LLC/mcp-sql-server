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
