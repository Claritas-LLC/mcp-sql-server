---
goal: Generate a Cloud Deployment Strategy Analysis for Hosting the MCP SQL Server Across Azure, AWS, and Databricks
version: 1.0
date_created: 2026-05-27
last_updated: 2026-05-27
owner: Cloud Solutions Architecture
status: Planned
tags: [architecture, design, deployment, azure, aws, databricks, mcp, sqlserver]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This plan defines how to produce a single decision document that enumerates deployment strategies for this MCP SQL Server across Azure, AWS, and Databricks, evaluates each strategy by complexity, cost, and security, and issues a recommendation that explicitly accounts for the current dependency that both SQL Server instances run on Azure VMs. The intended output is a decision-ready architecture document that can be used to verify whether Azure Container Apps is the best deployment target for this MCP server.

## 1. Requirements & Constraints

- **REQ-001**: Create one new document at `docs/cloud-deployment-strategy-analysis.md`.
- **REQ-002**: The document must enumerate at least these deployment strategies: Azure VM, Azure Container Apps, AWS-hosted option, AWS Bedrock fit assessment, and Databricks Apps.
- **REQ-003**: The document must analyze each strategy using the exact dimensions `complexity`, `cost`, and `security`.
- **REQ-004**: The document must include an explicit recommendation section with a ranked outcome, not just descriptive comparisons.
- **REQ-005**: The document must state that the SQL Server dependencies currently reside on Azure VMs and use that fact in the recommendation logic.
- **REQ-006**: The document must identify network-path implications for each strategy, including private connectivity feasibility, cross-cloud connectivity requirements, and expected latency/egress impact.
- **REQ-007**: The document must distinguish between viable hosting targets and non-hosting services. Specifically, it must validate whether AWS Bedrock can host this Python MCP server or only integrate with it indirectly.
- **REQ-008**: The document must include a decision matrix with normalized ratings for each strategy.
- **REQ-009**: The document must include a short executive summary for leadership review and a detailed rationale section for engineering review.
- **REQ-010**: The document must cross-reference current repository deployment guidance in `docs/azure-container-apps-deployment.md`, `docs/DEPLOYMENT-CHECKLIST.md`, and `docs/run-mcp-server-with-docker.md`.
- **SEC-001**: Every strategy analysis must address secret management, identity model, private network access to Azure-hosted SQL VMs, and blast radius.
- **SEC-002**: The document must preserve the repository's read-only-by-default and controlled-write posture as a non-negotiable deployment invariant.
- **SEC-003**: The document must identify where cloud-native identity and secret stores map to existing runtime expectations such as Key Vault or equivalent external secret managers.
- **CON-001**: The document must not assume a database relocation from Azure VMs to any other environment.
- **CON-002**: The document must not recommend a platform that cannot host an always-on Python HTTP service exposing `/mcp` and diagnostics endpoints.
- **CON-003**: The document must not contradict existing repository deployment docs unless the new document explicitly marks them as narrower implementation guides rather than platform recommendation guides.
- **CON-004**: The document must use deterministic labels for ratings. Allowed rating values are `Low`, `Medium`, `High`, and `Very High` only.
- **GUD-001**: The document should prefer Azure-native strategies when they materially reduce network complexity to Azure-hosted SQL VMs.
- **GUD-002**: The document should separate `platform fit` from `operational maturity`; a platform may be technically viable but still non-recommended.
- **PAT-001**: Use a weighted decision matrix with explicit weights for complexity, cost, security, network proximity, and operational fit.
- **PAT-002**: Use one subsection per strategy with the exact subheadings `Overview`, `Implementation Pattern`, `Complexity`, `Cost`, `Security`, `Network Considerations`, `Pros`, `Cons`, and `Recommendation Fit`.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Define the comparison framework and exact strategy set for the decision document.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---------- |
| TASK-001 | Create `docs/cloud-deployment-strategy-analysis.md` with front matter-free standard docs formatting used in the repository. |  |  |
| TASK-002 | Define the strategy set in the new document as: `Azure Container Apps`, `Azure VM`, `AWS ECS or EC2`, `AWS Bedrock fit assessment`, and `Databricks Apps`. |  |  |
| TASK-003 | Add a `Decision Criteria` section that defines rating semantics for `complexity`, `cost`, and `security` using only `Low`, `Medium`, `High`, and `Very High`. |  |  |
| TASK-004 | Add a `Context` section that states both SQL Server instances are hosted on Azure VMs and that the MCP server requires outbound SQL connectivity plus inbound HTTP access for `/mcp` and diagnostics endpoints. |  |  |
| TASK-005 | Define weighted scoring in the document using these exact weights: `security=30`, `network_proximity=25`, `operational_fit=20`, `complexity=15`, `cost=10`. |  |  |

### Implementation Phase 2

- **GOAL-002**: Analyze Azure-native hosting strategies against the current Azure VM SQL topology.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-006 | Add subsection `Azure Container Apps` describing the implementation pattern as containerized deployment with VNet integration, managed identity, Key Vault-backed secrets, and Entra-authenticated ingress aligned with `docs/azure-container-apps-deployment.md`. |  |  |
| TASK-007 | Rate `Azure Container Apps` for complexity, cost, security, network proximity, and operational fit, and explain that it is the default comparison baseline because the repository already contains ACA deployment guidance. |  |  |
| TASK-008 | Add subsection `Azure VM` describing the implementation pattern as Docker or process-based hosting on a dedicated VM in the same or peered Azure network as the SQL VMs. |  |  |
| TASK-009 | Rate `Azure VM` for complexity, cost, security, network proximity, and operational fit, with explicit discussion of higher patching burden, stronger raw network locality, and larger host-management surface area compared with ACA. |  |  |
| TASK-010 | Add an Azure recommendation note that compares `Azure Container Apps` versus `Azure VM` directly and states when VM hosting is justified, such as strict network-control requirements, custom agents, or unsupported ACA dependencies. |  |  |

### Implementation Phase 3

- **GOAL-003**: Analyze AWS-hosted strategies and explicitly validate Bedrock fit.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-011 | Add subsection `AWS ECS or EC2` describing the implementation pattern as container or VM hosting in AWS with secure connectivity back to Azure SQL VMs through site-to-site VPN, private interconnect, or public endpoint exposure if no private path exists. |  |  |
| TASK-012 | Rate `AWS ECS or EC2` for complexity, cost, security, network proximity, and operational fit, and explicitly account for cross-cloud egress, dual-cloud identity and secret-management overhead, and additional network fault domains. |  |  |
| TASK-013 | Add subsection `AWS Bedrock fit assessment` that states whether Bedrock can host a custom Python MCP HTTP server. The section must explicitly conclude whether Bedrock is a hosting platform, an integration platform, or not applicable for this server architecture. |  |  |
| TASK-014 | If Bedrock is not a viable hosting target, document it as `Not Recommended` and explain the correct interpretation: Bedrock may consume or integrate with an externally hosted service, but it is not the compute platform for this MCP server. |  |  |
| TASK-015 | Add an AWS summary note explaining that AWS hosting is structurally disadvantaged because the SQL backends remain on Azure VMs, making Azure-to-Azure deployment the lower-complexity and lower-risk default. |  |  |

### Implementation Phase 4

- **GOAL-004**: Analyze Databricks Apps as a platform-fit candidate.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-016 | Add subsection `Databricks Apps` describing the implementation pattern as hosting an application workload in the Databricks control plane or workspace context with secure secret handling and outbound connectivity to Azure VM-hosted SQL Servers. |  |  |
| TASK-017 | Rate `Databricks Apps` for complexity, cost, security, network proximity, and operational fit, explicitly noting whether the platform is optimized for long-running MCP gateway services versus analytics- or data-app-centric workloads. |  |  |
| TASK-018 | Add a platform-fit note explaining that Databricks Apps may be technically possible but is likely a weaker operational fit if the primary requirement is stable MCP service hosting rather than analytics-adjacent application delivery. |  |  |

### Implementation Phase 5

- **GOAL-005**: Produce the decision matrix, recommendation, and document validation output.

| Task | Description | Completed | Date |
| -------- | --------------------- | --------- | ---- |
| TASK-019 | Add a `Comparison Matrix` table to `docs/cloud-deployment-strategy-analysis.md` with columns `Strategy`, `Complexity`, `Cost`, `Security`, `Network Proximity`, `Operational Fit`, `Weighted Outcome`, and `Recommendation`. |  |  |
| TASK-020 | Add a `Recommendation` section that ranks all strategies from most recommended to least recommended and explicitly states whether `Azure Container Apps` is the best current default for this repository. |  |  |
| TASK-021 | Add a `When Not to Choose ACA` subsection listing concrete disqualifiers such as unsupported network controls, incompatible runtime dependencies, or mandatory host-level agents. |  |  |
| TASK-022 | Add a `Validation Sources` section linking repository references: `docs/azure-container-apps-deployment.md`, `docs/DEPLOYMENT-CHECKLIST.md`, `docs/run-mcp-server-with-docker.md`, and any official vendor documentation consulted during authoring. |  |  |
| TASK-023 | Run a final consistency pass to confirm the new document does not claim Bedrock is a compute host for this Python service unless verified by official documentation. |  |  |

## 3. Alternatives

- **ALT-001**: Create separate provider-specific documents for Azure, AWS, and Databricks. Not chosen because the user needs one decision artifact that directly compares options under the same constraints.
- **ALT-002**: Compare only Azure VM and Azure Container Apps. Not chosen because the user explicitly requested Azure, AWS, and Databricks strategies.
- **ALT-003**: Treat AWS Bedrock as a standard hosting target without validation. Not chosen because Bedrock may not be a general-purpose runtime for this MCP server and requires explicit fit validation.
- **ALT-004**: Produce a narrative recommendation without a scoring matrix. Not chosen because the user requested analysis by complexity, cost, and security and needs an auditable recommendation basis.

## 4. Dependencies

- **DEP-001**: Existing Azure deployment guidance in `docs/azure-container-apps-deployment.md`.
- **DEP-002**: Existing Azure deployment checklist in `docs/DEPLOYMENT-CHECKLIST.md`.
- **DEP-003**: Existing Docker runtime guidance in `docs/run-mcp-server-with-docker.md`.
- **DEP-004**: Current runtime architecture described in `README.md` and `AGENTS.md`.
- **DEP-005**: Official vendor documentation for Azure Container Apps, Azure VM networking, AWS compute hosting, AWS Bedrock capabilities, and Databricks Apps capabilities.

## 5. Files

- **FILE-001**: `plan/architecture-cloud-deployment-strategies-1.md` - This implementation plan.
- **FILE-002**: `docs/cloud-deployment-strategy-analysis.md` - Target decision document to be generated.
- **FILE-003**: `docs/azure-container-apps-deployment.md` - Current Azure implementation reference to cite, not replace.
- **FILE-004**: `docs/DEPLOYMENT-CHECKLIST.md` - Current Azure operational checklist to cite, not replace.
- **FILE-005**: `docs/run-mcp-server-with-docker.md` - Current runtime packaging reference to cite for common deployment requirements.
- **FILE-006**: `README.md` - Source for current runtime scope and architectural summary.

## 6. Testing

- **TEST-001**: Verify `docs/cloud-deployment-strategy-analysis.md` includes all five required strategies.
- **TEST-002**: Verify each strategy section contains the exact subheadings `Overview`, `Implementation Pattern`, `Complexity`, `Cost`, `Security`, `Network Considerations`, `Pros`, `Cons`, and `Recommendation Fit`.
- **TEST-003**: Verify the document includes a comparison matrix with normalized ratings and a final ranked recommendation.
- **TEST-004**: Verify the document explicitly states that the SQL Servers remain on Azure VMs and that this materially affects network, cost, and security analysis.
- **TEST-005**: Verify the document does not present AWS Bedrock as a general-purpose compute host unless supported by cited official documentation.
- **TEST-006**: Verify the recommendation section answers the specific decision question: whether Azure Container Apps is the best current approach for this MCP server.

## 7. Risks & Assumptions

- **RISK-001**: Vendor platform capabilities may be misunderstood if the author relies on assumptions instead of current official documentation, especially for Bedrock and Databricks Apps.
- **RISK-002**: A purely feature-based comparison may underweight the network penalty of running the MCP server outside Azure while the SQL Servers stay on Azure VMs.
- **RISK-003**: Security comparisons may be skewed if the document does not separate platform-native security controls from the operational burden required to configure them correctly.
- **RISK-004**: Cost conclusions may be misleading if data egress, private networking, and always-on compute requirements are omitted.
- **ASSUMPTION-001**: The MCP server remains a Python-based always-on HTTP service exposing `/mcp` and diagnostics routes.
- **ASSUMPTION-002**: Both SQL Server targets continue running on Azure VMs for the decision horizon covered by the document.
- **ASSUMPTION-003**: Azure Container Apps remains a supported deployment path in this repository and is the incumbent cloud-reference implementation.
- **ASSUMPTION-004**: The recommendation should optimize for practical deployment of this existing codebase, not for a hypothetical future redesign.

## 8. Related Specifications / Further Reading

- `docs/azure-container-apps-deployment.md`
- `docs/DEPLOYMENT-CHECKLIST.md`
- `docs/run-mcp-server-with-docker.md`
- `plan/remote-sql2019-fastmcp3-deployment-plan.md`
- `README.md`