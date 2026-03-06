# Deployment Guide for SQL Server MCP Server

This guide provides instructions for deploying the SQL Server MCP Server to various environments, including local development, Docker, Azure Container Apps, and AWS ECS.

## 📋 Prerequisites

Before deploying, ensure you have:
1.  **SQL Server Database**: A running instance (2019+ or Azure SQL).
2.  **Connection Details**: Host, Port (1433), User (sa), Password, Database.
3.  **Container Registry**: A place to push your Docker image (e.g., Docker Hub, ACR, ECR) if deploying to the cloud.

---

## 🌐 Remote Access & Networking

### Exposing the Server
By default, the server binds to `0.0.0.0` (all interfaces) when running via Docker or if `MCP_HOST` is set. To allow external tools (like n8n Cloud) to connect:

1.  **Public IP / DNS**: Ensure your machine has a public IP or dynamic DNS hostname.
2.  **Firewall Rules**: Open the port (default 8085) in your OS firewall.
    *   **Windows (PowerShell)**:
        ```powershell
        netsh advfirewall firewall add rule name="MCP Server 8085" dir=in action=allow protocol=TCP localport=8085
        ```
    *   **Linux (ufw)**:
        ```bash
        sudo ufw allow 8085/tcp
        ```
3.  **Tunnels (Alternative)**: Use a tunneling service like [ngrok](https://ngrok.com/) to bypass firewall/NAT issues during development.
    ```bash
    ngrok http 8085
    ```

---

## 💻 Local Development

### Option 1: Python (uv)
Best for rapid development and testing.

```bash
# 1. Install dependencies
uv sync

# 2. Set environment variables
$env:DB_SERVER="localhost"
$env:DB_USER="sa"
$env:DB_PASSWORD="YourPassword123"
$env:DB_NAME="master"
$env:DB_DRIVER="ODBC Driver 17 for SQL Server"

# 3. Run server
uv run mcp-sql-server
```

### Option 2: Docker Compose
Best for testing the containerized environment locally.

```bash
# 1. Update docker-compose.yml with your database credentials if needed

# 2. Build and run
docker compose up --build
```

---

## 🧪 Testing & Validation

This project includes a comprehensive test suite covering **Unit**, **Integration**, **Stress**, and **Blackbox** tests.

### Quick Start: Run Test Suite

1.  **Prerequisites**:
    *   Docker (for provisioning the temporary SQL Server 2019 container)
    *   Python 3.11+
    *   Dependencies: `pip install -r requirements.txt`

2.  **Run Full Test Cycle**:
    ```bash
    # 1. Provision SQL Server 2019 Container
    docker run -e "ACCEPT_EULA=Y" -e "SA_PASSWORD=McpTestPassword123!" \
      --name mcp_test_db -p 1433:1433 -d \
      mcr.microsoft.com/mssql/server:2019-latest
    
    # 2. Wait for container to be ready (~30 seconds)
    sleep 30
    
    # 3. Populate test database
    docker exec -i mcp_test_db /opt/mssql-tools18/bin/sqlcmd \
      -U SA -P "McpTestPassword123!" < setup_test_simple.sql
    
    # 4. Run comprehensive test suite
    python test_runner.py
    ```

3.  **Test Coverage**:
    * ✅ **Unit Tests**: SQL parsing, connection logic, parameter binding (no DB required)
    * ✅ **Integration Tests**: Real tool execution against live database
    * ✅ **Security Tests**: SQL injection prevention, readonly enforcement
    * ✅ **Code Quality**: Connection cleanup, error handling, no hardcoded credentials
    * ✅ **Blackbox Tests**: HTTP API responses and authentication

4.  **Review Test Results**:
    - See [TEST_REPORT.md](TEST_REPORT.md) for detailed findings
    - **Status**: ✅ READY FOR PRODUCTION (with minor optional improvements noted)

### Cleanup After Testing
```bash
docker stop mcp_test_db
docker rm mcp_test_db
```

---

## ☁️ Azure Container Apps (ACA)

### Features
*   **Serverless**: Scale to zero capability (though minReplicas=1 is recommended).
*   **Secure**: Secrets management for SQL passwords.
*   **Health Checks**: Built-in liveness and readiness probes.

### Deployment Steps (CLI)

1.  **Login to Azure**:
    ```bash
    az login
    ```

2.  **Create Container App**:
    ```bash
    az containerapp create \
      --name mcp-sqlserver \
      --resource-group MyResourceGroup \
      --environment MyEnvironment \
      --image harryvaldez/mcp_sqlserver:latest \
      --target-port 8000 \
      --ingress 'external' \
      --env-vars \
        DB_SERVER=myserver.database.windows.net \
        DB_USER=myadmin \
        DB_PASSWORD=secret-password-here \
        DB_NAME=master \
        MCP_ALLOW_WRITE=false
    ```

---

## ☁️ AWS ECS (Fargate)

### Features
*   **Serverless Compute**: No EC2 instances to manage.
*   **Logging**: Integrated with CloudWatch Logs.
*   **IAM Roles**: Least privilege access for ECS tasks.

### Deployment Steps

1.  **Create Task Definition**:
    *   Image: `harryvaldez/mcp_sqlserver:latest`
    *   Port Mappings: 8000
    *   Environment Variables: `DB_SERVER`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`.

2.  **Configure Network**:
    *   VPC: Must have connectivity to your RDS/SQL Server.
    *   Security Groups: Allow inbound port 1433 from the ECS tasks to the RDS instance.

3.  **Deploy Service**: Create an ECS Service using Fargate.

---

## 🔒 Security Checklist

When deploying to production, verify the following:

1. **Authentication**: If using HTTP transport, enable an auth provider (Azure AD, GitHub, Google, or API Key).
   * Set `FASTMCP_AUTH_TYPE` to your preferred mode.
   * For machine-to-machine (e.g., n8n), use `apikey` with `FASTMCP_API_KEY`.
   * For human-in-the-loop, use `github`, `google`, or `azure-ad`.
2. **Network**: Ensure the container can reach your SQL Server database.
   * **Azure**: Use VNet injection if using Azure SQL Managed Instance or private endpoints.
   * **AWS**: Ensure Security Groups allow inbound port 1433 from the ECS tasks.
3. **Secrets**: Never hardcode passwords. Use Azure Key Vault or AWS Secrets Manager where possible.
4. **Write Access**: Keep `MCP_ALLOW_WRITE=false` unless explicitly required for maintenance tasks.

---

## ⚙️ Environment Variables

Key environment variables supported by the server:
- `DB_SERVER` SQL Server hostname (also `SQL_SERVER`).
- `DB_PORT` SQL Server port, default 1433 (also `SQL_PORT`).
- `DB_USER` SQL User (also `SQL_USER`).
- `DB_PASSWORD` SQL Password (also `SQL_PASSWORD`).
- `DB_NAME` Target Database (also `SQL_DATABASE`).
- `DB_DRIVER` ODBC Driver name (also `SQL_DRIVER`), default `ODBC Driver 17 for SQL Server`.
- `MCP_TRANSPORT` Transport mode: `sse`, `http` (default), or `stdio`.
- `MCP_HOST` Host for HTTP transport, default `0.0.0.0`.
- `MCP_PORT` Port for HTTP transport, default `8000` (Container internal).
- `MCP_ALLOW_WRITE` Allow write operations, default `false`.

### Optional: FastMCP Skills Provider

If you want to expose local skill directories as MCP resources (separate from SQL tools), configure a FastMCP Skills Provider in your server code.

```python
from fastmcp import FastMCP
from fastmcp.server.providers.skills import VSCodeSkillsProvider

mcp = FastMCP("SQL Server MCP")
mcp.add_provider(
    VSCodeSkillsProvider(
        supporting_files="template",  # production default: compact list_resources()
        reload=False,                  # production default: avoid per-request directory re-scan
    )
)
```

Deployment guidance:
- Use `supporting_files="template"` for production to reduce resource listing size.
- Use `reload=True` only while actively editing skills during development.
- Keep Skills Provider behavior separate from SQL audit logging (`MCP_AUDIT_LOG_*`).
---

## ✅ Production Readiness Checklist

Before deploying to production, ensure:

- [ ] **Database Connection**: Tested with production database
- [ ] **Read/Write Roles**: Created and tested (see **Database Privileges** below)
- [ ] **Environment Variables**: Set all required variables (see .env.example)
- [ ] **Security**: Enabled authentication (FASTMCP_AUTH_TYPE)
- [ ] **Logging**: Configured log file path and level
- [ ] **Testing**: Run full test suite and reviewed TEST_REPORT.md
- [ ] **SSH Tunneling**: Configured if needed for remote access
- [ ] **Monitoring**: Set up logs collection and alerting
- [ ] **Backup Plan**: Document rollback procedures
- [ ] **Access Control**: Restrict MCP server access by IP/network

---

## 🔒 Security Hardening

1. **Enable Authentication**:
   ```bash
   export FASTMCP_AUTH_TYPE=azure-ad
   export FASTMCP_AZURE_AD_TENANT_ID=your-tenant-id
   export FASTMCP_AZURE_AD_CLIENT_ID=your-client-id
   ```

2. **Use SSH Tunnel** (for remote databases):
   ```bash
   export SSH_HOST=bastion.example.com
   export SSH_USER=ec2-user
   export SSH_PKEY=/path/to/private/key
   ```

3. **Minimal Read-Only Access**:
   - Deploy with `MCP_ALLOW_WRITE=false` by default
   - Require explicit env var change + container restart to enable writes
   - Audit write operations in logs

---

## 🗝️ Database Privileges

Configure two roles aligned to MCP modes:

### Read-Only User
Minimal privileges for safe querying.

```sql
USE [master];
CREATE LOGIN [mcp_readonly] WITH PASSWORD = 'StrongPassword123!';
GRANT VIEW SERVER STATE TO [mcp_readonly];

DECLARE @sql NVARCHAR(MAX) = N'';

SELECT @sql += '
USE [' + name + '];
CREATE USER mcp_readonly FOR LOGIN mcp_readonly;
ALTER ROLE db_datareader ADD MEMBER mcp_readonly;
GRANT VIEW DEFINITION TO mcp_readonly;'
FROM sys.databases
WHERE database_id > 4  -- skips master, model, msdb, tempdb
  AND state_desc = 'ONLINE';

EXEC sp_executesql @sql;
```

### Read/Write User
Full DML privileges and ability to create objects.

```sql
USE [master];
CREATE LOGIN [mcp_rw] WITH PASSWORD = 'StrongPassword123!';
GRANT VIEW SERVER STATE TO [mcp_rw];

DECLARE @sql NVARCHAR(MAX) = N'';

SELECT @sql += '
USE [' + name + '];
CREATE USER mcp_readonly FOR LOGIN mcp_rw;
ALTER ROLE db_datareader ADD MEMBER mcp_rw;
ALTER ROLE db_writer ADD MEMBER mcp_rw;
GRANT VIEW DEFINITION TO mcp_rw;
GRANT CREATE TABLE TO mcp_rw;
GRANT CREATE VIEW TO mcp_rw;
GRANT CREATE PROCEDURE TO mcp_rw;
GRANT CREATE FUNCTION TO mcp_rw;'
FROM sys.databases
WHERE database_id > 4  -- skips master, model, msdb, tempdb
  AND state_desc = 'ONLINE';

EXEC sp_executesql @sql;
```
