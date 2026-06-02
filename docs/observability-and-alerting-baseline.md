# Observability and Alerting Baseline

## Health Probes

- Liveness/readiness endpoints:
  - `GET /diagnostics/health`
  - `GET /diagnostics/security`
- Optional deep operational probe:
  - `GET /diagnostics/pool`

## Core SLO Indicators

- Availability: health endpoint success rate
- Latency: MCP tool request latency distribution
- Correctness: error-rate by tool and by instance
- Security: auth failure and denied-write trend stability

## Minimum Alerts

1. Health endpoint failure for >5 minutes.
2. Authentication failures above threshold for >10 minutes.
3. SQL connectivity failures on either instance for >5 minutes.
4. Rate-limit denial spike beyond expected baseline.
5. Pool saturation sustained above 80%.

## Required Log Fields

- `timestamp`
- `request_id`
- `tool`
- `instance`
- `actor`
- `decision`
- `latency_ms`
- `error_code`## Dashboard Minimum Panels

1. Request volume by tool.
2. Error count by error code.
3. P95/P99 latency by tool.
4. Denied vs allowed request ratio.
5. SQL instance availability (`ping` results).
