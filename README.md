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

## Important Documentation

- [Tool catalog](docs/mcp-tool-catalog.md) - canonical list of exposed tools and contracts.
- [Access levels and controlled write](docs/access-levels-and-controlled-write.md) - authorization model and write guardrails.
- [Runtime policy configuration guide](docs/runtime-policy-configuration-guide.md) - authoritative policy workflow, YAML roles, and safe update steps.
- [Run with Docker](docs/run-mcp-server-with-docker.md) - local and remote Docker runtime instructions.
- [Azure Container Apps deployment](docs/azure-container-apps-deployment.md) - Azure deployment flow and operational guidance.
- [Deployment checklist](docs/DEPLOYMENT-CHECKLIST.md) - pre-deploy and post-deploy validation steps.
- [Security maintenance runbook](docs/runbooks/security-maintenance.md) - weekly/monthly/quarterly security operations.
- [Scaling strategy runbook](docs/runbooks/scaling-strategy.md) - scaling and load-validation operations.
- [Connectivity and diagnostics spec](docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md) - discovery and diagnostics behavior reference.
- [Security policy](SECURITY.md) - reporting and hardening policy.
- [Contributing guide](CONTRIBUTING.md) - branch, PR, and testing expectations.

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
- docs/access-levels-and-controlled-write.md: access model and controlled-write enforcement reference

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
- http://localhost:8080/diagnostics/pool

Primary rollout verification checks:

- `/diagnostics/health`: confirms service and instance connectivity.
- `/diagnostics/security`: confirms auth mode, required scope count, group-authorization posture, and registered tool inventory.
- `/diagnostics/pool`: confirms per-instance SQL pool sizing and reuse counters.

## Docker Runtime

Use the runtime compose flow documented in docs/run-mcp-server-with-docker.md.

Controlled-write policy is enforced from config/runtime-policy.yaml. The file policy/sql-allowlist.yaml is a review/reference mirror and is not loaded as a runtime policy source.

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

Current validation snapshot:

- Full test suite: `143 passed`
- See [testing/artifacts/phase5-entra-pooling-summary.md](testing/artifacts/phase5-entra-pooling-summary.md) for rollout verification notes.

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
- Latest release notes: [docs/release-notes-v1.3.0.md](docs/release-notes-v1.3.0.md)

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
