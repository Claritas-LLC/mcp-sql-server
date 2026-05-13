# AGENTS

Guidance for AI coding agents working in this repository.

## Project Snapshot

- Python 3.11+ FastMCP + FastAPI service for dual SQL Server 2019 instances.
- Strong read-only posture with controlled-write guardrails, rate limiting, and diagnostics.
- Runtime entry point: [src/server.py](src/server.py).

## Fast Start

1. Create/activate a virtual environment.
2. Install dependencies:
   - `pip install -e .[dev]`
3. Run checks before proposing changes:
   - `ruff check .`
   - `pytest -q`

## Architecture Boundaries

- Service/bootstrap: [src/server.py](src/server.py), [src/config_loader.py](src/config_loader.py)
- SQL access and pooling: [src/db/](src/db)
- Security and policy enforcement: [src/middleware/](src/middleware), [src/security/](src/security)
- Tool contracts and registration: [src/tools/](src/tools)
- Diagnostics endpoints and summaries: [src/diagnostics/](src/diagnostics)

When adding features, keep changes inside the relevant boundary and avoid cross-cutting edits unless required.

## Non-Negotiable Guardrails

- Preserve read-only defaults and write controls:
  - Policy: [config/runtime-policy.yaml](config/runtime-policy.yaml)
  - Denylist: [policy/sql-denylist.yaml](policy/sql-denylist.yaml)
  - Allowlist: [policy/sql-allowlist.yaml](policy/sql-allowlist.yaml)
- Keep strict input validation for all tools and SQL-facing parameters.
- Never expose secrets or connection details in logs, diagnostics, or errors.
- Preserve deterministic error contracts and redaction behavior.
- Do not weaken audit logging or rate limiting paths.

## Change Workflow

1. Read nearby tests first in [tests/](tests).
2. Implement minimal, focused changes.
3. Add/update tests for behavior changes.
4. Run `ruff check .` and `pytest -q`.
5. Update docs if behavior/config changes.

## High-Value References

- Contribution process: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security policy/reporting: [SECURITY.md](SECURITY.md)
- Access model and controlled write: [docs/access-levels-and-controlled-write.md](docs/access-levels-and-controlled-write.md)
- Tool inventory/contracts: [docs/mcp-tool-catalog.md](docs/mcp-tool-catalog.md)
- Docker runtime: [docs/run-mcp-server-with-docker.md](docs/run-mcp-server-with-docker.md)
- Operational runbooks:
  - [docs/runbooks/security-maintenance.md](docs/runbooks/security-maintenance.md)
  - [docs/runbooks/scaling-strategy.md](docs/runbooks/scaling-strategy.md)

## Practical Pitfalls To Avoid

- Adding a SQL tool without validation/redaction test coverage.
- Introducing writes outside controlled-write policy and allowlist flow.
- Returning raw exception details that may leak sensitive runtime info.
- Breaking dual-instance behavior symmetry unintentionally.
