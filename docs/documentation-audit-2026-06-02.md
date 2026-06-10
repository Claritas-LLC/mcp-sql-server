# Documentation Audit - 2026-06-02 (updated 2026-06-10)

## Scope

- Reviewed all Markdown files under `docs/` and `docs/runbooks/`.
- Verified high-risk runtime/deployment guidance against source files in `src/`, `config/`, and `docker/`.

## Review Matrix

| File | Status | Action |
| --- | --- | --- |
| `docs/access-levels-and-controlled-write.md` | Updated (2026-06-10) | Expanded denylist section to list all 13 blocked patterns (DDL, DML, DCL, system procedures). |
| `docs/azure-container-apps-deployment.md` | Updated | Fixed MCP `/mcp/` validation examples to use initialize + session ID flow. |
| `docs/cloud-deployment-strategy-analysis.md` | Up-to-date | Retained; no changes required. |
| `docs/demo-narration-script.md` | Updated (2026-06-10) | Expanded SQL denylist description to include DML (INSERT, UPDATE, DELETE, MERGE) and DCL (GRANT, REVOKE, DENY) alongside existing DDL and system procedures. |
| `docs/DEPLOYMENT-CHECKLIST.md` | Updated | Added production gate criteria and session-based MCP validation steps. |
| `docs/github-branch-protection-checklist.md` | Up-to-date | Retained; no changes required. |
| `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` | Updated | Added explicit reference status note and canonical pointer to tool catalog. |
| `docs/mcp-tool-catalog.md` | Rebuilt | Replaced corrupted/duplicated sections with current registered tool contracts. |
| `docs/release-notes-v1.2.0.md` | Historical | Retained; no changes required. |
| `docs/release-notes-v1.3.0.md` | Historical | Retained; no changes required. || `docs/release-notes-v1.4.0.md` | New (2026-06-10) | Added for SQL denylist expansion release. || `docs/run-mcp-server-with-docker.md` | Updated | Clarified Redis-default runtime behavior and added session-based HTTP call pattern. |
| `docs/runtime-policy-configuration-guide.md` | Up-to-date | Retained; no changes required. |
| `docs/traceability-matrix.md` | Generated placeholder | Retained; CI-owned file. |
| `docs/runbooks/scaling-strategy.md` | Up-to-date | Retained; no changes required. |
| `docs/runbooks/security-maintenance.md` | Up-to-date | Retained; no changes required. |

## Missing Production Docs Added

| File | Purpose |
| --- | --- |
| `docs/index.md` | Canonical documentation entrypoint and navigation map. |
| `docs/production-deployment-runbook.md` | Deterministic production deployment and rollback procedure. |
| `docs/production-operations-runbook.md` | Day-2 operations and incident triage workflow. |
| `docs/disaster-recovery-and-rollback.md` | Recovery playbook and rollback decision path. |
| `docs/production-configuration-matrix.md` | Runtime configuration baseline and source mapping. |
| `docs/observability-and-alerting-baseline.md` | Minimum observability and alerting requirements. |
| `docs/release-notes-v1.3.1.md` | Documentation release change log. |

## Key Findings

1. `docs/mcp-tool-catalog.md` contained duplicated and malformed sections that could lead to incorrect tool usage.
2. MCP streamable HTTP requirements (Accept header + session ID lifecycle) were missing from key deployment/runtime docs.
3. Production operations and disaster recovery runbooks were not present before this audit and have now been added.

## Residual Risks

1. `docs/mcp-sql2019-connectivity-discovery-diagnostics-spec.md` is still partly a design/spec artifact and may drift from runtime behavior if treated as canonical.
2. Cloud/provider instructions can drift as platform CLIs evolve; command blocks should be re-validated during each release cycle.

## Recommended Ongoing Control

- Add a release checklist item to validate docs command examples and MCP session flow each release.
- Treat `docs/mcp-tool-catalog.md` as the canonical operational contract and update it whenever tool registration changes.
