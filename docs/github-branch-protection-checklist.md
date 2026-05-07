# GitHub Branch Protection Checklist

Use this checklist to configure branch protection (or a ruleset) for master.

## Target Branch

- Branch name pattern: master

## Required Pull Request Controls

- Require a pull request before merging
- Require approvals: at least 1
- Dismiss stale approvals when new commits are pushed
- Require conversation resolution before merging

## Required Status Checks

- Require status checks to pass before merging
- Require branches to be up to date before merging
- Required checks:
  - ci / lint-test-build

## Merge and History Controls

- Require linear history (optional but recommended)
- Do not allow force pushes
- Do not allow deletions

## Commit Integrity

- Require signed commits (recommended)

## Admin and Bypass Policy

- Apply protections to administrators
- Restrict bypass lists to minimum required maintainers

## Release and Tag Controls

- Protect release tags (v*)
- Restrict who can create/update protected tags

## Security Integrations

- Enable Dependabot alerts
- Enable Dependabot security updates
- Enable secret scanning
- Enable push protection for secrets
- Enable code scanning alerts (if available)

## Operational Guidance

- Review rules quarterly
- Audit bypass usage monthly
- Keep CODEOWNERS aligned with team ownership
