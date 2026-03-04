# SQL Server MCP Server

A powerful Model Context Protocol (MCP) server for **SQL Server 2019+** database administration, designed for AI agents like **VS Code**, **Claude**, and **Codex**.

This server exposes a suite of DBA-grade tools to inspect schemas, analyze performance, check security, and troubleshoot issues—all through a safe, controlled interface.

## 🚀 Features

- **Deep Inspection**: Discover schemas, tables, indexes, and their sizes.
- **Logical Modeling**: Analyze foreign keys and table relationships to understand the data model.
- **Performance Analysis**: Detect fragmentation, missing indexes, and buffer pool health.
- **Security Audits**: Analyze database privileges, orphaned users, and authentication modes.
- **Safe Execution**: Read-only by default, with optional write capabilities for specific maintenance tasks.
- **Multiple Transports**: Supports `sse` (Server-Sent Events) and `stdio`. HTTPS is supported via SSL configuration variables.
- **Secure Authentication**: Built-in support for **Azure AD (Microsoft Entra ID)** and standard token auth.
- **HTTPS Support**: Native SSL/TLS support for secure remote connections.
- **SSH Tunneling**: Built-in support for connecting via SSH bastion hosts.
- **Python 3.11**: Built on a stable Python runtime for improved compatibility.
- **Broad Compatibility**: Fully tested with **SQL Server 2019** and **SQL Server 2022**.
- **Comprehensive Testing**: Full unit, integration, stress, and blackbox test suite with automated Docker provisioning.
- **Production Ready**: Verified security audit, connection pooling, error handling, and resource cleanup.
- **Monitoring & Logging**: Structured logging with DEBUG/INFO/WARNING levels, configurable output.

---

## 📦 Installation & Usage

### ⚡ Quickstart: Docker + n8n

Spin up a complete environment with **SQL Server**, **MCP Server**, and **n8n** in one command.

1.  **Download the Compose File**:
    Save [docker-compose-n8n.yml](docker-compose-n8n.yml) to your project directory.

2.  **Start the Stack**:
    ```bash
    docker compose -f docker-compose-n8n.yml up -d
    ```

3.  **Connect n8n**:
    *   Open n8n at [http://localhost:5678](http://localhost:5678).
    *   Add an **AI Agent** node.
    *   Add an **MCP Tool** to the agent.
    *   Set **Source** to `Remote (SSE)`.
    *   Set **URL** to `http://mcp-sqlserver:8085/sse` (Note: use container name and port 8085).
    *   **Execute!** You can now ask the AI agent to use tools like `db_sql2019_list_tables`, `db_sql2019_execute_query`, or `db_sql2019_check_fragmentation`.

---

For detailed deployment instructions on **Azure Container Apps**, **AWS ECS**, and **Docker**, please see our **[Deployment Guide](DEPLOYMENT.md)**.

> **Note**: For details on the required database privileges for read-only and read-write modes, see the **[Database Privileges](DEPLOYMENT.md#database-privileges)** section in the Deployment Guide.

### Option 1: VS Code & Claude Desktop

This section explains how to configure the server for Claude Desktop and VS Code extensions.

1.  **Claude Desktop Integration**:
    Edit your `claude_desktop_config.json` (usually in `~/Library/Application Support/Claude/` on macOS or `%APPDATA%\Claude\` on Windows).

2.  **VS Code Extension Configuration**:
    For extensions like Cline or Roo Code, go to the extension settings in VS Code and look for "MCP Servers" configuration.

You can use either of the following methods to configure the server.

#### Method A: Using Docker (Recommended)
This method ensures you have all dependencies pre-installed. Note the `-i` flag (interactive) and `MCP_TRANSPORT=stdio`.

```json
{
  "mcpServers": {
    "sqlserver": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "--env-file", ".env",
        "harryvaldez/mcp-sql-server:latest"
      ]
    }
  }
}
```

#### Method B: Using Local Python (uv)
If you prefer running the Python code directly and have `uv` installed:

```json
{
  "mcpServers": {
    "sqlserver": {
      "command": "uv",
      "args": ["run", "mcp-sql-server"],
      "env": {
        "DB_SERVER": "localhost",
        "DB_USER": "sa",
        "DB_PASSWORD": "YourPassword123",
        "DB_NAME": "master",
        "DB_DRIVER": "ODBC Driver 17 for SQL Server"
      }
    }
  }
}
```

### Option 2: Docker (Recommended)

The Docker image is available on Docker Hub at `harryvaldez/mcp-sql-server`.

```bash
# 1. Pull the image
docker pull harryvaldez/mcp-sql-server:latest

# 2. Run in HTTP Mode (SSE)
docker run -d \
  --name mcp-sqlserver-http \
  --env-file .env \
  -p 8085:8000 \
  harryvaldez/mcp-sql-server:latest

# 3. Run in Write Mode (HTTP - Secure)
docker run -d \
  --name mcp-sqlserver-write \
  --env-file .env \
  -e MCP_ALLOW_WRITE=true \
  -e MCP_CONFIRM_WRITE=true \
  # ⚠️ Untested / Not Production Ready
  -e FASTMCP_AUTH_TYPE=azure-ad \
  -e FASTMCP_AZURE_AD_TENANT_ID=... \
  -e FASTMCP_AZURE_AD_CLIENT_ID=... \
  -p 8001:8000 \
  harryvaldez/mcp-sql-server:latest
```

### Option 2b: Docker with SSH Tunneling

To connect to a database behind a bastion host (e.g., in a private subnet), you can mount your SSH key and configure the tunnel variables. Set `ALLOW_SSH_AGENT=true` to enable SSH agent forwarding if your SSH key is loaded in your SSH agent:

```bash
docker run -d \
  --name mcp-sqlserver-ssh \
  --env-file .env \
  -v ~/.ssh/id_rsa:/root/.ssh/id_rsa:ro \
  -e SSH_HOST=bastion.example.com \
  -e SSH_USER=ec2-user \
  -e SSH_PKEY="/root/.ssh/id_rsa" \
  -e ALLOW_SSH_AGENT=true \
  -p 8000:8000 \
  harryvaldez/mcp-sql-server:latest
```

**Using Docker Compose:**
The `docker-compose.yml` is configured to use the public image:
```bash
docker compose up -d
```

### Option 3: Local Python (uv)

> **Note:** `SQL_*` aliases (e.g., `SQL_SERVER`) are also supported for backward compatibility.

```bash
# Set connection variables
export DB_SERVER=localhost
export DB_USER=sa
export DB_PASSWORD=YourPassword123
export DB_NAME=master

# Run in HTTP Mode (SSE)
export MCP_TRANSPORT=http
uv run .

# Run in Write Mode (HTTP)
export MCP_TRANSPORT=http
export MCP_ALLOW_WRITE=true
export MCP_CONFIRM_WRITE=true
export FASTMCP_AUTH_TYPE=azure-ad # ⚠️ Untested / Not Production Ready
# ... set auth vars ...
uv run .
```

### Option 4: Node.js (npx)

```bash
# Set connection variables
export DB_SERVER=localhost
export DB_USER=sa
export DB_PASSWORD=YourPassword123
export DB_NAME=master

# Run in HTTP Mode (SSE)
export MCP_TRANSPORT=http
npx .

# Run in Write Mode (HTTP)
export MCP_TRANSPORT=http
export MCP_ALLOW_WRITE=true
export MCP_CONFIRM_WRITE=true
export FASTMCP_AUTH_TYPE=azure-ad # ⚠️ Untested / Not Production Ready
# ... set auth vars ...
npx .
```

### Option 5: n8n Integration (AI Agent)

You can use this MCP server as a "Remote Tool" in n8n to empower AI agents with database capabilities.

1.  **Download Workflow**: Get the [n8n-mcp-workflow.json](n8n-mcp-workflow.json).
2.  **Import to n8n**:
    *   Open your n8n dashboard.
    *   Go to **Workflows** -> **Import from File**.
    *   Select `n8n-mcp-workflow.json`.
3.  **Configure Credentials**:
    *   Open the **AI Agent** node.
    *   Set your **OpenAI** credentials.
    *   If your MCP server is protected, open the **SQL Server MCP** node and update the `Authorization` header in "Header Parameters".
4.  **Run**: Click "Execute Workflow" to test the connection (defaults to `db_sql2019_ping`).

### Troubleshooting n8n Connection

If n8n (Cloud) cannot connect to your local MCP server:
1.  **Public Accessibility**: Your server must be reachable from the internet. `localhost` or local names won't work from n8n Cloud.
2.  **Firewall**: Ensure your firewall allows inbound traffic on the MCP port (default 8085).
    ```powershell
    # Allow port 8085 on Windows
    netsh advfirewall firewall add rule name="MCP Server 8085" dir=in action=allow protocol=TCP localport=8085
    ```
3.  **Quick Fix (ngrok)**: Use [ngrok](https://ngrok.com/) to tunnel your local server to the internet.
    ```bash
    ngrok http 8085
    ```
    Then use the generated `https://....ngrok-free.app/sse` URL in n8n.

---

### ⚡ Testing & Validation

This project includes a comprehensive test suite covering **Unit**, **Integration**, **Stress**, and **Blackbox** tests.

1.  **Prerequisites**:
    *   Docker (for provisioning the temporary SQL Server 2019 container)
    *   Python 3.10+
    *   `pip install -r testing/requirements-test.txt`

2.  **Run Full Test Cycle**:
    ```bash
    # 1. Provision & Populate Test Database
    python testing/setup_sql_server.py
    
    # 2. Run Comprehensive Test Suite
    pytest -v testing/
    
    # Or run specific tests like server info validation
    python testing/test_server_info_mcp.py
    ```

3.  **Verification Coverage**:
    *   ✅ **Unit Tests**: Core connection logic and helper functions, mocked to run without a live database.
    *   ✅ **Integration Tests**: End-to-end verification of all 25+ MCP tools against a live SQL Server 2019 instance.
    *   ✅ **Stress Tests**: Verifies stability under concurrent load (50+ parallel requests).
    *   ✅ **Blackbox Tests**: Validates the MCP protocol implementation and tool discovery.

---

## ⚙️ Configuration

The server is configured entirely via environment variables.

### Performance Limits
To prevent the MCP server from becoming unresponsive or overloading the database, the following safeguards are in place:

*   **Statement Timeout**: Queries are automatically cancelled if they run longer than **120 seconds** (default).
    *   **Behavior**: The MCP tool will return an error: `Query execution timed out.`
    *   **Configuration**: Set `MCP_STATEMENT_TIMEOUT_MS` (milliseconds) to adjust this limit.
*   **Max Rows**: Queries returning large result sets are truncated to **500 rows** (default).
    *   **Configuration**: Set `MCP_MAX_ROWS` to adjust.

### Core Connection
| Variable | Description | Default |
|----------|-------------|---------|
| `DB_SERVER` | SQL Server hostname or IP (also `SQL_SERVER`) | *Required* |
| `DB_PORT` | SQL Server port (also `SQL_PORT`) | `1433` |
| `DB_USER` | SQL User (also `SQL_USER`) | *Required* |
| `DB_PASSWORD` | SQL Password (also `SQL_PASSWORD`) | *Required* |
| `DB_NAME` | Target Database (also `SQL_DATABASE`) | *Required* |
| `DB_DRIVER` | ODBC Driver name (also `SQL_DRIVER`) | `ODBC Driver 17 for SQL Server` |
| `DB_ENCRYPT` | Enable encryption (`yes`/`no`) | `no` |
| `DB_TRUST_CERT` | Trust server certificate (`yes`/`no`) | `yes` |
| `MCP_HOST` | Host to bind the server to | `0.0.0.0` |
| `MCP_PORT` | Internal container port. The host port is typically mapped to this (e.g., 8085 -> 8000). | `8000` (Docker default) |
| `MCP_TRANSPORT` | Transport mode: `sse`, `http` (uses SSE), or `stdio` | `http` |
| `MCP_ALLOW_WRITE` | Enable write tools (`db_sql2019_create_db_user`, etc.) | `false` |
| `MCP_CONFIRM_WRITE` | **Required if ALLOW_WRITE=true**. Safety latch to confirm write mode. | `false` |
| `MCP_STATEMENT_TIMEOUT_MS` | Max execution time per query in milliseconds | `120000` (2 minutes) |
| `MCP_SKIP_CONFIRMATION` | Set to "true" to skip startup confirmation dialog (Windows) | `false` |
| `MCP_LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `MCP_LOG_FILE` | Optional path to write logs to a file | *None* |

### Security Constraints
If `MCP_ALLOW_WRITE=true`, the server enforces the following additional security checks at startup:
1. **Explicit Confirmation**: You must set `MCP_CONFIRM_WRITE=true`.
2. **Mandatory Authentication (HTTP)**: If using `http` transport, you must configure `FASTMCP_AUTH_TYPE` (e.g., `azure-ad`, `oidc`, `jwt`). Write mode over unauthenticated HTTP is prohibited.

> ⚠️ **Warning: Authentication Verification Pending**
> **Token Auth** and **Azure AD Auth** have not been tested and are **not production-ready**.
> While the implementation follows standard FastMCP patterns, end-to-end verification is pending.
> See [Testing & Validation](#testing--validation) for current status.

### 🔐 Authentication & OAuth2

The server supports several authentication modes via `FASTMCP_AUTH_TYPE`.

#### 1. Generic OAuth2 Proxy
Bridge MCP dynamic registration with traditional OAuth2 providers.
Set `FASTMCP_AUTH_TYPE=oauth2`.

| Variable | Description |
|----------|-------------|
| `FASTMCP_OAUTH_AUTHORIZE_URL` | Provider's authorization endpoint |
| `FASTMCP_OAUTH_TOKEN_URL` | Provider's token endpoint |
| `FASTMCP_OAUTH_CLIENT_ID` | Your registered client ID |
| `FASTMCP_OAUTH_CLIENT_SECRET` | Your registered client secret |
| `FASTMCP_OAUTH_BASE_URL` | Public URL of this MCP server |
| `FASTMCP_OAUTH_JWKS_URI` | Provider's JWKS endpoint (for token verification) |
| `FASTMCP_OAUTH_ISSUER` | Expected token issuer |
| `FASTMCP_OAUTH_AUDIENCE` | (Optional) Expected token audience |

#### 2. GitHub / Google (Managed)
Pre-configured OAuth2 providers for simplified setup.
Set `FASTMCP_AUTH_TYPE=github` or `google`.

| Variable | Description |
|----------|-------------|
| `FASTMCP_GITHUB_CLIENT_ID` | GitHub App/OAuth Client ID |
| `FASTMCP_GITHUB_CLIENT_SECRET` | GitHub Client Secret |
| `FASTMCP_GITHUB_BASE_URL` | Public URL of this MCP server |
| `FASTMCP_GOOGLE_CLIENT_ID` | Google OAuth Client ID |
| `FASTMCP_GOOGLE_CLIENT_SECRET` | Google Client Secret |
| `FASTMCP_GOOGLE_BASE_URL` | Public URL of this MCP server |

#### 3. Azure AD (Microsoft Entra ID)
Simplified configuration for Azure AD.
Set `FASTMCP_AUTH_TYPE=azure-ad`.

| Variable | Description |
|----------|-------------|
| `FASTMCP_AZURE_AD_TENANT_ID` | Your Azure Tenant ID |
| `FASTMCP_AZURE_AD_CLIENT_ID` | Your Azure Client ID |
| `FASTMCP_AZURE_AD_CLIENT_SECRET` | (Optional) Client secret for OIDC Proxy mode |
| `FASTMCP_AZURE_AD_BASE_URL` | (Optional) Base URL for OIDC Proxy mode |

#### 4. OpenID Connect (OIDC) Proxy
Standard OIDC flow with discovery.
Set `FASTMCP_AUTH_TYPE=oidc`.

| Variable | Description |
|----------|-------------|
| `FASTMCP_OIDC_CONFIG_URL` | OIDC well-known configuration URL |
| `FASTMCP_OIDC_CLIENT_ID` | OIDC Client ID |
| `FASTMCP_OIDC_CLIENT_SECRET` | OIDC Client Secret |
| `FASTMCP_OIDC_BASE_URL` | Public URL of this MCP server |

#### 5. Pure JWT Verification
Validate tokens signed by known issuers (Resource Server mode).
Set `FASTMCP_AUTH_TYPE=jwt`.

| Variable | Description |
|----------|-------------|
| `FASTMCP_JWT_JWKS_URI` | Provider's JWKS endpoint |
| `FASTMCP_JWT_ISSUER` | Expected token issuer |
| `FASTMCP_JWT_AUDIENCE` | (Optional) Expected token audience |

#### 6. API Key (Static Token)
Simple Bearer token authentication. Ideal for machine-to-machine communication (e.g., n8n, internal services).
Set `FASTMCP_AUTH_TYPE=apikey`.

| Variable | Description |
|----------|-------------|
| `FASTMCP_API_KEY` | The secret key clients must provide in the `Authorization: Bearer <key>` header. |

#### 7. n8n Integration (AI Agent & HTTP Request)
The server is fully compatible with n8n workflows.

**Using the MCP Client Tool (AI Agent):**
1. Run the server with `FASTMCP_AUTH_TYPE=apikey`.
2. In n8n, add an **AI Agent** node.
3. Add the **MCP Tool** to the agent.
4. Set **Source** to `Remote (SSE)`.
5. Set **URL** to `http://<your-ip>:8000/mcp`.
6. Add a header: `Authorization: Bearer <your-api-key>`.

**Using the HTTP Request Node:**
1. Run the server with `FASTMCP_AUTH_TYPE=github` (or another OAuth2 provider).
2. Create an **OAuth2 API** credential in n8n.
3. Use the **HTTP Request** node with that credential to call tools via JSON-RPC.

### HTTPS / SSL
To enable HTTPS, provide both the certificate and key files.

| Variable | Description |
|----------|-------------|
| `MCP_SSL_CERT` | Path to SSL certificate file (`.crt` or `.pem`) |
| `MCP_SSL_KEY` | Path to SSL private key file (`.key`) |

### SSH Tunneling
To access a database behind a bastion host, configure the following SSH variables. The server will automatically establish a secure tunnel.

| Variable | Description | Default |
|----------|-------------|---------|
| `SSH_HOST` | Bastion/Jump host address | *None* |
| `SSH_USER` | SSH username | *None* |
| `SSH_PASSWORD` | SSH password (optional) | *None* |
| `SSH_PKEY` | Path to private key file (optional) | *None* |
| `SSH_PORT` | SSH port | `22` |
| `ALLOW_SSH_AGENT` | Enable SSH agent forwarding (`true`, `1`, `yes`, `on`) | `false` |

> **Note**: When SSH is enabled, the `SQL_SERVER` should point to the database host as seen from the *bastion* (e.g., internal IP or RDS endpoint).

---

## 🔒 Logging & Security

This server implements strict security practices for logging:

- **Sanitized INFO Logs**: High-level operations (like `db_sql2019_run_query` and `db_sql2019_explain_query`) are logged at `INFO` level, but **raw SQL queries and parameters are never included** to prevent sensitive data leaks.
- **Fingerprinting**: Instead of raw SQL, we log SHA-256 fingerprints (`sql_sha256`, `params_sha256`) to allow correlation and debugging without exposing data.
- **Debug Mode**: Raw SQL and parameters are only logged when `MCP_LOG_LEVEL=DEBUG` is explicitly set, and even then, sensitive parameters are hashed where possible.
- **Safe Defaults**: By default, the server runs in `INFO` mode, ensuring production logs are safe.

---

## 🛠️ Tools Reference

### 🏥 Health & Info (Always Available)
- `db_sql2019_ping()`: Basic connectivity probe with server/database metadata.
- `db_sql2019_server_info_mcp()`: SQL Server version/edition + MCP runtime settings.
- `db_sql2019_db_stats(database: str | None = None)`: Core object counts for a database.

### 🔍 Discovery & Query (Always Available)
- `db_sql2019_list_databases()`: List online databases visible to the current login.
- `db_sql2019_list_tables(database_name: str, schema_name: str | None = None)`: List base tables.
- `db_sql2019_get_schema(database_name: str, table_name: str, schema_name: str = "dbo")`: Column metadata.
- `db_sql2019_list_objects(database_name: str, object_type: str = "TABLE", object_name: str | None = None, schema: str | None = None, order_by: str | None = None, limit: int = 50)`: Unified object listing for database/schema/table/view/index/function/procedure/trigger.
- `db_sql2019_execute_query(database_name: str, sql: str, params_json: str | None = None, max_rows: int | None = None)`: Legacy-compatible read/query tool.
- `db_sql2019_run_query(...)`: Supports both signatures:
  - `db_sql2019_run_query(database_name, sql, params_json=None, max_rows=None)`
  - `db_sql2019_run_query(sql, params_json=None, max_rows=None)` (uses default `DB_NAME`)

### ⚡ Analysis & Performance (Always Available)
- `db_sql2019_get_index_fragmentation(database_name: str, schema: str | None = None, min_fragmentation: float = 10.0, min_page_count: int = 100, limit: int = 50)`: Raw fragmentation rows.
- `db_sql2019_analyze_index_health(...)`: Severity summary over fragmented indexes.
- `db_sql2019_check_fragmentation(database_name: str, min_fragmentation: float = 10.0, min_page_count: int = 100, include_recommendations: bool = True)`: Maintenance-focused fragmentation report.
- `db_sql2019_analyze_table_health(database_name: str, schema: str, table_name: str, view: Literal["summary", "standard", "full"] = "standard", fields: str | None = None, token_budget: int | None = None)`: Table size, indexes, FKs, stats, and recommendations with token-aware response shaping, field projection, and budgeted truncation.
- `db_sql2019_show_top_queries(database_name: str, view: Literal["summary", "standard", "full"] = "standard", fields: str | None = None, token_budget: int | None = None)`: Query Store top-query analysis (requires Query Store enabled) with summary/standard/full payload options plus field projection and budgeted truncation.
- `db_sql2019_explain_query(sql: str, analyze: bool = False, output_format: str = "xml")`: XML execution plan.
- `db_sql2019_db_sec_perf_metrics(profile: str = "oltp")`: Security + performance audit snapshot.

### 🧠 Data Model (Always Available)
- `db_sql2019_analyze_logical_data_model(database_name: str, schema: str = "dbo", include_views: bool = False, max_entities: int | None = None, include_attributes: bool = True, view: Literal["summary", "standard", "full"] = "standard", fields: str | None = None, token_budget: int | None = None)`: Entity/relationship model analysis with response shaping for context-window efficiency, field projection, and budgeted truncation.
- `db_sql2019_open_logical_model(database_name: str)`: Generates a shareable data model report URL.
- `db_sql2019_generate_ddl(database_name: str, object_name: str, object_type: str)`: DDL extraction/generation for supported objects.

### 🔧 Write/Admin (Requires `MCP_ALLOW_WRITE=true` and `MCP_CONFIRM_WRITE=true`)
- `db_sql2019_create_db_user(username: str, password: str, privileges: str = "read", database: str | None = None)`
- `db_sql2019_drop_db_user(username: str, database: str | None = None)`
- `db_sql2019_kill_session(session_id: int)`
- `db_sql2019_create_object(object_type: str, object_name: str, schema: str | None = None, parameters: dict | None = None)`
- `db_sql2019_alter_object(object_type: str, object_name: str, operation: str, schema: str | None = None, parameters: dict | None = None)`
- `db_sql2019_drop_object(object_type: str, object_name: str, schema: str | None = None, parameters: dict | None = None)`

---

## 📊 Session Monitor & Web UI
 
 The server includes built-in, real-time web interfaces for monitoring and analysis. These interfaces run on a background HTTP server, even when using the `stdio` transport (Hybrid Mode).
 
 **Default Port**: `8085` (to avoid conflicts with other local services). Configurable via `MCP_PORT`.
 
 ### 1. Real-time Session Monitor
 **Access**: `http://localhost:8085/sessions-monitor`
 
 **Features**:
 - **Real-time Graph**: Visualizes active vs. idle sessions over time.
 - **Auto-Refresh**: Updates every 5 seconds without page reload.
 - **Session Stats**: Instant view of Active, Idle, and Total connections.
 
 ### 2. Logical Data Model Report
 Generated on-demand via the `db_sql2019_analyze_logical_data_model` tool.
 
 **Access**: `http://localhost:8085/data-model-analysis?id=<UUID>`
 
 **Features**:
 - **Interactive ERD**: Zoomable Mermaid.js diagram of your schema.
 - **Health Score**: Automated grading of your schema design.
 - **Issues List**: Detailed breakdown of missing keys, normalization risks, and naming violations.
 
 ---

## 🛠️ Usage Examples

Here are concise examples of calling the most-used tools from an MCP client.

### 1. Check MCP Server Info
**Prompt:** `using sqlserver, call db_sql2019_server_info_mcp() and display results`

**Result:**
```json
{
  "server_name": "sql2019-test",
  "database": "master",
  "server_version_short": "15.0.4455.2",
  "server_edition": "Developer Edition (64-bit)",
  "server_port": 1433
}
```

### 2. Query Store Performance Analysis
**Prompt:** `using sqlserver_readonly, call db_sql2019_show_top_queries(database='USGISPRO_800') and display results`

**Result:**
```json
{
  "database": "USGISPRO_800",
  "query_store_enabled": true,
  "long_running_queries": [
    {
      "query_id": 549115,
      "query_text": "** Encrypted Text **",
      "executions": 1,
      "avg_duration_ms": 342841.5,
      "object_name": "Ad-hoc Query"
    }
  ],
  "summary": {
    "long_running_queries_count": 3,
    "high_cpu_queries_count": 3,
    "high_io_queries_count": 5,
    "total_recommendations": 3
  }
}
```

### 3. Analyze Table Health
**Prompt:** `using sqlserver_readonly, call db_sql2019_analyze_table_health(database_name='USGISPRO_800', schema='dbo', table_name='Account') and display results`

**Result:**
```json
{
  "table_info": {
    "TableName": "Account",
    "SchemaName": "dbo",
    "RowCounts": 3199,
    "TotalSpaceKB": 1496,
    "UsedSpaceKB": 1256,
    "UnusedSpaceKB": 240
  },
  "health_analysis": {
    "constraint_issues": [
      {
        "type": "Unindexed Foreign Key",
        "message": "Warning: Foreign key 'FK_Account_Company' on column 'CompanyID' is not indexed."
      }
    ],
    "index_issues": []
  },
  "recommendations": [
    {
      "severity": "Medium",
      "recommendation": "Create an index on column 'CompanyID' to support the foreign key 'FK_Account_Company'."
    }
  ]
}
```

### 4. Fragmentation Report
**Prompt:** `using sqlserver, call db_sql2019_check_fragmentation(database_name='USGISPRO_800') and display results`

**Result:**
```json
{
  "database": "USGISPRO_800",
  "total_fragmented_indexes": 8,
  "fragmentation_summary": {
    "severe": 0,
    "high": 0,
    "medium": 8,
    "low": 0
  },
  "top_fragmented_indexes": [
    {
      "schema": "dbo",
      "table_name": "DataHierarchy",
      "index_name": "nc_DataHierarchy_status_pp",
      "fragmentation_percent": 24.7,
      "recommended_action": "REORGANIZE"
    }
  ]
}
```

### 5. Interactive ERD Generation
**Prompt:** `using sqlserver, call db_sql2019_open_logical_model(database_name='USGISPRO_800') and display results`

**Result:**
```json
{
  "message": "ERD webpage generated for database 'USGISPRO_800'.",
  "database": "USGISPRO_800",
  "erd_url": "http://localhost:8085/data-model-analysis?id=<UUID>",
  "summary": {
    "entities": 265,
    "relationships": 293,
    "issues_count": {
      "identifiers": 75,
      "relationships": 240
    }
  }
}
```

### 6. Token-Efficient Tool Calls

Use these patterns to keep MCP responses compact in long agent sessions.

**A. Summary-first response:**
```text
using sqlserver_readonly, call db_sql2019_show_top_queries(
  database_name='USGISPRO_800',
  view='summary'
)
```

**B. Project only required fields:**
```text
using sqlserver_readonly, call db_sql2019_show_top_queries(
  database_name='USGISPRO_800',
  view='standard',
  fields='database,summary,long_running_queries.query_id,long_running_queries.avg_duration_ms'
)
```

**C. Enforce a token budget:**
```text
using sqlserver_readonly, call db_sql2019_analyze_logical_data_model(
  database_name='USGISPRO_800',
  view='standard',
  token_budget=1200
)
```

When `token_budget` is applied, responses include `_truncation` metadata so the client can detect compaction and request a deeper follow-up call if needed.

---

## 🧪 Testing

The MCP server includes comprehensive test coverage:

### Running Tests Locally

1. **Provision Test Database** (Docker):
   ```bash
   docker run -e "ACCEPT_EULA=Y" -e "SA_PASSWORD=McpTestPassword123!" \
     --name mcp_sqlserver_test -p 1433:1433 -d \
     mcr.microsoft.com/mssql/server:2019-latest
   ```

2. **Populate Test Data**:
   ```bash
   docker exec -i mcp_sqlserver_test /opt/mssql-tools18/bin/sqlcmd \
     -U SA -P "McpTestPassword123!" < testing/setup_test_database.sql
   ```

3. **Run Unit Tests**:
   ```bash
  python -m pytest testing/unit_test_mocked.py -v
   ```

4. **Run Integration Tests**:
   ```bash
  pytest testing/test_server.py -v
   ```

5. **View Full Test Report**:
   - See [TEST_REPORT.md](TEST_REPORT.md) for comprehensive test results
   - Includes unit tests, integration tests, code review, and security audit

### Test Coverage

- ✅ **Unit Tests**: SQL parsing, connection management, parameter binding
- ✅ **Integration Tests**: Real database operations, schema discovery, tool execution
- ✅ **Security Audit**: SQL injection prevention, readonly enforcement, credential handling
- ✅ **Code Quality**: No hardcoded credentials, proper error handling, connection cleanup
- ✅ **Blackbox Tests**: HTTP API responses, SSE endpoint, authentication

---

## ❓ FAQ & Troubleshooting

### Frequently Asked Questions

**Q: Why is everything prefixed with `db_sql2019_`?**
A: This server is explicitly versioned for SQL Server 2019+ compatibility. This avoids naming conflicts if you run multiple MCP servers for different database versions.

**Q: Can I use this with Azure SQL Database?**
A: Yes! It works with Azure SQL Database and Azure SQL Managed Instance.

**Q: How do I enable write operations?**
A: By default, the server is read-only. To enable write tools (like creating users or killing sessions), set the environment variable `MCP_ALLOW_WRITE=true`.

### Common Issues

**Driver Not Found**
Ensure `ODBC Driver 17 for SQL Server` (or 18) is installed. The Docker image includes this by default.

**Connection Timeout**
Check your firewall settings (port 1433).

---

## 📬 Contact & Support

For comments, issues, or feature enhancements, please contact the maintainer or submit an issue to the repository:

- **Repository**: https://github.com/harryvaldez/mcp-sql-server
- **Maintainer**: Harry Valdez
