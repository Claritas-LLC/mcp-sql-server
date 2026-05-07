# Contributing

Thanks for contributing to MCP SQL Server.

## Development Setup

1. Use Python 3.11+.
2. Create and activate a virtual environment.
3. Install dependencies:

```powershell
pip install -e .[dev]
```

## Branching

- Create feature branches from master.
- Keep commits focused and descriptive.
- Open pull requests for all non-trivial changes.

## Quality Gates

Before opening a pull request, run:

```powershell
ruff check .
pytest -q
```

## Pull Request Guidance

- Describe the change and motivation.
- Include security impact if applicable.
- Include test evidence (command + result summary).
- Update docs when behavior or configuration changes.

## MCP-Specific Expectations

- Maintain strict input validation on all tools.
- Preserve deterministic error contract patterns.
- Keep write operations explicitly controlled by policy.
- Ensure sensitive fields are redacted in outputs and logs.

## Commit Style

Prefer concise, imperative commit subjects. Example:

- feat: add index health analysis guardrails
- fix: handle missing FastMCP http_app in type-checking context

## Security Reporting

Do not open a public issue for exploitable vulnerabilities.
Use the process in SECURITY.md.
