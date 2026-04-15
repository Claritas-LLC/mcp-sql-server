# Security Controls Inventory

## Repository-Defined Controls

- Dependabot config: `.github/dependabot.yml`
- CodeQL workflow: `.github/workflows/codeql.yml`
- Secret scanning workflow: `.github/workflows/secret-scan.yml`
- Security policy: `SECURITY.md`

## GitHub Settings (Manual)

Enable and verify in repository settings:

- Dependency graph: Enabled
- Dependabot alerts: Enabled
- Dependabot security updates: Enabled
- Secret scanning alerts: Enabled (if available for repository visibility tier)
- Push protection: Enabled (if available)

## Branch Protection Baseline

Apply to default branch:

- Require pull request before merging
- Require at least 1 approval
- Require status checks to pass before merging
- Require conversation resolution before merging
- Dismiss stale approvals on new commits
- Restrict force pushes
- Restrict branch deletion
