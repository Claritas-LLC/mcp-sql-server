# CI Runbook

## Workflows

- `CI` (`.github/workflows/ci.yml`): lint, syntax check, tests, Docker build validation
- `CodeQL` (`.github/workflows/codeql.yml`): static security analysis
- `Secret Scan` (`.github/workflows/secret-scan.yml`): secret detection in commits
- `Release Docker Image` (`.github/workflows/release-image.yml`): manual image publish to Docker Hub

## Failure Triage

1. Open failed workflow run in GitHub Actions.
2. Identify failing job and step.
3. Reproduce locally:
   - `ruff check mcp_sqlserver`
   - `python -m py_compile mcp_sqlserver/server.py`
   - `pytest -q`
   - `docker build -t mcp-sql-server:ci .`
4. Fix on a topic branch and open PR.

## Re-run Policy

- Re-run failed jobs only after confirming no flaky external dependency caused the failure.
- Do not bypass required checks for normal feature/fix PRs.

## Release Workflow Requirements

- Repository secrets must exist:
  - `DOCKERHUB_USERNAME`
  - `DOCKERHUB_TOKEN`
- Use `workflow_dispatch` input `image_tag` to publish deterministic tags.
