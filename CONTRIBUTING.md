# Contributing Guide

## Branch Naming

Use short-lived branches from the default branch:

- `feature/<short-description>`
- `fix/<short-description>`
- `chore/<short-description>`

Examples:

- `feature/add-query-audit-summary`
- `fix/sessions-monitor-instance-validation`
- `chore/update-ci-workflow`

## Commit Message Style

Use Conventional Commits:

- `feat: add data model report persistence`
- `fix: handle invalid instance in sessions monitor`
- `chore: update dependency pins`

Guidelines:

- Keep commits atomic (one logical change per commit).
- Use imperative mood.
- Avoid vague messages such as `update` or `fixed stuff`.

## Pull Request Process

1. Rebase your branch on the latest default branch.
2. Run local checks before opening a PR:

```powershell
.\.venv\Scripts\Activate.ps1
python -m py_compile mcp_sqlserver\server.py
pytest -q
```

3. Open a PR using the repository template.
4. Provide clear test evidence in the PR description.

## Coding Standards

- Preserve existing public tool signatures unless change is required and documented.
- Keep security controls intact (`MCP_ALLOW_WRITE`, auth settings, audit settings).
- Avoid introducing secrets into code, tests, logs, or docs.

## Reporting Issues

Use the issue templates for bugs and feature requests. Include reproducible steps and expected behavior.
