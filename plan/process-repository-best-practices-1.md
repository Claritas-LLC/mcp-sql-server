---
goal: Implement GitHub repository best practices for mcp-sql-server
version: 1.0
date_created: 2026-04-15
last_updated: 2026-04-15
owner: Repository Maintainers
status: In progress
tags: [process, repository, github, governance, security]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

This plan defines deterministic steps to align this repository with GitHub repository best practices across naming, metadata, documentation, branching, protections, commit hygiene, ignore rules, CI/CD, project tracking, and security automation.

## 1. Requirements & Constraints

- **REQ-001**: Preserve repository runtime behavior while introducing governance and automation files.
- **REQ-002**: Add missing repository metadata and contribution guidance files.
- **REQ-003**: Standardize branch, pull request, and commit workflows using documented rules.
- **REQ-004**: Add CI workflows that validate code and container build health on pull requests.
- **REQ-005**: Configure security scanning and dependency updates through GitHub-native features.
- **SEC-001**: Do not commit secrets, credentials, or environment files containing sensitive values.
- **SEC-002**: Enforce branch protection requirements on the default branch.
- **OPS-001**: Keep all automation deterministic and executable with repository-local files.
- **CON-001**: Do not rename the repository in this plan because rename requires owner-level coordination.
- **CON-002**: Do not require paid GitHub features unless an equivalent free feature is unavailable.
- **GUD-001**: Prefer repository configuration-as-code under `.github/` whenever supported.
- **PAT-001**: Use small, atomic pull requests and Conventional Commit messages for all plan tasks.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Establish repository metadata and contribution baseline.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Create `README.md` with sections: Overview, Features, Prerequisites, Local Setup, Docker Run, Environment Variables, MCP Endpoints, Troubleshooting, and License. Include exact commands that work for Windows PowerShell. | ✅ | 2026-04-15 |
| TASK-002 | Create `LICENSE` using MIT template or organization-required license text. | ✅ | 2026-04-15 |
| TASK-003 | Create `CONTRIBUTING.md` with branch naming (`feature/*`, `fix/*`, `chore/*`), PR checklist, coding standards, and test expectations. | ✅ | 2026-04-15 |
| TASK-004 | Create `CODE_OF_CONDUCT.md` using Contributor Covenant v2.1 text. | ✅ | 2026-04-15 |
| TASK-005 | Create `.github/ISSUE_TEMPLATE/bug_report.yml` and `.github/ISSUE_TEMPLATE/feature_request.yml` with required fields for reproducibility and acceptance criteria. | ✅ | 2026-04-15 |
| TASK-006 | Create `.github/pull_request_template.md` with sections: Summary, Scope, Test Evidence, Breaking Changes, and Security Impact. | ✅ | 2026-04-15 |

### Implementation Phase 2

- GOAL-002: Implement branch strategy, commit hygiene, and ignore policy enforcement.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-007 | Document default branching strategy in `docs/repository-governance.md`: protected `master` (or `main` after migration), short-lived topic branches, squash merge policy, and hotfix flow. | ✅ | 2026-04-15 |
| TASK-008 | Add commit message policy to `docs/repository-governance.md` using Conventional Commits format with examples (`feat:`, `fix:`, `chore:`). | ✅ | 2026-04-15 |
| TASK-009 | Add `.editorconfig` to normalize line endings, encoding, trailing whitespace, and indentation for `*.py`, `*.md`, and `*.yml`. | ✅ | 2026-04-15 |
| TASK-010 | Review and update `.gitignore` to include Python caches, venv, logs, test artifacts, local env files, and editor caches while preserving required runtime files. | ✅ | 2026-04-15 |
| TASK-011 | Add `.gitattributes` to enforce text normalization and mark binary patterns if present. | ✅ | 2026-04-15 |
| TASK-012 | Create `docs/commit-history-guidelines.md` with rules for atomic commits, rebasing before merge, and prohibited vague commit messages. | ✅ | 2026-04-15 |

### Implementation Phase 3

- GOAL-003: Add CI/CD quality gates and deterministic validation workflows.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-013 | Create `.github/workflows/ci.yml` with triggers on `pull_request` and `push` to default branch; jobs: Python setup, dependency install, lint (`ruff` if configured), syntax check (`python -m py_compile mcp_sqlserver/server.py`), and tests (`pytest -q`). | ✅ | 2026-04-15 |
| TASK-014 | Extend `.github/workflows/ci.yml` with Docker build validation job: `docker build -t mcp-sql-server:ci .` without push. | ✅ | 2026-04-15 |
| TASK-015 | Create `.github/workflows/release-image.yml` with manual trigger (`workflow_dispatch`) and guarded push to Docker Hub using repository secrets for credentials. | ✅ | 2026-04-15 |
| TASK-016 | Add status badges for CI workflow to `README.md` once workflow filenames are final. | ✅ | 2026-04-15 |
| TASK-017 | Add `docs/runbook-ci.md` documenting workflow purpose, failure triage, and rerun procedure. | ✅ | 2026-04-15 |

### Implementation Phase 4

- GOAL-004: Enable repository security best practices and dependency hygiene.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-018 | Create `.github/dependabot.yml` for weekly updates of `pip` and `github-actions` ecosystems with scoped directories and PR labels. | ✅ | 2026-04-15 |
| TASK-019 | Create `.github/workflows/codeql.yml` for Python analysis on pull requests and weekly schedule. | ✅ | 2026-04-15 |
| TASK-020 | Create `.github/workflows/secret-scan.yml` using `gitleaks` (or equivalent) on pull requests and pushes to default branch. | ✅ | 2026-04-15 |
| TASK-021 | Add `SECURITY.md` with vulnerability reporting channel, disclosure expectations, and response timeline targets. | ✅ | 2026-04-15 |
| TASK-022 | Enable GitHub settings manually: dependency graph, Dependabot alerts, secret scanning alerts, and push protection; record enabled state in `docs/security-controls.md`. |  |  |

### Implementation Phase 5

- GOAL-005: Standardize issue/project tracking and finalize governance controls.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-023 | Create `.github/labels.yml` manifest (or equivalent script) defining standard labels: `bug`, `enhancement`, `documentation`, `security`, `infra`, `needs-triage`, `good-first-issue`. | ✅ | 2026-04-15 |
| TASK-024 | Create `docs/project-tracking.md` defining issue states, board columns, SLA targets, and milestone usage rules. | ✅ | 2026-04-15 |
| TASK-025 | Configure branch protection for default branch: require PR, require 1+ approval, require all CI checks, dismiss stale approvals, block force push, block deletion, and require resolved conversations. |  |  |
| TASK-026 | Configure repository topics in GitHub UI to include: `mcp`, `python`, `sql-server`, `fastmcp`, `docker`, and document final set in `docs/repository-metadata.md`. |  |  |
| TASK-027 | Run final verification checklist in `docs/repository-audit-checklist.md` and record pass/fail for every REQ/SEC/CON item in this plan. | ✅ | 2026-04-15 |

## 3. Alternatives

- **ALT-001**: Apply only `.gitignore` and CI changes, skipping governance docs. Rejected because contributor onboarding and process consistency remain weak.
- **ALT-002**: Use only GitHub UI settings without versioned files. Rejected because configuration drift cannot be reviewed through pull requests.
- **ALT-003**: Add third-party SaaS for all security checks. Rejected because GitHub-native features cover required controls with lower operational overhead.

## 4. Dependencies

- **DEP-001**: GitHub repository admin access for branch protection, topics, and security settings.
- **DEP-002**: GitHub Actions runner support for Docker build steps.
- **DEP-003**: Existing Python project dependencies from `requirements.txt` for CI test execution.
- **DEP-004**: Docker Hub repository and secrets (`DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`) for image publishing workflow.

## 5. Files

- **FILE-001**: README.md - repository overview and usage documentation.
- **FILE-002**: LICENSE - legal licensing terms.
- **FILE-003**: CONTRIBUTING.md - contribution process and standards.
- **FILE-004**: CODE_OF_CONDUCT.md - contributor behavior policy.
- **FILE-005**: SECURITY.md - vulnerability disclosure process.
- **FILE-006**: .gitignore - ignore policy for local/generated artifacts.
- **FILE-007**: .editorconfig - editor normalization settings.
- **FILE-008**: .gitattributes - text and binary handling policy.
- **FILE-009**: .github/pull_request_template.md - PR quality checklist.
- **FILE-010**: .github/ISSUE_TEMPLATE/bug_report.yml - structured bug intake.
- **FILE-011**: .github/ISSUE_TEMPLATE/feature_request.yml - structured feature intake.
- **FILE-012**: .github/workflows/ci.yml - CI quality gates.
- **FILE-013**: .github/workflows/release-image.yml - controlled Docker release workflow.
- **FILE-014**: .github/workflows/codeql.yml - static security analysis workflow.
- **FILE-015**: .github/workflows/secret-scan.yml - secret scanning workflow.
- **FILE-016**: .github/dependabot.yml - automated dependency updates.
- **FILE-017**: docs/repository-governance.md - branch and commit rules.
- **FILE-018**: docs/commit-history-guidelines.md - commit history standards.
- **FILE-019**: docs/security-controls.md - enabled security control inventory.
- **FILE-020**: docs/project-tracking.md - issue/project process.
- **FILE-021**: docs/repository-metadata.md - naming/topics metadata record.
- **FILE-022**: docs/repository-audit-checklist.md - final compliance checklist.

## 6. Testing

- **TEST-001**: Run CI workflow on a test pull request and confirm all required checks pass.
- **TEST-002**: Validate issue templates and PR template render correctly in GitHub UI.
- **TEST-003**: Open a simulated vulnerability report path and verify SECURITY.md instructions are actionable.
- **TEST-004**: Trigger Dependabot config validation by creating a branch with malformed then corrected `.github/dependabot.yml` and confirm parse success.
- **TEST-005**: Push a synthetic secret in a disposable branch to verify secret scan workflow alerts and block policy behavior.
- **TEST-006**: Verify branch protection blocks direct push to default branch and enforces mandatory checks.
- **TEST-007**: Confirm `.gitignore` excludes local caches, test outputs, and `.env` while tracking required runtime files.

## 7. Risks & Assumptions

- **RISK-001**: Overly strict branch protections can slow urgent hotfixes if emergency bypass is undefined.
- **RISK-002**: CI runtime can increase due to Docker build and security scans, affecting contributor cycle time.
- **RISK-003**: Missing or misconfigured repository secrets can break release workflow.
- **RISK-004**: Dependabot PR volume can create review fatigue without batching policies.
- **ASSUMPTION-001**: Maintainers have admin permissions to apply repository-level settings.
- **ASSUMPTION-002**: Current test suite is stable enough to serve as a required branch check.
- **ASSUMPTION-003**: The repository will continue using Python and Docker as primary runtime technologies.

## 8. Related Specifications / Further Reading

[GitHub Repository Best Practices - Marcel.L](https://dev.to/pwd9000/github-repository-best-practices-23ck)
[GitHub Docs - Setting up your project for healthy contributions](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions)
[GitHub Docs - About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/defining-the-mergeability-of-pull-requests/about-protected-branches)
[GitHub Docs - GitHub Actions](https://docs.github.com/en/actions)
[GitHub Docs - Code security](https://docs.github.com/en/code-security)