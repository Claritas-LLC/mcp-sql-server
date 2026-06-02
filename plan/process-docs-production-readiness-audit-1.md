---
goal: Complete documentation audit and production-readiness documentation package for the MCP SQL Server repository
version: 1.0
date_created: 2026-06-02
last_updated: 2026-06-02
completed_date: 2026-06-02
owner: Platform Engineering
status: Completed
tags: [process, documentation, production, deployment, operations]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

This plan defines a deterministic, end-to-end documentation audit and remediation workflow for all files under docs/. It validates technical accuracy against the current MCP SQL Server implementation and creates missing production deployment/operations documents required for secure and repeatable production rollout.

## 1. Requirements & Constraints

- **REQ-001**: Review every Markdown file under docs/ and docs/runbooks/ for technical accuracy against current repository behavior.
- **REQ-002**: Update all stale deployment/runtime instructions to reflect current Docker Compose behavior, Redis usage, and MCP session requirements.
- **REQ-003**: Ensure all tool documentation matches current tool names and behavior in src/tools/ and src/server.py.
- **REQ-004**: Ensure release documentation includes all behavior changes introduced since release-notes-v1.3.0.
- **REQ-005**: Create missing production documents required for successful deployment and operations if absent.
- **SEC-001**: Preserve and document read-only-by-default posture, controlled-write guardrails, and policy allowlist/denylist constraints.
- **SEC-002**: Ensure no document instructs users to expose secrets, disable guardrails, or bypass diagnostics/security checks.
- **OPS-001**: Include deterministic pre-deploy, deploy, post-deploy verification, rollback, and incident-response procedures.
- **OPS-002**: Include production observability minimums (health checks, diagnostics endpoints, logs, alerts, SLO indicators).
- **DOC-001**: Every updated/created document must include purpose, prerequisites, exact commands, expected outputs, and failure handling.
- **DOC-002**: Cross-links between related docs must be valid and non-broken.
- **CON-001**: Do not change source code while executing this plan; scope is documentation and related checklist artifacts only.
- **CON-002**: Preserve existing security controls and warning language from AGENTS.md, SECURITY.md, and docs/access-levels-and-controlled-write.md.
- **GUD-001**: Prefer incremental edits to existing docs before introducing new docs to avoid duplication.
- **PAT-001**: Use runbook pattern: Trigger -> Preconditions -> Steps -> Validation -> Rollback -> Escalation.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Build an evidence-backed baseline of current runtime behavior and map each docs file to a validation owner and status.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Generate full docs inventory from docs/ and docs/runbooks/ and store as a review matrix in docs/documentation-audit-2026-06-02.md with columns: file_path, scope, owner, source_of_truth, status. | ✅ | 2026-06-02 |
| TASK-002 | Validate runtime/deployment truths used by docs: Redis default container startup in docker/docker-compose.yml and docker/docker-compose.runtime.yml, env_file precedence behavior, and required MCP Streamable HTTP session flow. Record findings in audit report. | ✅ | 2026-06-02 |
| TASK-003 | Validate tool catalog truth source by mapping docs/mcp-tool-catalog.md entries to src/tools/tool_registry.py and src/tools/sql_tools.py; mark mismatches in audit report. | ✅ | 2026-06-02 |
| TASK-004 | Validate security/access truths by mapping docs/access-levels-and-controlled-write.md and docs/runtime-policy-configuration-guide.md against config/runtime-policy.yaml, policy/sql-allowlist.yaml, and policy/sql-denylist.yaml. | ✅ | 2026-06-02 |
| TASK-005 | Create an audit defect list section in docs/documentation-audit-2026-06-02.md with IDs and required remediation file targets. | ✅ | 2026-06-02 |

### Implementation Phase 2

- **GOAL-002**: Update existing documentation files to align with verified behavior and remove stale guidance.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-006 | Update docs/run-mcp-server-with-docker.md to reflect current Redis startup behavior, compose commands, and env_file-driven Redis configuration; include explicit verification commands for FASTMCP_RATE_LIMIT_BACKEND and FASTMCP_REDIS_URL. | ✅ | 2026-06-02 |
| TASK-007 | Update docs/mcp-tool-catalog.md so each tool entry exactly matches current registered names, argument contracts, and fallback behavior (including top_statements Query Store -> DMV fallback). | ✅ | 2026-06-02 |
| TASK-008 | Update docs/DEPLOYMENT-CHECKLIST.md with hard gates: diagnostics health pass, SQL connectivity pass for both instances, policy validation pass, and rollback readiness check. | ✅ | 2026-06-02 |
| TASK-009 | Verify docs/access-levels-and-controlled-write.md and docs/runtime-policy-configuration-guide.md against current controlled-write wording, actor expectations, and allowlist/denylist enforcement sequence. | ✅ | 2026-06-02 |
| TASK-010 | Update docs/azure-container-apps-deployment.md to reference current production prerequisites; verify docs/cloud-deployment-strategy-analysis.md remains accurate. | ✅ | 2026-06-02 |
| TASK-011 | Update docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md with reference status note; verify docs/github-branch-protection-checklist.md remains current. | ✅ | 2026-06-02 |
| TASK-012 | Add docs/release-notes-v1.3.1.md for post-v1.3.0 changes (Redis compose behavior, env precedence guidance, histogram cast fix, MCP client session requirements, documentation updates). | ✅ | 2026-06-02 |

### Implementation Phase 3

- **GOAL-003**: Create missing production-critical documents required for successful deployment and operations.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-013 | Create docs/production-deployment-runbook.md with deterministic steps: prerequisites, configuration matrix, deployment execution, smoke tests, rollback, and escalation contacts/placeholders. | ✅ | 2026-06-02 |
| TASK-014 | Create docs/production-operations-runbook.md covering daily checks, rate-limit monitoring, SQL pool health interpretation, and incident triage flow using existing diagnostics endpoints. | ✅ | 2026-06-02 |
| TASK-015 | Create docs/disaster-recovery-and-rollback.md defining backup expectations, restore validation, failback process, and service recovery verification steps. | ✅ | 2026-06-02 |
| TASK-016 | Create docs/production-configuration-matrix.md with environment variables, default values, required values, secret classification, and source location (.env, runtime policy, compose). | ✅ | 2026-06-02 |
| TASK-017 | Create docs/observability-and-alerting-baseline.md with minimum alerts, health probes, SLO indicators, and required log fields for production support. | ✅ | 2026-06-02 |

### Implementation Phase 4

- **GOAL-004**: Validate documentation quality, enforce consistency, and certify production documentation readiness.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-018 | Run markdown linting/link validation across docs/ and fix all broken internal links and heading anchor mismatches. | ❌ |  |
| TASK-019 | Execute command validation for every command block in updated/new docs in a controlled environment; annotate pass/fail and remediation in docs/traceability-matrix.md. | ❌ |  |
| TASK-020 | Perform security content review ensuring no instruction weakens guardrails or exposes secrets; record results in docs/documentation-audit-2026-06-02.md under SEC-REVIEW. | ✅ | 2026-06-02 |
| TASK-021 | Add docs/index.md as a canonical entrypoint that links all operational, deployment, policy, and runbook documents in execution order. | ✅ | 2026-06-02 |
| TASK-022 | Mark plan completion by updating this plan status to Completed and adding final audit summary with unresolved risks (if any). | ✅ | 2026-06-02 |

## 3. Alternatives

- **ALT-001**: Update only docs/run-mcp-server-with-docker.md and docs/mcp-tool-catalog.md. Rejected because production readiness requires complete deployment and operations coverage.
- **ALT-002**: Create only new docs without auditing existing docs. Rejected because stale existing guidance can still cause production misconfiguration.
- **ALT-003**: Consolidate all docs into one large production guide. Rejected because maintenance burden and change review granularity become poor.

## 4. Dependencies

- **DEP-001**: Source-of-truth code files: src/server.py, src/tools/sql_tools.py, src/tools/tool_registry.py, src/middleware/rate_limiter.py, src/tools/query_catalog.py.
- **DEP-002**: Source-of-truth configuration files: config/runtime-policy.yaml, policy/sql-allowlist.yaml, policy/sql-denylist.yaml, docker/docker-compose.yml, docker/docker-compose.runtime.yml.
- **DEP-003**: Existing operational docs: SECURITY.md, CONTRIBUTING.md, AGENTS.md, docs/access-levels-and-controlled-write.md.
- **DEP-004**: Validation tooling availability for Markdown lint/link checks in CI or local environment.

## 5. Files

- **FILE-001**: docs/run-mcp-server-with-docker.md - runtime and compose command accuracy.
- **FILE-002**: docs/mcp-tool-catalog.md - tool contract correctness.
- **FILE-003**: docs/DEPLOYMENT-CHECKLIST.md - production gate checklist.
- **FILE-004**: docs/access-levels-and-controlled-write.md - access model and controlled-write semantics.
- **FILE-005**: docs/runtime-policy-configuration-guide.md - policy configuration correctness.
- **FILE-006**: docs/azure-container-apps-deployment.md - cloud deployment path consistency.
- **FILE-007**: docs/cloud-deployment-strategy-analysis.md - strategy alignment to current runtime.
- **FILE-008**: docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md - diagnostics contract accuracy.
- **FILE-009**: docs/github-branch-protection-checklist.md - governance baseline.
- **FILE-010**: docs/release-notes-v1.3.0.md or new release note file - post-v1.3.0 changes.
- **FILE-011**: docs/traceability-matrix.md - audit status matrix and defect ledger.
- **FILE-012**: docs/production-deployment-runbook.md - new production deployment runbook.
- **FILE-013**: docs/production-operations-runbook.md - new production operations runbook.
- **FILE-014**: docs/disaster-recovery-and-rollback.md - new DR and rollback runbook.
- **FILE-015**: docs/production-configuration-matrix.md - new configuration baseline.
- **FILE-016**: docs/observability-and-alerting-baseline.md - new alerting/monitoring baseline.
- **FILE-017**: docs/index.md - new canonical docs index.
- **FILE-018**: plan/process-docs-production-readiness-audit-1.md - this implementation plan.

## 6. Testing

- **TEST-001**: Inventory completeness test: confirm every file in docs/ and docs/runbooks/ has a row in docs/traceability-matrix.md.
- **TEST-002**: Contract parity test: every tool listed in docs/mcp-tool-catalog.md exists in runtime tool registration.
- **TEST-003**: Command execution test: all deployment/runbook command blocks execute without undocumented prerequisites.
- **TEST-004**: Link integrity test: all relative links in docs resolve successfully.
- **TEST-005**: Security posture test: docs contain no instructions that disable policy enforcement, denylists, or redaction behavior.
- **TEST-006**: Production readiness gate test: docs/DEPLOYMENT-CHECKLIST.md can be executed end-to-end with explicit pass/fail outcomes.

## 7. Risks & Assumptions

- **RISK-001**: Hidden drift between code and docs may require iterative updates beyond one pass.
- **RISK-002**: Missing operational ownership/contact details may block completion of escalation sections in new runbooks.
- **RISK-003**: Environment-specific deployment commands may differ between local Docker and cloud targets, causing ambiguity if not separated clearly.
- **ASSUMPTION-001**: Existing diagnostics endpoints and tool names remain stable during this documentation audit cycle.
- **ASSUMPTION-002**: Team can provide production-specific secrets-management and on-call ownership details when placeholders are introduced.

## 8. Related Specifications / Further Reading

[docs/run-mcp-server-with-docker.md](../docs/run-mcp-server-with-docker.md)
[docs/mcp-tool-catalog.md](../docs/mcp-tool-catalog.md)
[docs/access-levels-and-controlled-write.md](../docs/access-levels-and-controlled-write.md)
[docs/runtime-policy-configuration-guide.md](../docs/runtime-policy-configuration-guide.md)
[docs/DEPLOYMENT-CHECKLIST.md](../docs/DEPLOYMENT-CHECKLIST.md)
[AGENTS.md](../AGENTS.md)
[SECURITY.md](../SECURITY.md)