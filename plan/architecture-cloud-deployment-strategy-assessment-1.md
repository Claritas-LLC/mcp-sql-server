---
goal: Create a Comparative Cloud Deployment Strategy Document for MCP SQL Server Across Azure, AWS, and Databricks
version: 1.0
date_created: 2026-05-27
last_updated: 2026-05-27
owner: Cloud Solutions Architecture
status: Planned
tags: [architecture, deployment, azure, aws, databricks, mcp, sqlserver, documentation]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This plan defines how to produce a single decision-quality document that compares viable deployment strategies for this MCP SQL Server service across Azure, AWS, and Databricks. The document will evaluate each strategy against complexity, cost, security, and operational fit, with explicit consideration that the SQL Server instances accessed by this MCP server are hosted on Azure VMs.

## 1. Requirements & Constraints

- **REQ-001**: Create a new comparison document at `docs/cloud-deployment-strategy-comparison.md`.
- **REQ-002**: The comparison document must enumerate deployment strategies in Azure, AWS, and Databricks.
- **REQ-003**: The comparison document must include, at minimum, these candidate strategies: Azure VM, Azure Container Apps, AWS-hosted strategy for MCP consumption by AWS workloads, and Databricks Apps.
- **REQ-004**: The comparison document must evaluate each strategy using the same rubric: hosting fit, implementation complexity, operating cost, security posture, network path to Azure VM-hosted SQL Server, scalability, and operational burden.
- **REQ-005**: The comparison document must produce one primary recommendation and at least one conditional alternative recommendation.
- **REQ-006**: The comparison document must explicitly distinguish between direct hosting strategies and indirect integration strategies when a platform is not a natural runtime host for this Python FastMCP service.
- **REQ-007**: The comparison document must include an executive summary suitable for architecture decision review.
- **REQ-008**: The comparison document must include a final decision matrix with normalized ratings for all candidate strategies.
- **SEC-001**: Every strategy analysis must account for the current security posture of the service: read-only defaults, controlled-write guardrails, rate limiting, audit logging, Entra authentication support, and secret isolation.
- **SEC-002**: Every strategy analysis must evaluate the exposure introduced by cross-cloud traffic between the MCP host and SQL Server running on Azure VMs.
- **SEC-003**: The document must prefer private networking patterns over public SQL exposure and must treat public SQL reachability as non-recommended.
- **SEC-004**: The document must call out identity, secret-management, ingress, and egress controls required for each candidate platform.
- **CON-001**: The analysis must remain consistent with the current repository runtime shape: Python 3.11+, FastMCP + FastAPI, HTTP `/mcp` endpoint, Docker-based deployment path, and dual SQL instance configuration.
- **CON-002**: The analysis must assume the SQL Server systems of record remain on Azure VMs and are not relocated as part of this decision.
- **CON-003**: The plan must not require code changes to the runtime service; it only defines documentation deliverables and decision analysis.
- **GUD-001**: Use current repository docs as source-of-truth for Azure deployment capabilities and Docker runtime assumptions.
- **GUD-002**: Use explicit scoring criteria so two reviewers can independently reproduce the same recommendation.
- **PAT-001**: Treat platform-native connectivity to Azure VM-hosted SQL Server as a first-order decision driver, not a secondary note.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Define the comparison scope, candidate strategies, and scoring rubric before drafting the decision document.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Create a strategy inventory section in `docs/cloud-deployment-strategy-comparison.md` listing these candidates exactly: `Azure VM`, `Azure Container Apps`, `Azure App Service with container hosting`, `AWS ECS/Fargate for MCP server near AWS clients`, `AWS Bedrock-adjacent integration pattern`, and `Databricks Apps`. |  |  |
| TASK-002 | Define a normalized scoring rubric in `docs/cloud-deployment-strategy-comparison.md` with dimensions `Complexity`, `Cost`, `Security`, `Network Fit`, `Operational Overhead`, and `Platform Alignment`, each scored on a fixed 1-5 scale with written scoring rules. |  |  |
| TASK-003 | Add a section that classifies each candidate as either `Direct Host`, `Container Host`, or `Indirect Integration Pattern` so platforms that cannot directly host the service are analyzed accurately. |  |  |
| TASK-004 | Add explicit architectural assumptions to `docs/cloud-deployment-strategy-comparison.md`, including that SQL Server remains on Azure VMs, private networking is preferred, and the current service remains a Python HTTP containerized workload. |  |  |

### Implementation Phase 2

- GOAL-002: Analyze Azure-hosted strategies with emphasis on proximity to Azure VM-hosted SQL Server and existing repo deployment guidance.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-005 | Document the `Azure VM` strategy in `docs/cloud-deployment-strategy-comparison.md`, including deployment shape, network path to Azure VM SQL Server, expected operational tasks, likely cost profile, and hardening controls. |  |  |
| TASK-006 | Document the `Azure Container Apps` strategy in `docs/cloud-deployment-strategy-comparison.md`, reusing facts from `docs/azure-container-apps-deployment.md` and evaluating VNet integration, managed identity, Key Vault secret flow, elasticity, and cost. |  |  |
| TASK-007 | Document the `Azure App Service with container hosting` strategy in `docs/cloud-deployment-strategy-comparison.md`, evaluating whether it is simpler or weaker than ACA for this MCP server’s network and auth requirements. |  |  |
| TASK-008 | Add a subsection that compares Azure VM vs Azure Container Apps vs Azure App Service specifically for private connectivity to Azure VM SQL Server, operational maintenance, and secret management. |  |  |

### Implementation Phase 3

- GOAL-003: Analyze AWS and Databricks strategies with explicit treatment of cross-cloud networking and platform fit limitations.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-009 | Document the `AWS ECS/Fargate for MCP server near AWS clients` strategy in `docs/cloud-deployment-strategy-comparison.md`, including required secure connectivity back to Azure VM SQL Server through VPN, private link equivalent, or other private network extension. |  |  |
| TASK-010 | Document the `AWS Bedrock-adjacent integration pattern` in `docs/cloud-deployment-strategy-comparison.md` and explicitly state whether Bedrock is a direct hosting target for this server or only a consumer/integration environment that still requires a separate runtime host. |  |  |
| TASK-011 | Document the `Databricks Apps` strategy in `docs/cloud-deployment-strategy-comparison.md`, including feasibility of hosting the MCP server runtime, network requirements back to Azure VM SQL Server, authentication boundaries, and operational tradeoffs. |  |  |
| TASK-012 | Add a dedicated cross-cloud risk section in `docs/cloud-deployment-strategy-comparison.md` covering latency, egress charges, network trust boundaries, private connectivity complexity, incident response overhead, and secret sprawl for AWS and Databricks options. |  |  |

### Implementation Phase 4

- GOAL-004: Produce the recommendation, final decision matrix, and repository cross-links.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-013 | Create a decision matrix table in `docs/cloud-deployment-strategy-comparison.md` with one row per candidate strategy and one column per scoring dimension plus `Recommended Use`. |  |  |
| TASK-014 | Write a recommendation section in `docs/cloud-deployment-strategy-comparison.md` that names one default recommendation, one conditional alternative, and one set of explicitly non-preferred options. |  |  |
| TASK-015 | Add a short executive summary at the top of `docs/cloud-deployment-strategy-comparison.md` stating that Azure-hosted deployment is the expected default when SQL Server remains on Azure VMs unless there is a stronger platform-coupling requirement elsewhere. |  |  |
| TASK-016 | Update `README.md` to add a link to `docs/cloud-deployment-strategy-comparison.md` under the documentation list after the document is created and reviewed. |  |  |

### Implementation Phase 5

- GOAL-005: Validate the document for accuracy, consistency, and decision usefulness.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-017 | Verify all statements about current runtime behavior against `README.md`, `docs/run-mcp-server-with-docker.md`, `docs/azure-container-apps-deployment.md`, and `docs/DEPLOYMENT-CHECKLIST.md`. |  |  |
| TASK-018 | Validate that every candidate strategy includes all required dimensions: complexity, cost, security, network fit, and recommendation status. |  |  |
| TASK-019 | Validate that the document contains no recommendation that depends on public exposure of Azure VM SQL Server endpoints. |  |  |
| TASK-020 | Run markdown/documentation review for clarity and consistency, then finalize the document for architecture review. |  |  |

## 3. Alternatives

- **ALT-001**: Create separate deployment guides for Azure, AWS, and Databricks without a unified comparison. Not chosen because it does not produce a single decision artifact with comparable scoring.
- **ALT-002**: Limit the document to Azure-only options because the SQL Server lives on Azure VMs. Not chosen because the user is explicitly evaluating cross-cloud deployment choices and needs quantified tradeoffs.
- **ALT-003**: Treat AWS Bedrock and Databricks Apps as equivalent direct hosting targets without qualification. Not chosen because the plan must distinguish direct hosting from adjacent integration patterns to avoid architectural errors.

## 4. Dependencies

- **DEP-001**: `README.md` for current runtime description and documentation index.
- **DEP-002**: `docs/azure-container-apps-deployment.md` for the repo’s existing Azure Container Apps deployment facts.
- **DEP-003**: `docs/DEPLOYMENT-CHECKLIST.md` for currently validated Azure deployment assumptions.
- **DEP-004**: `docs/run-mcp-server-with-docker.md` for container runtime and operational expectations.
- **DEP-005**: Current repository architecture boundaries in `AGENTS.md` and runtime entry point notes in `src/server.py`.

## 5. Files

- **FILE-001**: `plan/architecture-cloud-deployment-strategy-assessment-1.md` - This implementation plan.
- **FILE-002**: `docs/cloud-deployment-strategy-comparison.md` - New decision document comparing Azure, AWS, and Databricks deployment strategies.
- **FILE-003**: `README.md` - Documentation index update to expose the new comparison document.

## 6. Testing

- **TEST-001**: Verify the new document contains all required candidate strategies and no candidate is missing a rubric score.
- **TEST-002**: Verify every strategy analysis includes explicit discussion of complexity, cost, security, and network path to Azure VM-hosted SQL Server.
- **TEST-003**: Verify the recommendation section names one primary recommendation and one conditional fallback recommendation.
- **TEST-004**: Verify all repository-specific claims are traceable to current local docs and do not contradict existing deployment guidance.
- **TEST-005**: Verify `README.md` links to the new comparison document after implementation.

## 7. Risks & Assumptions

- **RISK-001**: AWS and Databricks platform capabilities may be overstated if the document does not clearly separate direct hosting from integration-only patterns.
- **RISK-002**: Cost comparisons may become misleading if network egress and private connectivity costs are omitted from cross-cloud options.
- **RISK-003**: Security scoring may be distorted if the analysis assumes public SQL access instead of private network extension.
- **RISK-004**: A simplistic recommendation could ignore organizational constraints such as existing AWS or Databricks operating standards.
- **ASSUMPTION-001**: The MCP server remains a containerized Python service exposed over HTTP and does not require platform-specific rewrite.
- **ASSUMPTION-002**: The Azure VM-hosted SQL Server systems remain the authoritative data sources for both instances.
- **ASSUMPTION-003**: Azure-hosted deployment options will generally score better on network fit and security because they avoid avoidable cross-cloud paths to Azure VM-hosted SQL Server.
- **ASSUMPTION-004**: Cross-cloud deployment options are only compelling when there is a stronger workload locality requirement for AWS or Databricks consumers than for the SQL systems of record.

## 8. Related Specifications / Further Reading

- `README.md`
- `docs/azure-container-apps-deployment.md`
- `docs/DEPLOYMENT-CHECKLIST.md`
- `docs/run-mcp-server-with-docker.md`
- `plan/remote-sql2019-fastmcp3-deployment-plan.md`