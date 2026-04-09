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
    * Supported runtime values are: `none`, `apikey`, `oidc`, `jwt`, `azure-ad`, `github`, `google`.
    * If `FASTMCP_AUTH_TYPE=apikey`, `FASTMCP_API_KEY` is mandatory and startup fails fast when missing.
    * `MCP_ALLOW_QUERY_TOKEN_AUTH` only applies when auth is enabled.
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

### Startup Argument Mapping

Canonical startup entrypoints are:

- `python server_startup.py`
- `python -m mcp_sqlserver.server`

Both paths call `run_server_entrypoint` in `mcp_sqlserver/server.py`, which maps startup settings deterministically as follows:

- Always passes `transport` from `MCP_TRANSPORT`.
- If `MCP_TRANSPORT=http`, also passes `host` from `MCP_HOST` and `port` from `MCP_PORT`.
- For non-HTTP transports (for example `stdio`), only `transport` is passed.

### Health Probes

When running in HTTP transport, use `GET /health` for liveness/readiness checks.

- Expected status code: `200`
- Expected payload fields: `status`, `service`, `transport`
- Sensitive values such as database credentials and API keys are intentionally omitted.

Example probe:

```bash
curl -s http://127.0.0.1:8000/health
```

### Tool Search Transform Settings

Optional runtime settings for FastMCP tool-search:

- `MCP_TOOL_SEARCH_ENABLED`
- `MCP_TOOL_SEARCH_STRATEGY` (`regex` or `bm25`)
- `MCP_TOOL_SEARCH_MAX_RESULTS`
- `MCP_TOOL_SEARCH_ALWAYS_VISIBLE`
- `MCP_TOOL_SEARCH_TOOL_NAME`
- `MCP_TOOL_CALL_TOOL_NAME`

If the installed FastMCP runtime does not provide transform classes, startup logs a warning and continues without transform activation.

### Provider-Layer Transform Suite Settings

The server supports a provider-layer transform pipeline for broader FastMCP guidance coverage.

- `MCP_TRANSFORM_LAYERS_ENABLED` enables/disables layer assembly.
- `MCP_TRANSFORM_LAYER_ORDER` controls layer order when enabled.
- Per-layer feature flags:
    - `MCP_TRANSFORM_VISIBILITY_ENABLED`
    - `MCP_TRANSFORM_NAMESPACE_ENABLED`
    - `MCP_TRANSFORM_TOOL_TRANSFORMATION_ENABLED`
    - `MCP_TRANSFORM_RESOURCES_AS_TOOLS_ENABLED`
    - `MCP_TRANSFORM_PROMPTS_AS_TOOLS_ENABLED`
    - `MCP_TRANSFORM_CODE_MODE_ENABLED`

Layer-specific controls:

- Visibility: `MCP_TRANSFORM_VISIBILITY_ALLOWLIST`, `MCP_TRANSFORM_VISIBILITY_DENYLIST`
- Namespace: `MCP_TRANSFORM_NAMESPACE_PREFIX`
- Tool transformation: `MCP_TRANSFORM_TOOL_NAME_MAP`, `MCP_TRANSFORM_TOOL_DESCRIPTION_MAP`
- Code mode: `MCP_TRANSFORM_CODE_MODE_POLICY`

Operational defaults:

- Feature flags for all transform layers are default-off.
- Unavailable transform APIs are logged and skipped without terminating startup.

Recommended rollout order:

1. Enable `MCP_TRANSFORM_VISIBILITY_ENABLED` only.
2. Enable `MCP_TRANSFORM_NAMESPACE_ENABLED` after verifying client compatibility.
3. Enable `MCP_TRANSFORM_TOOL_TRANSFORMATION_ENABLED` only after downstream name-mapping validation.
4. Evaluate `MCP_TRANSFORM_RESOURCES_AS_TOOLS_ENABLED` and `MCP_TRANSFORM_PROMPTS_AS_TOOLS_ENABLED` in non-production first.
5. Enable `MCP_TRANSFORM_CODE_MODE_ENABLED` only with explicit policy review.

## Release Gate Matrix

| Gate | Depends On | Pass Criteria | Fail Criteria | Commands |
|------|------------|---------------|---------------|----------|
| `GATE-STARTUP` | None | Startup config and entrypoint tests pass. | Any failure in startup config tests. | `python -m pytest tests/test_server_startup_config.py -q` |
| `GATE-AUTH` | `GATE-STARTUP` | Blackbox HTTP auth behavior and hardening tests pass. | Any auth or caller-identity regression failure. | `python -m pytest tests/test_blackbox_http.py tests/test_hardening_controls.py -q` |
| `GATE-TRANSFORM` | `GATE-STARTUP` | Transform/route behavior and readonly guard tests pass. | Any transform/health/readonly regression failure. | `python -m pytest tests/test_server_startup_config.py tests/test_readonly_sql.py -q` |
| `GATE-INTEGRATION` | `GATE-AUTH`, `GATE-TRANSFORM` | Full final validation bundle passes. | Any command in the integration bundle fails. | `python -m pytest tests/test_server_startup_config.py tests/test_blackbox_http.py tests/test_hardening_controls.py tests/test_readonly_sql.py -q` |

## Rollout Sequence and Rollback

### Stage 1: Local Validation

- Run gate checks in dependency order: `GATE-STARTUP` -> `GATE-AUTH` and `GATE-TRANSFORM` -> `GATE-INTEGRATION`.
- Capture command outputs to timestamped files under `testing/`.

Rollback triggers:

- Startup tests fail.
- Auth denial or caller-identity tests fail.
- Readonly guard tests fail.

Rollback actions:

- Revert to prior deployment artifact (last known good image/tag or commit).
- Restore prior environment values for `MCP_TRANSPORT`, `FASTMCP_AUTH_TYPE`, and related auth settings.

### Stage 2: Staging Validation

- Deploy candidate artifact to staging with production-like environment settings.
- Run `GATE-INTEGRATION` test bundle and perform health/auth probes.

Recommended transform smoke sequence before promotion:

1. Enable `MCP_TRANSFORM_VISIBILITY_ENABLED=true` only.
2. Then enable `MCP_TRANSFORM_NAMESPACE_ENABLED=true` with a safe prefix.
3. Then enable `MCP_TRANSFORM_TOOL_TRANSFORMATION_ENABLED=true` with a minimal name map.

Expected compatibility probe results during staging smoke:

- `GET /health` returns `200`.
- `GET /mcp` without a session ID may return `400` and is acceptable for raw HTTP compatibility probing.
- No startup crash occurs when each transform stage is enabled.

Rollback triggers:

- `GET /health` returns non-200 or malformed payload.
- Auth probe behavior deviates from expected mode.
- Any integration gate failure.

Rollback actions:

- Roll back staging to previous artifact.
- Restore previous environment snapshot (including `MCP_TRANSPORT`, `FASTMCP_AUTH_TYPE`, `FASTMCP_API_KEY` references).

### Stage 3: Production Promotion

- Promote only after all staging checks pass.
- Execute post-release probes immediately after deployment.

Rollback triggers:

- Health probe failure.
- Unexpected unauthenticated access in protected mode.
- Runtime error spikes tied to startup/auth/transform changes.

Rollback actions:

- Roll back production artifact to prior stable release.
- Restore prior environment configuration.
- Re-run `GATE-STARTUP` and `GATE-AUTH` in staging before retry.

## Post-Release Verification

Run all of the following in deployment environment:

- `GET /health` returns `200` with `status=ok`.
- Sample MCP endpoint request succeeds under expected auth mode.
- In `apikey` mode, invalid token request is denied (401/403).

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
GRANT VIEW ANY DATABASE TO [mcp_readonly];
GRANT VIEW ANY definition to [mcp_readonly];
GRANT view server state to [mcp_readonly];

DECLARE @sql NVARCHAR(MAX) = N'';

SELECT @sql += '
EXEC(N''USE ' + QUOTENAME(name) + ';
CREATE USER mcp_readonly FOR LOGIN mcp_readonly;
ALTER ROLE db_datareader ADD MEMBER mcp_readonly;
GRANT VIEW DEFINITION TO mcp_readonly;'');'
FROM sys.databases
WHERE state_desc = 'ONLINE';

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
EXEC(N''USE ' + QUOTENAME(name) + ';
CREATE USER mcp_rw FOR LOGIN mcp_rw;
ALTER ROLE db_datareader ADD MEMBER mcp_rw;
ALTER ROLE db_datawriter ADD MEMBER mcp_rw;
GRANT VIEW DEFINITION TO mcp_rw;
GRANT CREATE TABLE TO mcp_rw;
GRANT CREATE VIEW TO mcp_rw;
GRANT CREATE PROCEDURE TO mcp_rw;
GRANT CREATE FUNCTION TO mcp_rw;
GRANT VIEW ANY DATABASE TO mcp_rw;
GRANT VIEW ANY definition to mcp_rw;
GRANT view server state to mcp_rw;'');'
FROM sys.databases
WHERE database_id > 0  -- skips master, model, msdb, tempdb
  AND state_desc = 'ONLINE';

EXEC sp_executesql @sql;
```
