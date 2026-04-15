# Commit History Guidelines

## Objectives

- Keep history readable and auditable
- Preserve intent of each change
- Reduce regressions by keeping commits atomic

## Standards

- One commit should represent one logical change.
- Commit messages must use Conventional Commits.
- Include context in commit body for non-obvious changes.
- Rebase feature branches on default branch before opening PR.

## Good Examples

- `feat: add pull request template for quality gates`
- `fix: return 400 for invalid sessions monitor instance`
- `docs: document docker startup command`

## Prohibited Patterns

- `fixed stuff`
- `update`
- Large mixed commits touching unrelated concerns

## Suggested Local Workflow

1. Create a small branch-specific change set.
2. Run local verification:
   - `python -m py_compile mcp_sqlserver/server.py`
   - `pytest -q`
3. Commit using Conventional Commits.
4. Push and open PR.
