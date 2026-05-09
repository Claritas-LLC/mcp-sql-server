# MCP SQL Server

Remote FastMCP server for dual SQL Server 2019 instances with strong read-only controls, rate limiting, and diagnostics.

## What This Repository Provides

- FastMCP + FastAPI service exposing SQL tools over HTTP at /mcp
- Dual-instance SQL Server 2019 support (primary and secondary)
- Read-only SQL policy controls with denylist and allowlist config
- Redis or local rate limiting with per-actor and global limits
- Security-oriented output handling (sensitive field redaction)
- Diagnostics endpoints for runtime posture and tool usage
- Docker runtime and compose files for local and remote operation

## Repository Structure

- src: service runtime, tool registration, middleware, diagnostics
- config: instance config, policy, and rate-limit settings
- policy: SQL allowlist and denylist definitions
- docker: Dockerfile and compose files
- tests: unit tests
- testing: integration and operational test harnesses
- docs: tool catalog, runbooks, and run instructions
- docs/runbooks/scaling-strategy.md: runbook for scaling and load-validation operations
- docs/runbooks/security-maintenance.md: runbook for security posture checks and maintenance

## Quick Start (Local)

1. Create and activate a Python 3.11+ virtual environment.
2. Install dependencies:

```powershell
pip install -e .[dev]
```

3. Copy environment and config templates:

```powershell
Copy-Item .env.example .env
```

4. Configure instances in config/instances.yaml.
5. Run the service:

```powershell
python -m src.server
```

6. Validate endpoints:

- http://localhost:8080/
- http://localhost:8080/diagnostics/health
- http://localhost:8080/diagnostics/security

## Docker Runtime

Use the runtime compose flow documented in docs/run-mcp-server-with-docker.md.

```powershell
docker compose -f docker/docker-compose.runtime.yml up -d
```

## Operational Runbooks

- [Scaling strategy](docs/runbooks/scaling-strategy.md) - guidance for dashboard scaling and load validation.
- [Security maintenance](docs/runbooks/security-maintenance.md) - maintenance checks for security posture and operational hygiene.

## Testing

Run unit tests:

```powershell
pytest -q
```

## Security Notes

- Do not commit real secrets.
- Keep .env local only.
- Prefer least-privilege SQL credentials.
- See SECURITY.md for reporting and hardening guidance.

## Contributing

See CONTRIBUTING.md for branch, PR, and test expectations.

## Release and CI

- CI runs on pull requests and pushes to master/main.
- Release tags follow v* (example: v1.2).

## CMMI-Oriented Platform Integration

This repository includes GitHub-native process controls aligned to CMMI implementation patterns:

- Requirements management: requirement issue template and PR traceability sections
- Configuration management: branch protection, CODEOWNERS, signed commits, and protected release tags
- Verification and validation: CI checks, PR gates, and traceability check workflow
- Measurement and analysis: scheduled traceability matrix generation
- Audit trail: issue/PR history, commit history, and workflow logs retained in GitHub

Artifacts:

- .github/ISSUE_TEMPLATE/requirement.yml
- .github/workflows/traceability-check.yml
- .github/workflows/traceability-matrix.yml
- docs/traceability-matrix.md

## License

Licensed under the MIT License. See [LICENSE](LICENSE).
