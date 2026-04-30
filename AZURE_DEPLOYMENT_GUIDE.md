# Azure Deployment Guide: SQL Server MCP Server

This guide analyzes deployment options for hosting the SQL Server MCP Server as a remote service in Azure, with a focus on cost, security, and management overhead.

## Target Architecture

- **Format**: Docker Container
- **Connectivity**: Remote MCP (HTTPS)
- **Authentication**: Azure Entra ID (OAuth 2.0)
- **Database Connectivity**: Private/Public SQL Server (Instance 1 & 2)

---

## Deployment Options Analysis

### 1. Azure App Service for Containers (Recommended)
**Ranking: #1**

- **Cost**: Medium (~$12-$45/month for B1/P1v2 slots).
- **Management Overhead**: Low (PaaS).
- **Security**: High. Built-in **Authentication (EasyAuth)** allows for Azure Entra ID integration without changing the application code.
- **Pros**: SSL termination, easy scaling, integrated auth.
- **Cons**: Fixed monthly cost even if idle.

### 2. Azure Container Instances (ACI)
**Ranking: #2**

- **Cost**: Low (Pay-per-second, ~$10-$30/month if running 24/7).
- **Management Overhead**: Very Low (Serverless).
- **Security**: Medium. Does not provide built-in OAuth/Entra integration. Requires a sidecar (e.g., Nginx with OAuth) or code-level auth.
- **Pros**: No infrastructure management.
- **Cons**: Connectivity can be tricky for remote MCP without a public IP/FQDN and SSL.

### 3. Azure VM with Docker Runtime
**Ranking: #3**

- **Cost**: Low to Medium (Starting at ~$8/month for B-series).
- **Management Overhead**: High. Requires OS patching, Docker updates, and manual SSL configuration (Let's Encrypt).
- **Security**: Low to Medium. Requires manual hardening and firewall management.
- **Pros**: Bare-metal control.
- **Cons**: High operational burden.

### 4. Azure Kubernetes Service (AKS)
**Ranking: #4**

- **Cost**: High (Management plane is free, but node costs are higher).
- **Management Overhead**: Maximum.
- **Security**: Enterprise-grade.
- **Pros**: Highly scalable.
- **Cons**: Significant overkill for a single MCP server.

---

## Summary Table & Ranking

| Option | Cost (Priority) | Management Overhead | Security | Overall Rank |
| :--- | :--- | :--- | :--- | :--- |
| **Azure App Service** | Medium | Low | **High (EasyAuth)** | **1** |
| **Azure Container Instances** | **Low** | **Very Low** | Medium | 2 |
| **VM with Docker** | Low | High | Medium | 3 |
| **AKS** | High | Maximum | High | 4 |

---

## Recommendations & Assumptions

### Assumptions
1.  **Usage**: The MCP server will be used by multiple remote clients (n8n, Cursor, etc.).
2.  **Authentication**: Azure Entra ID is the mandatory standard for enterprise security.
3.  **Connectivity**: The server must be accessible via HTTPS.

### Recommendation: Azure App Service for Containers
Provision an **Azure App Service (Linux)** using the **Basic (B1)** or **Premium (P1v2)** tier. 

**Implementation Steps:**
1.  **Build & Push**: Build the Docker image and push it to Azure Container Registry (ACR).
2.  **Provision**: Create a Web App for Containers pointing to the ACR image.
3.  **Authentication**: Enable **App Service Authentication** in the Azure Portal. Select "Azure Event ID" (Microsoft) as the provider.
4.  **Environment Variables**: Configure the `SQL_SERVER_0*`, `SQL_USER_0*`, etc., in the "Application Settings" (these are injected as environment variables).
5.  **VNet Integration**: If the SQL Server is in a private network, enable VNet integration on the App Service.

### Authentication Detail (OAuth)
By using Azure App Service's built-in authentication, the MCP server itself doesn't need to handle OAuth 2.0 flow. The App Service acts as a reverse proxy, validating tokens before they reach the Python process.
- Clients (n8n, Cursor) will first authenticate against Entra ID to get a Bearer token.
- They will then send this token in the `Authorization` header.
- The App Service will validate the token and forward the request to the MCP server.
