# Repository Audit Checklist

## Requirements Validation

- [x] REQ-001 Preserve runtime behavior while adding governance files
- [x] REQ-002 Add metadata and contribution guidance files
- [x] REQ-003 Standardize branching/PR/commit workflows in docs/templates
- [x] REQ-004 Add CI workflow with lint/syntax/tests and Docker build check
- [x] REQ-005 Add dependency and security scanning configuration

## Security Validation

- [x] SEC-001 `.env` and local secrets ignored in `.gitignore`
- [ ] SEC-002 Branch protection enabled in GitHub UI

## Constraint Validation

- [x] CON-001 Repository not renamed by plan execution
- [x] CON-002 Free/native GitHub features used where possible

## Manual Post-merge Checklist

- [ ] Configure branch protection rules in GitHub settings
- [ ] Enable dependency graph and Dependabot alerts
- [ ] Enable secret scanning and push protection (if available)
- [ ] Apply repository topics in GitHub UI
- [ ] Optionally automate labels from `.github/labels.yml`
