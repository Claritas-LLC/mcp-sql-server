# Cloud Deployment Strategy Analysis

## Executive Summary

This repository already has a validated deployment path for Azure Container Apps, and the current SQL Server systems of record remain on Azure VMs. Given that topology, Azure Container Apps is the best default deployment target for this MCP server because it offers the strongest balance of security, operational simplicity, and cloud-native controls without introducing avoidable cross-cloud network complexity.

Azure VM hosting remains the strongest fallback when host-level control is mandatory, such as when you need custom agents, unusual network controls, or runtime dependencies that do not fit well in Azure Container Apps. AWS-hosted deployment and Databricks Apps are both technically possible in some form, but they are structurally disadvantaged because they force the service to reach back into Azure for its primary SQL dependencies. AWS Bedrock is not a hosting target for this MCP server; it is an AI service that could consume or integrate with an externally hosted MCP service, but it is not the runtime platform for this Python HTTP application.

## Context

This MCP server is a Python 3.11+ FastMCP and FastAPI service that exposes HTTP endpoints at `/mcp` plus diagnostics routes. The repository already documents Docker-based packaging and an Azure Container Apps deployment flow with Entra authentication, Key Vault secret references, and VNet-aware SQL connectivity. The service is security-sensitive because it enforces read-only-by-default behavior, controlled-write guardrails, rate limiting, audit logging, and strict redaction behavior.

The primary architectural constraint is that both SQL Server instances accessed by this MCP server are hosted on Azure VMs. That fact materially changes the recommendation because network path, private connectivity, secret handling, and operational response all become simpler when the MCP host remains in Azure.

## Decision Criteria

### Rating Scale

- `Low`: Favorable for adoption or low burden.
- `Medium`: Acceptable with moderate tradeoffs.
- `High`: Significant tradeoffs or notable burden.
- `Very High`: Strong downside or major complexity/risk.

### Weighted Scoring Model

The comparison uses these weights:

- `Security`: 30
- `Network Proximity`: 25
- `Operational Fit`: 20
- `Complexity`: 15
- `Cost`: 10

For `Complexity` and `Cost`, lower is better. For `Security`, `Network Proximity`, and `Operational Fit`, higher is better. To normalize the matrix, the document uses this numeric conversion:

| Dimension Type | Low | Medium | High | Very High |
| --- | --- | --- | --- | --- |
| Complexity or Cost | 4 | 3 | 2 | 1 |
| Security, Network Proximity, or Operational Fit | 1 | 2 | 3 | 4 |

The weighted outcome is used for ranking, but the final recommendation also considers architectural fit and operational realism.

## Strategy Analysis

### Azure Container Apps

#### Overview

Azure Container Apps is a serverless container platform designed for long-running containerized applications, APIs, and background services. It aligns directly with this repository's existing container packaging and current Azure deployment documentation.

#### Implementation Pattern

Package the MCP server as the current Docker image, deploy it to Azure Container Apps, use managed identity for Azure resource access, use Key Vault references for secrets, and use VNet integration so the service can reach SQL Server on Azure VMs through private network paths. External or internal ingress can be selected depending on whether `/mcp` must be exposed publicly or only to private consumers.

#### Complexity

`Low`

This option is already documented in the repo, supports container-native deployment, and avoids managing the underlying host. Network integration and managed identity add some setup effort, but the control plane and scaling model are already aligned to the current service shape.

#### Cost

`Low`

For an always-on but not extremely heavy MCP service, ACA is typically cost-efficient relative to a dedicated VM because it reduces baseline host overhead and operations time. Cost can rise if minimum replica counts, dedicated workload profiles, or heavy private networking requirements are added, but it remains favorable for this service profile.

#### Security

`High`

ACA supports managed identity, secret handling, private networking, internal ingress, and container isolation. It maps well to the repo's current Entra and Key Vault guidance and avoids exposing SQL publicly when deployed correctly. The main security tradeoff is reduced host-level control compared to a VM, but for this service that is usually a net advantage rather than a weakness.

#### Network Considerations

This is the best cloud-native fit when SQL Server remains on Azure VMs. The service can stay in Azure, use VNet integration, and keep the network path short and private. This minimizes latency, reduces egress concerns, and keeps incident response inside one cloud network domain.

#### Pros

- Strong fit for the repository's existing Docker and Azure deployment model.
- Built-in scaling, ingress, revisioning, and secret management.
- Lower operational burden than self-managed hosts.
- Strong alignment with private Azure-to-Azure connectivity to SQL VMs.

#### Cons

- Less host-level customization than a dedicated VM.
- Some network and debugging scenarios are less direct than logging into a VM.
- If very specific agents or OS-level controls are required, fit declines.

#### Recommendation Fit

`Recommended as the default deployment target.`

### Azure VM

#### Overview

Azure VM hosting places the MCP server on a dedicated VM in Azure, either as a Dockerized service or a direct Python process. This maximizes infrastructure control and keeps the service close to the SQL VMs.

#### Implementation Pattern

Deploy the existing container or Python runtime on a hardened Azure VM in the same VNet or a peered VNet as the SQL Server VMs. Use NSGs, local OS hardening, patch management, and a secret store integration such as Key Vault plus managed identity where possible.

#### Complexity

`Medium`

Application deployment itself is straightforward, but the platform burden is materially higher than ACA because the team must own patching, VM baseline hardening, capacity planning, log shipping, service supervision, and OS lifecycle work.

#### Cost

`Medium`

VMs introduce fixed cost whether the service is lightly used or not. For one always-on service the cost may still be acceptable, but it generally becomes less favorable than ACA once host operations and patching time are counted.

#### Security

`High`

This can be highly secure when properly hardened because it allows tight network placement and full OS control. However, that same control increases operational responsibility. Security quality depends more directly on patch discipline, VM baseline enforcement, endpoint protection, and administrator hygiene.

#### Network Considerations

This has the strongest raw network locality because the service can sit directly beside the SQL VMs. It is a very good option when the main driver is strict network governance or tight host-level control.

#### Pros

- Maximum control over OS, networking, and runtime dependencies.
- Very strong proximity to Azure VM-hosted SQL Server.
- Useful when custom agents, drivers, or host policies are required.

#### Cons

- Higher ongoing operational burden.
- Higher patching and maintenance responsibility.
- Less elegant scaling and rollout behavior than ACA.

#### Recommendation Fit

`Recommended only when host-level control requirements outweigh the added operational burden.`

### AWS ECS or EC2

#### Overview

AWS ECS or EC2 can host this MCP server as a containerized or VM-based service, but the application would then depend on cross-cloud connectivity back to Azure VM-hosted SQL Server.

#### Implementation Pattern

Run the service in ECS on Fargate or EC2, or on a dedicated EC2 instance, and establish secure connectivity to Azure through site-to-site VPN, private interconnect, or another network extension. Public SQL exposure should be treated as non-recommended.

#### Complexity

`High`

The container hosting itself is well understood, but the real complexity comes from hybrid network design, DNS behavior, traffic routing, secret-management duplication, IAM plus Azure identity coordination, and troubleshooting across two clouds.

#### Cost

`High`

Beyond compute cost, this option adds cross-cloud network cost, possible egress cost, duplicated observability tooling, and additional engineering time. The total platform cost is therefore materially less favorable than keeping the service in Azure.

#### Security

`Medium`

AWS can securely host the service, but the end-to-end design is weaker than Azure-native hosting because the trust boundary spans clouds. The cross-cloud network path, secret duplication, and operational split increase the number of failure and control points.

#### Network Considerations

This is the largest drawback. The service's main database dependency remains in Azure, so AWS hosting creates longer network paths, more routing complexity, and more failure modes. It is only compelling when the dominant clients of the MCP server are already in AWS and there is a strong reason to keep the service near those consumers.

#### Pros

- Strong container-hosting support through ECS and EC2.
- Useful when AWS is the dominant application platform for the MCP consumers.
- May fit organizations already standardized on AWS runtime operations.

#### Cons

- Cross-cloud connectivity back to Azure SQL VMs is a major penalty.
- Higher security and troubleshooting complexity.
- More expensive in networking and operational effort.

#### Recommendation Fit

`Situational only. Not preferred while SQL Server remains on Azure VMs.`

### AWS Bedrock Fit Assessment

#### Overview

Amazon Bedrock is a managed generative AI service that provides access to foundation models and AI-building capabilities. It is not the same thing as a general-purpose container or VM hosting environment.

#### Implementation Pattern

Bedrock can act as a consumer or integration layer for AI workloads that call external services, but it is not the runtime host for this MCP server's always-on Python HTTP application. If an AWS AI solution wants to use this MCP server, the correct pattern is to host the MCP server elsewhere, then let Bedrock-adjacent applications call it.

#### Complexity

`Very High`

As a direct hosting option, the complexity is effectively prohibitive because the platform does not match the application's runtime requirements.

#### Cost

`High`

Cost is not the main issue here. The primary issue is platform mismatch. Any architecture that tries to force Bedrock into the hosting role would add unnecessary complexity without solving the compute-hosting requirement.

#### Security

`Low`

Security is not rated poorly because Bedrock itself is insecure. It is rated poorly for this use case because it is the wrong abstraction for hosting this server, so the design would still need another secure runtime elsewhere.

#### Network Considerations

Bedrock does not remove the need for a separately hosted MCP service. The SQL connectivity problem remains entirely unresolved until another hosting platform is chosen.

#### Pros

- Relevant if an AI workflow in AWS wants to consume an external MCP service.
- Useful as an integration consumer of the service, not as the service host.

#### Cons

- Not a direct hosting platform for this Python HTTP MCP server.
- Does not solve compute hosting, diagnostics hosting, or SQL connectivity.
- Creates architectural confusion if treated as a deployment target.

#### Recommendation Fit

`Not recommended as a hosting strategy. Valid only as an external consumer or integration surface.`

### Databricks Apps

#### Overview

Databricks Apps is an app-hosting surface inside the Databricks platform for secure data and AI applications. It is more plausible as a host than Bedrock because it does support application deployment, including Python frameworks, but it is primarily optimized for data and AI app scenarios rather than a general MCP gateway service.

#### Implementation Pattern

Deploy an app into Databricks Apps and configure outbound connectivity, secrets, authorization, and operational telemetry so it can reach the Azure VM-hosted SQL Servers. This requires validating that the app model, networking model, and runtime limits fit a long-running MCP API service rather than an interactive data app.

#### Complexity

`High`

Although Databricks Apps supports application deployment, this service is not naturally centered on Databricks-native data products. The engineering team would need to validate platform fit, networking behavior, auth boundaries, and service lifecycle assumptions that are not already established in the repo.

#### Cost

`Medium`

Compute cost may be reasonable, but this option introduces platform-premium considerations, workspace constraints, and additional integration work. It is less obviously cost-efficient than ACA for an always-on MCP gateway.

#### Security

`Medium`

Databricks Apps includes secure app features and platform controls, but for this use case the architecture still stretches across platforms and depends on outbound connectivity to Azure SQL VMs. That weakens the overall fit compared with keeping the service in Azure.

#### Network Considerations

The network path is still less natural than Azure hosting. Even if the app can reach Azure VMs securely, the architecture remains cross-platform and less direct than Azure-to-Azure deployment.

#### Pros

- Real app-hosting capability, unlike Bedrock.
- Strong fit if the primary value of the MCP service is tightly coupled to Databricks-native user experiences or AI/data apps.
- Built-in app development and deployment workflow for supported frameworks.

#### Cons

- Weaker natural fit for a general MCP gateway service.
- Still cross-platform relative to Azure VM-hosted SQL Server.
- Requires workspace-level product and operational alignment that this repo does not currently assume.

#### Recommendation Fit

`Situational only. Better than Bedrock as a host, but still weaker than Azure-native hosting for this service.`

## Comparison Matrix

| Strategy | Complexity | Cost | Security | Network Proximity | Operational Fit | Weighted Outcome | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Azure Container Apps | Low | Low | High | High | High | 3.40 | 1st |
| Azure VM | Medium | Medium | High | High | Medium | 3.05 | 2nd |
| Databricks Apps | High | Medium | Medium | Medium | Medium | 2.10 | 3rd |
| AWS ECS or EC2 | High | High | Medium | Low | Medium | 1.90 | 4th |
| AWS Bedrock fit assessment | Very High | High | Low | Low | Low | 1.15 | 5th |

## Recommendation

### Primary Recommendation

Deploy this MCP server to Azure Container Apps.

This is the best current default because it matches the existing repository packaging model, aligns with the documented Azure deployment path, supports managed identity and Key Vault integration, and keeps the service in the same cloud as the Azure VM-hosted SQL Servers. That combination gives the best overall balance of security, simplicity, and cost.

### Secondary Recommendation

Use Azure VM hosting only when you need host-level capabilities that ACA does not provide cleanly.

Examples include mandatory custom security agents, specialized drivers, unusual network controls, or strict operational requirements that depend on direct VM access. In those cases, the extra maintenance burden may be justified.

### Lower-Ranked Options

Databricks Apps is viable only when the MCP service is intentionally part of a Databricks-centered product experience and the team is willing to accept the additional platform and networking complexity.

AWS ECS or EC2 is viable only when AWS-side client locality is more important than SQL-side locality and the organization is willing to build and operate secure cross-cloud networking back into Azure.

AWS Bedrock should not be selected as the hosting strategy for this service. It is an AI platform, not the compute runtime for this MCP server.

## When Not to Choose ACA

Do not choose Azure Container Apps if any of the following are true:

- The service requires host-level agents or OS customization that ACA cannot provide.
- The network design requires VM-native controls or packet-handling behavior that ACA does not support sufficiently.
- The application requires runtime dependencies or privileged operations incompatible with a managed container platform.
- The organization mandates direct VM access for incident handling, forensic tooling, or compliance controls that cannot be met in ACA.

If those constraints are absent, ACA remains the best current default.

## Validation Sources

### Repository Sources

- `README.md`
- `docs/azure-container-apps-deployment.md`
- `docs/DEPLOYMENT-CHECKLIST.md`
- `docs/run-mcp-server-with-docker.md`
- `AGENTS.md`

### Vendor References

- Azure Container Apps overview: https://learn.microsoft.com/en-us/azure/container-apps/overview
- Amazon ECS overview: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/Welcome.html
- Amazon Bedrock overview: https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html
- Databricks Apps overview: https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/

## Bottom Line

If the goal is to deploy this existing MCP server with the least architectural friction while SQL Server remains on Azure VMs, Azure Container Apps is the best approach. Azure VM is the strongest alternative when host control is the deciding requirement. AWS and Databricks options are not impossible, but they are weaker because they move the MCP layer away from the database systems it serves.