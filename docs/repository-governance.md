# Repository Governance

## Branching Strategy

Default branch policy:

- Protected default branch: `master` (migrate to `main` when maintainers schedule rename)
- No direct pushes to protected branch
- All changes land through pull requests
- Use squash merge as default merge method

Working branch model:

- `feature/<short-description>` for new capabilities
- `fix/<short-description>` for defects
- `chore/<short-description>` for maintenance and tooling updates

Hotfix flow:

1. Create `fix/<hotfix-description>` from default branch.
2. Implement minimal corrective change.
3. Open expedited PR with mandatory review and CI checks.
4. Squash merge to default branch.

## Pull Request Rules

- At least one reviewer approval before merge
- Required checks must pass before merge
- Conversations must be resolved before merge
- Keep PR scope focused and small when possible

## Commit Message Policy

Use Conventional Commits:

- `feat: add instance-aware health endpoint`
- `fix: handle missing report id parameter`
- `chore: add issue templates`
- `docs: update local run instructions`

Rules:

- First line should be concise and descriptive
- One logical change per commit
- Avoid vague messages (`update`, `misc`, `fix stuff`)
