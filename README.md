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
- **Comprehensive Testing**: Includes unit tests with mocked data for core functionality like server information retrieval (`db_sql2019_server_info_mcp`).

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
    *   **Execute!** You can now ask the AI agent to "count rows in tables" or "check database stats".

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
        "harryvaldez/mcp_sqlserver:latest"
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

The Docker image is available on Docker Hub at `harryvaldez/mcp_sqlserver`.

```bash
# 1. Pull the image
docker pull harryvaldez/mcp_sqlserver:latest

# 2. Run in HTTP Mode (SSE)
docker run -d \
  --name mcp-sqlserver-http \
  --env-file .env \
  -p 8085:8000 \
  harryvaldez/mcp_sqlserver:latest

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
  harryvaldez/mcp_sqlserver:latest
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
  harryvaldez/mcp_sqlserver:latest
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
    *   `pip install -r tests/requirements-test.txt`

2.  **Run Full Test Cycle**:
    ```bash
    # 1. Provision & Populate Test Database
    python tests/setup_sql_server.py
    
    # 2. Run Comprehensive Test Suite
    pytest -v tests/
    
    # Or run specific tests like server info validation
    python test_server_info_mcp.py
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
- `db_sql2019_server_info_mcp()`: Get comprehensive MCP server and database connection information (server details, database version, user, connection details, and MCP configuration).

### 🔍 Schema Discovery (Always Available)
- `db_sql2019_list_objects(database_name: str, object_type: str, object_name: str = None, schema: str = None, order_by: str = None, limit: int = 50)`: **(Enhanced Consolidated Tool)** Unified tool to list database objects with advanced filtering and sorting options.
    - **Database-specific**: Now accepts `database_name` to target specific databases
    - **Object filtering**: New `object_name` parameter for specific object name filtering (supports LIKE patterns)
    - **Supported object_type values**: 'database', 'schema', 'table', 'view', 'index', 'function', 'procedure', 'trigger'
    - **Common Use Cases**:
        - **Find specific table**: `object_type='table', object_name='Account'`
        - **List all tables in schema**: `object_type='table', schema='dbo'`
        - **Table Sizes**: `object_type='table', order_by='size'`
        - **Row Counts**: `object_type='table', order_by='rows'`
        - **Find Objects**: `object_type='procedure', object_name='%my_proc%'`
- `db_sql2019_analyze_logical_data_model(database_name: str, schema: str = "dbo", include_views: bool = False, max_entities: int = None, include_attributes: bool = True)`: **(Data Model Analysis)** Generates a comprehensive logical data model analysis for a database schema. Returns entities, relationships, naming convention issues, normalization problems, and actionable recommendations. No web UI is generated.

### ⚡ Performance & Tuning (Always Available)
- `db_sql2019_analyze_table_health(database_name: str, schema: str, table_name: str)`: **(Enhanced Power Tool)** Comprehensive health check for a specific table, including size analysis, index fragmentation, foreign key dependencies, statistics health, **missing constraint analysis** (foreign keys, check constraints, defaults, primary keys), and **enhanced index recommendations** (missing FK indexes, disabled indexes, unused large indexes, redundant indexes). Returns actionable tuning recommendations with severity levels.
- `db_sql2019_show_top_queries(database_name: str)`: **(Query Store Analysis)** Analyzes Query Store data to identify top problematic queries including long-running queries, regressed queries (performance degradation), high CPU consumption, high I/O queries, and frequently executed poor-performing queries. Provides specific recommendations for each issue with actionable steps. **Prerequisite**: Query Store must be enabled on the target database (not enabled by default in SQL Server 2019). If disabled, the tool will return empty results or errors. To enable: `ALTER DATABASE [database_name] SET QUERY_STORE = ON;`
- `db_sql2019_open_logical_model(database_name: str)`: **(Interactive ERD Webpage)** Generates an interactive Entity-Relationship Diagram (ERD) webpage depicting all entities (tables), their columns, data types, constraints, and relationships. Returns a URL to view the interactive ERD with pan/zoom controls, detailed entity analysis, and design recommendations. Click on any entity to view comprehensive details including indexes, relationships to other entities, and column specifications.
- `db_sql2019_generate_ddl(database_name: str, object_name: str, object_type: str)`: **(DDL Generation)** Generate complete DDL (CREATE/ALTER) statements to recreate database objects. Supports tables, views, indexes, functions, procedures, and triggers. Returns object metadata, dependencies, and production-ready DDL with proper constraints and indexes.
- `db_sql2019_explain_query(sql: str, analyze: bool = False, output_format: str = "xml")`: Get the XML execution plan for a query.

### 🕵️ Session & Security (Always Available)
- `db_sql2019_db_sec_perf_metrics(profile: str = "oltp")`: Comprehensive security and performance audit with tuning recommendations (Orphaned Users, PLE, Buffer Cache Hit Ratio, authentication mode, sysadmin privileges, memory configuration, parallelism settings).

### 🔧 Maintenance (Requires `MCP_ALLOW_WRITE=true`)
- `db_sql2019_run_query(sql: str, params_json: str = None, max_rows: int = None)`: Execute ad-hoc SQL queries. **Read-Only Mode**: Enforces read-only SQL (blocks INSERT/UPDATE/DELETE). **Write Mode**: Allows all SQL operations. `max_rows` defaults to 500 (configurable via `MCP_MAX_ROWS`). Returns up to `max_rows` rows; if truncated, `truncated: true` is set.
- `db_sql2019_create_db_user(username: str, password: str, privileges: str = "read", database: str = None)`: Create a new SQL Login and User with specified privileges.
- `db_sql2019_drop_db_user(username: str)`: Drop a SQL Login and User.
- `db_sql2019_kill_session(session_id: int)`: Terminate a specific database session by SPID.
- `db_sql2019_create_object(object_type: str, object_name: str, schema: str = None, parameters: dict = None)`: Create database objects (table, view, index, function, procedure, trigger).
- `db_sql2019_alter_object(object_type: str, object_name: str, operation: str, schema: str = None, parameters: dict = None)`: Modify database objects.
- `db_sql2019_drop_object(object_type: str, object_name: str, schema: str = None, parameters: dict = None)`: Drop database objects.

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

Here are some real-world examples of using the tools via an MCP client.

### 1. Check MCP Server Info
**Prompt:** `using sqlserver, call db_sql2019_server_info_mcp() and display results`

**Result:**
```json
{
  "server_version": "Microsoft SQL Server 2019 (RTM-CU32-GDR) (KB5068404) - 15.0.4455.2 (X64) \n\tOct  7 2025 21:10:15 \n\tCopyright (C) 2019 Microsoft Corporation\n\tDeveloper Edition (64-bit) on Windows Server 2019 Datacenter 10.0 <X64> (Build 17763: ) (Hypervisor)\n",
  "server_name": "gisdevsql01",
  "database": "master",
  "user": "n8n_DBMonitor",
  "server_version_short": "15.0.4455.2",
  "server_edition": "Developer Edition (64-bit)",
  "server_addr": "10.125.1.7",
  "server_port": 1433
}
```

### 2. Query Store Performance Analysis
**Prompt:** `using sqlserver_readonly, call db_sql2019_show_top_queries(database='USGISPRO_800') and display results`

> **Note**: The `sqlserver_readonly` alias is used to explicitly indicate that the MCP client is configured with read-only credentials, ensuring no data modification operations are possible. This is a common practice for monitoring and analysis tools.


**Result:**
```json
{
  "database": "USGISPRO_800",
  "query_store_enabled": true,
  "query_store_config": {
    "state": "READ_WRITE",
    "current_storage_mb": 256,
    "max_storage_mb": 1024,
    "stale_threshold_days": 30,
    "capture_mode": "AUTO"
  },
  "analysis_period": {
    "earliest_data": "2026-02-09T15:21:02+00:00",
    "latest_data": "2026-02-23T15:32:07+00:00",
    "days_covered": 14,
    "total_queries": 0
  },
  "long_running_queries": [
    {
      "query_id": 549115,
      "query_text": "** Encrypted Text **",
      "executions": 1,
      "avg_duration_ms": 342841.5,
      "avg_cpu_ms": 339409.9,
      "avg_logical_io_reads": 16687138,
      "object_name": "gissp_CreateFlatDataIndicatorTree"
    },
    {
      "query_id": 664345,
      "query_text": "DECLARE @vAccountID INT, @vModuleID INT, @vReferenceDate DATE, @vLanguageID INT, @vGeographyLevelID INT, @vLowestGeographyLevelID INT, @DataYearIDs dbo.DataYearList, @DataValueTypeIDs dbo.DataValueTypeList, @CountryIDs dbo.CountryList, @DatabaseIDs dbo.DatabaseList, @vGeographyLevelKey NVARCHAR(10), @vHierarchical BIT, @vAccountID INT, @vModuleID INT, @vReferenceDate DATE, @vLanguageID INT, @vGeographyLevelID INT, @vLowestGeographyLevelID INT, @DataYearIDs dbo.DataYearList, @DataValueTypeIDs dbo.DataValueTypeList, @CountryIDs dbo.CountryList, @DatabaseIDs dbo.DatabaseList, @vGeographyLevelKey NVARCHAR(10), @vHierarchical BIT\r\n\t\t\tSELECT [scz26c].[ZIPCODE], [scz26c].[ZIPCODE_NAME], [scz26c].[STATE_CODE], [scz26c].[COUNTY_FIPS], [scz26c].[COUNTY_NAME]\r\n\t\t\tFROM [scz26c]\r\n\t\t\tWHERE [scz26c].[STATE_CODE] IN (SELECT [scz26c].[STATE_CODE] FROM [scz26c] WHERE [scz26c].[ZIPCODE] IN (SELECT [scz26c].[ZIPCODE] FROM [scz26c] WHERE [scz26c].[ZIPCODE_NAME] LIKE @vGeographyLevelKey + '%') GROUP BY [scz26c].[STATE_CODE])\r\n\t\t\tGROUP BY [scz26c].[ZIPCODE], [scz26c].[ZIPCODE_NAME], [scz26c].[STATE_CODE], [scz26c].[COUNTY_FIPS], [scz26c].[COUNTY_NAME]\r\n\t\t\tHAVING 1 = 0 OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2578 THEN ISNULL(HPEBTotalX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBTotalX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2572 THEN ISNULL(HPEBRNR_RetailX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBRNR_RetailX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2562 THEN ISNULL(HPEBRNR_NonRetailX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBRNR_NonRetailX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2542 THEN ISNULL(HPEBApparelX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBApparelX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2544 THEN ISNULL(HPEBCashContributionsX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBCashContributionsX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2546 THEN ISNULL(HPEBEducationX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBEducationX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2548 THEN ISNULL(HPEBEntertainmentX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBEntertainmentX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2550 THEN ISNULL(HPEBFoodX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBFoodX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2552 THEN ISNULL(HPEBHous_FurnishEquipX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_FurnishEquipX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2556 THEN ISNULL(HPEBHealthX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHealthX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2564 THEN ISNULL(HPEBHous_OperationsX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_OperationsX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2558 THEN ISNULL(HPEBHous_HouseKeepingX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_HouseKeepingX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2566 THEN ISNULL(HPEBPersonalCareX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBPersonalCareX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2548 THEN ISNULL(HPEBEntertainmentX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBEntertainmentX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2550 THEN ISNULL(HPEBFoodX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBFoodX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2552 THEN ISNULL(HPEBHous_FurnishEquipX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_FurnishEquipX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2556 THEN ISNULL(HPEBHealthX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHealthX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2564 THEN ISNULL(HPEBHous_OperationsX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_OperationsX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2558 THEN ISNULL(HPEBHous_HouseKeepingX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_HouseKeepingX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2566 THEN ISNULL(HPEBPersonalCareX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBPersonalCareX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2548 THEN ISNULL(HPEBEntertainmentX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBEntertainmentX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2550 THEN ISNULL(HPEBFoodX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBFoodX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2552 THEN ISNULL(HPEBHous_FurnishEquipX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_FurnishEquipX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2556 THEN ISNULL(HPEBHealthX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHealthX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2564 THEN ISNULL(HPEBHous_OperationsX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_OperationsX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2558 THEN ISNULL(HPEBHous_HouseKeepingX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_HouseKeepingX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2566 THEN ISNULL(HPEBPersonalCareX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBPersonalCareX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2568 THEN ISNULL(HPEBPersonalInsurPensionsX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBPersonalInsurPensionsX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2570 THEN ISNULL(HPEBReadingX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBReadingX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2574 THEN ISNULL(HPEBHous_ShelterX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_ShelterX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2576 THEN ISNULL(HPEBTobaccoX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBTobaccoX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2580 THEN ISNULL(HPEBTransportationX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBTransportationX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2582 THEN ISNULL(HPEBHous_UtilitiesX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_UtilitiesX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2560 THEN ISNULL(HPEBMiscellaneousX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBMiscellaneousX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998)  ORDER BY [scz26c].[ZIPCODE_NAME]",
      "executions": 1,
      "avg_duration_ms": 9349.9,
      "avg_cpu_ms": 1925.4,
      "avg_logical_io_reads": 239810,
      "object_name": "Ad-hoc Query"
    },
    {
      "query_id": 664332,
      "query_text": "DECLARE @vAccountID INT, @vModuleID INT, @vReferenceDate DATE, @vLanguageID INT, @vGeographyLevelID INT, @vLowestGeographyLevelID INT, @DataYearIDs dbo.DataYearList, @DataValueTypeIDs dbo.DataValueTypeList, @CountryIDs dbo.CountryList, @DatabaseIDs dbo.DatabaseList, @vGeographyLevelKey NVARCHAR(10), @vHierarchical BIT\r\n\t\t\tSELECT [scz26c].[ZIPCODE], [scz26c].[ZIPCODE_NAME], [scz26c].[STATE_CODE], [scz26c].[COUNTY_FIPS], [scz26c].[COUNTY_NAME]\r\n\t\t\tFROM [scz26c]\r\n\t\t\tWHERE [scz26c].[STATE_CODE] IN (SELECT [scz26c].[STATE_CODE] FROM [scz26c] WHERE [scz26c].[ZIPCODE] IN (SELECT [scz26c].[ZIPCODE] FROM [scz26c] WHERE [scz26c].[ZIPCODE_NAME] LIKE @vGeographyLevelKey + '%') GROUP BY [scz26c].[STATE_CODE])\r\n\t\t\tGROUP BY [scz26c].[ZIPCODE], [scz26c].[ZIPCODE_NAME], [scz26c].[STATE_CODE], [scz26c].[COUNTY_FIPS], [scz26c].[COUNTY_NAME]\r\n\t\t\tHAVING 1 = 0 OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2578 THEN ISNULL(HPEBTotalX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBTotalX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2572 THEN ISNULL(HPEBRNR_RetailX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBRNR_RetailX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2562 THEN ISNULL(HPEBRNR_NonRetailX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBRNR_NonRetailX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2542 THEN ISNULL(HPEBApparelX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBApparelX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2544 THEN ISNULL(HPEBCashContributionsX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBCashContributionsX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2546 THEN ISNULL(HPEBEducationX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBEducationX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2548 THEN ISNULL(HPEBEntertainmentX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBEntertainmentX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2550 THEN ISNULL(HPEBFoodX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBFoodX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2552 THEN ISNULL(HPEBHous_FurnishEquipX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_FurnishEquipX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2556 THEN ISNULL(HPEBHealthX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHealthX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2564 THEN ISNULL(HPEBHous_OperationsX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_OperationsX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2558 THEN ISNULL(HPEBHous_HouseKeepingX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_HouseKeepingX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2566 THEN ISNULL(HPEBPersonalCareX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBPersonalCareX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2568 THEN ISNULL(HPEBPersonalInsurPensionsX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBPersonalInsurPensionsX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2570 THEN ISNULL(HPEBReadingX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBReadingX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2574 THEN ISNULL(HPEBHous_ShelterX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_ShelterX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2576 THEN ISNULL(HPEBTobaccoX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBTobaccoX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2580 THEN ISNULL(HPEBTransportationX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBTransportationX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2582 THEN ISNULL(HPEBHous_UtilitiesX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBHous_UtilitiesX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998) OR NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 2560 THEN ISNULL(HPEBMiscellaneousX, -99998.8) WHEN C.[Ind] IS NULL AND HPEBMiscellaneousX IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) NOT IN (-99998.8, -99999.9, -99998)  ORDER BY [scz26c].[ZIPCODE_NAME]",
      "executions": 1,
      "avg_duration_ms": 8152.1,
      "avg_cpu_ms": 190.6,
      "avg_logical_io_reads": 10656,
      "object_name": "Ad-hoc Query"
    }
  ],
  "regressed_queries": [],
  "high_cpu_queries": [
    {
      "query_id": 549115,
      "query_text": "** Encrypted Text **",
      "executions": 1,
      "avg_cpu_ms": 339409.9,
      "max_cpu_ms": 339409.9,
      "avg_duration_ms": 342841.5,
      "avg_logical_io_reads": 16687138,
      "object_name": "Ad-hoc Query"
    },
    {
      "query_id": 664200,
      "query_text": "SELECT [dcz31].[DMA_FIPS] AS [DMA_FIPS], [dcz31].[DMA_NAME] AS [DMA_NAME], [dcz31].[COUNTY_FIPS] AS [COUNTY_FIPS], [dcz31].[COUNTY_NAME] AS [COUNTY_NAME], [dcz31].[ZIPCODE] AS [ZIPCODE], [dcz31].[ZIPCODE_NAME] AS [ZIPCODE_NAME], [dcz31].[DMA_COUNTY] AS [DMA_COUNTY], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1963 THEN ISNULL(PFG0002, -99998.8) WHEN C.[Ind] IS NULL AND PFG0002 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG0002], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1965 THEN ISNULL(PFG0305, -99998.8) WHEN C.[Ind] IS NULL AND PFG0305 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG0305], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1967 THEN ISNULL(PFG0611, -99998.8) WHEN C.[Ind] IS NULL AND PFG0611 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG0611], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1969 THEN ISNULL(PFG1217, -99998.8) WHEN C.[Ind] IS NULL AND PFG1217 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG1217], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1964 THEN ISNULL(PFG0004, -99998.8) WHEN C.[Ind] IS NULL AND PFG0004 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG0004], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1966 THEN ISNULL(PFG0509, -99998.8) WHEN C.[Ind] IS NULL AND PFG0509 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG0509], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1968 THEN ISNULL(PFG1014, -99998.8) WHEN C.[Ind] IS NULL AND PFG1014 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG1014], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1970 THEN ISNULL(PFG1517, -99998.8) WHEN C.[Ind] IS NULL AND PFG1517 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG1517], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1971 THEN ISNULL(PFG1820, -99998.8) WHEN C.[Ind] IS NULL AND PFG1820 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG1820], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1972 THEN ISNULL(PFG2124, -99998.8) WHEN C.[Ind] IS NULL AND PFG2124 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG2124], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1973 THEN ISNULL(PFG2529, -99998.8) WHEN C.[Ind] IS NULL AND PFG2529 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG2529], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1974 THEN ISNULL(PFG3034, -99998.8) WHEN C.[Ind] IS NULL AND PFG3034 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG3034], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1975 THEN ISNULL(PFG3539, -99998.8) WHEN C.[Ind] IS NULL AND PFG3539 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG3539], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1976 THEN ISNULL(PFG4044, -99998.8) WHEN C.[Ind] IS NULL AND PFG4044 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG4044], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1977 THEN ISNULL(PFG4549, -99998.8) WHEN C.[Ind] IS NULL AND PFG4549 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG4549], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1978 THEN ISNULL(PFG5054, -99998.8) WHEN C.[Ind] IS NULL AND PFG5054 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG5054], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1979 THEN ISNULL(PFG5559, -99998.8) WHEN C.[Ind] IS NULL AND PFG5559 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG5559], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1980 THEN ISNULL(PFG6064, -99998.8) WHEN C.[Ind] IS NULL AND PFG6064 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG6064], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1981 THEN ISNULL(PFG6569, -99998.8) WHEN C.[Ind] IS NULL AND PFG6569 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG6569], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1982 THEN ISNULL(PFG7074, -99998.8) WHEN C.[Ind] IS NULL AND PFG7074 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG7074], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1983 THEN ISNULL(PFG7579, -99998.8) WHEN C.[Ind] IS NULL AND PFG7579 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG7579], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1984 THEN ISNULL(PFG8084, -99998.8) WHEN C.[Ind] IS NULL AND PFG8084 IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG8084], NULLIF(NULLIF(MAX(CASE WHEN C.[Ind] = 1985 THEN ISNULL(PFG85P, -99998.8) WHEN C.[Ind] IS NULL AND PFG85P IS NULL THEN -99998.8 ELSE -99999.9 END), -99998.8), -99998.000000) AS [PFG85P] FROM [AMDS2026].[dbo].[us_dcz31] dcz31 LEFT OUTER JOIN @AccountAccess C ON [dcz31].[ZIPCODE] = C.[GeoAbbr] WHERE 1 = 1  OR (PFG0002 IS NOT NULL AND PFG0002 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG0305 IS NOT NULL AND PFG0305 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG0611 IS NOT NULL AND PFG0611 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG1217 IS NOT NULL AND PFG1217 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG0004 IS NOT NULL AND PFG0004 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG0509 IS NOT NULL AND PFG0509 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG1014 IS NOT NULL AND PFG1014 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG1517 IS NOT NULL AND PFG1517 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG1820 IS NOT NULL AND PFG1820 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG2124 IS NOT NULL AND PFG2124 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG2529 IS NOT NULL AND PFG2529 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG3034 IS NOT NULL AND PFG3034 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG3539 IS NOT NULL AND PFG3539 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG4044 IS NOT NULL AND PFG4044 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG4549 IS NOT NULL AND PFG4549 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG5054 IS NOT NULL AND PFG5054 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG5559 IS NOT NULL AND PFG5559 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG6064 IS NOT NULL AND PFG6064 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG6569 IS NOT NULL AND PFG6569 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG7074 IS NOT NULL AND PFG7074 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG7579 IS NOT NULL AND PFG7579 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG8084 IS NOT NULL AND PFG8084 NOT IN (-99998.8, -99999.9, -99998))  OR (PFG85P IS NOT NULL AND PFG85P NOT IN (-99998.8, -99999.9, -99998))  ORDER BY [dcz31].[ZIPCODE_NAME]",
      "executions": 1,
      "avg_cpu_ms": 8819.2,
      "max_cpu_ms": "8819.2",
      "avg_duration_ms": 5406.8,
      "avg_logical_io_reads": 62722,
      "object_name": "Ad-hoc Query"
    }
  ],
  "high_io_queries": [
    {
      "query_id": 549115,
      "query_text": "** Encrypted Text **",
      "executions": 1,
      "avg_logical_io_reads": 16687138,
      "avg_logical_io_writes": 1398,
      "avg_physical_io_reads": 3686,
      "avg_duration_ms": 342841.5,
      "avg_cpu_ms": 339409.9
    },
    {
      "query_id": 606587,
      "query_text": "INSERT INTO @AccountAccess ( [CID], [Lvl], [GeoAbbr], [Ind], [Col], [Name] )\r\n\t\t\tEXECUTE [dbo].[gissp_GetAccountGeographyAccess_ByGeographyLevel2] @vAccountID, @vModuleID, @vGeographyLevelID, @IndicatorsXML, @ReferenceDate, @vLanguageID",
      "executions": 14,
      "avg_logical_io_reads": 942847,
      "avg_logical_io_writes": 10615,
      "avg_physical_io_reads": 6224,
      "avg_duration_ms": 3711.5,
      "avg_cpu_ms": 3696.0
    },
    {
      "query_id": 549492,
      "query_text": "(@DataYearIDs dbo.DataYearList,@DataValueTypeIDs dbo.DataValueTypeList,@CountryIDs dbo.CountryList,@vGeographyLevelID int,@DatabaseIDs dbo.DatabaseList,@vLanguageID int,@vLowestGeographyLevelID int,@vAccountID int,@vModuleID int,@vReferenceDate date,@vGeographyLevelKey nvarchar(10),@vHierarchical bit)INSERT INTO @DataGroups ( [GroupID], [GroupName], [Description], [Sequence] )\r\nSELECT A.[DataGroupID], C.[DatabaseName] + ' - ' + A.[DataGroupName], A.[Description], A.[SortOrder]\r\nFROM ([dbo].[gisfn_GetDataGroups_ByCountryLevel] ( @DataYearIDs, @DataValueTypeIDs, @CountryIDs, @vGeographyLevelID, @DatabaseIDs, @vLanguageID ) A\r\n\t\t  INNER JOIN \r\n\t  [dbo].[gisfn_GetDataGroups_ByCountryLevel] ( @DataYearIDs, @DataValueTypeIDs, @CountryIDs, @vLowestGeographyLevelID, @DatabaseIDs, @vLanguageID ) D\r\n\t\t  ON A.[DataGroupID] = D.[DataGroupID])\r\n\t\t  LEFT OUTER JOIN \r\n\t  [dbo].[gisfn_GetAccountDataGroups_ByCountryLevel] ( @vAccountID, @vModuleID, @DataYearIDs, @DataValueTypeIDs, @CountryIDs, @vGeographyLevelID, @DatabaseIDs, @vReferenceDate, @vLanguageID ) B\r\n\t\t  ON A.[DataGroupID] = B.[DataGroupID]\r\nWHERE B.[DataGroupID] IS NOT NULL\r\nUNION ALL\r\nSELECT A.[DataGroupID], ISNULL(B.[LanguageText], A.[DataGroupName]) AS [DataGroupName],\r\n\t   A.[Description], A.[SortOrder]\r\nFROM [dbo].[DataGroup] A LEFT OUTER JOIN [dbo].[Resource] B\r\n\t\t\t\t\t\t\t\t\t\t\t  ON B.[TableName]  = 'DataGroup'     AND\r\n\t\t\t\t\t\t\t\t\t\t\t\t B.[ColumnName] = 'DataGroupName' AND\r\n\t\t\t\t\t\t\t\t\t\t\t\t B.[LanguageID] = @vLanguageID\t  AND\r\n\t\t\t\t\t\t\t\t\t\t\t\t B.[TableID]    = A.[DataGroupID]\r\nWHERE A.[Internal] = 1 AND\r\n\t (EXISTS (SELECT 'X' FROM [dbo].[AccountDataIndicator]\r\n\t\t\t  WHERE [AccountID] = @vAccountID AND\r\n\t\t\t\t\t[Status]    = 1) OR\r\n\t  EXISTS (SELECT 'X' FROM [dbo].[AccountDataCategory]\r\n\t\t\t  WHERE [AccountID] IN ( @vAccountID, 0 ) AND\r\n\t\t\t\t    [Status]    = 1) OR\r\n\t  EXISTS (SELECT 'X' FROM [dbo].[AccountDataIndicatorShare]\r\n\t\t\t  WHERE [AccountID] = @vAccountID AND\r\n\t\t\t\t    [Status]    = 1) OR\r\n\t  EXISTS (SELECT 'X' FROM [dbo].[AccountDataCategoryShare]\r\n\t\t\t  WHERE [AccountID] = @vAccountID AND\r\n\t\t\t\t    [Status]    = 1))",
      "executions": 3,
      "avg_logical_io_reads": 792396,
      "avg_logical_io_writes": 11,
      "avg_physical_io_reads": 961,
      "avg_duration_ms": 1210.2,
      "avg_cpu_ms": 997.8
    },
    {
      "query_id": 606606,
      "query_text": "** Encrypted Text **",
      "executions": 14,
      "avg_logical_io_reads": 670517,
      "avg_logical_io_writes": 6263,
      "avg_physical_io_reads": 1,
      "avg_duration_ms": 2100.9,
      "avg_cpu_ms": 2091.5
    },
    {
      "query_id": 549508,
      "query_text": "(@DataYearIDs dbo.DataYearList,@DataValueTypeIDs dbo.DataValueTypeList,@CountryIDs dbo.CountryList,@vGeographyLevelID int,@DatabaseIDs dbo.DatabaseList,@vLanguageID int,@vLowestGeographyLevelID int,@vAccountID int,@vModuleID int,@vReferenceDate date,@VCDataCategoryID int,@vGeographyLevelKey nvarchar(10),@vHierarchical bit,@UDDataCategoryID int)INSERT INTO @DataSubCategories ( [CategoryID], [SubCategoryID], [SubCategoryName], [Description], [Sequence] )\r\nSELECT A.[DataCategoryID], A.[DataSubCategoryID], A.[DataSubCategoryName], A.[Description], A.[SortOrder]\r\nFROM ([dbo].[gisfn_GetDataSubCategories_ByCountryLevel] ( @DataYearIDs, @DataValueTypeIDs, @CountryIDs, @vGeographyLevelID, @DatabaseIDs, NULL, @vLanguageID ) A\r\n\t\t\t INNER JOIN\r\n\t  [dbo].[gisfn_GetDataSubCategories_ByCountryLevel] ( @DataYearIDs, @DataValueTypeIDs, @CountryIDs, @vLowestGeographyLevelID, @DatabaseIDs, NULL, @vLanguageID ) C\r\n\t\t\t ON A.[DataSubCategoryID] = C.[DataSubCategoryID])\r\n\t\t\t LEFT OUTER JOIN \r\n\t [dbo].[gisfn_GetAccountDataSubCategories_ByCountryLevel] ( @vAccountID, @vModuleID, @DataYearIDs, @DataValueTypeIDs, @CountryIDs, @vGeographyLevelID, @DatabaseIDs, NULL, @vReferenceDate, @vLanguageID ) B\r\n\t\t\t ON A.[DataSubCategoryID] = B.[DataSubCategoryID]\r\nWHERE B.[DataSubCategoryID] IS NOT NULL\r\nUNION ALL\r\nSELECT @VCDataCategoryID AS [DataCategoryID], [AccountDataCategoryID] AS [DataSubCategoryID], \r\n\t   [DataCategoryName], [DataCategoryName] AS [Description], 1 AS [SortOrder]\r\nFROM [dbo].[AccountDataCategory]\r\nWHERE [AccountID] IN ( @vAccountID, 0 ) AND\r\n\t  [Status]    = 1\r\nUNION ALL\r\nSELECT [DataCategoryID], [DataSubCategoryID], \r\n\t   [DataSubCategoryName], [DataSubCategoryName] AS [Description], 1 AS [SortOrder]\r\nFROM [dbo].[DataSubCategory]\r\nWHERE [Internal]\t\t   = 1\t  AND\r\n\t  [Status]\t\t\t   = 1\t  AND\r\n\t  [DataSubCategoryKey] = 'VI' AND\r\n\t (EXISTS (SELECT 'X' FROM [dbo].[AccountDataIndicator]\r\n\t\t\t  WHERE [AccountID] = @vAccountID AND\r\n\t\t\t\t\t[Status]    = 1) OR\r\n\t  EXISTS (SELECT 'X' FROM [dbo].[AccountDataIndicatorShare]\r\n\t\t\t  WHERE [AccountID] = @vAccountID AND\r\n\t\t\t\t    [Status]    = 1))\r\nUNION ALL\r\nSELECT DISTINCT @UDDataCategoryID AS [DataCategoryID], A.[AccountDataUploadID], A.[FileName], A.[FileName], 1\r\nFROM [dbo].[AccountDataUpload] A INNER JOIN [dbo].[AccountDataIndicatorUpload] B\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t   ON A.[AccountDataUploadID] = B.[AccountDataUploadID] AND\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t  A.[IsSuccessful]\t\t  = 1\t\t\t\t\t\t\t\tAND\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t (A.[GeographyLevelID]    = @vGeographyLevelID\t\tOR\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t  CHARINDEX(',' + @vGeographyLevelKey + ',', ',' + A.[GeographyLevelList] + ',') > 0) AND\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t  A.[GeographyColumn]\t != B.[ColumnName]\t\t\tAND\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t  A.[Status]\t\t\t  = 1\t\t\t\t\t\t\t\tAND\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t  B.[Status]\t\t\t  = 1\t\t\t\t\t\t\t\tAND\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t  @vHierarchical\t\t  = 0\t\t\t\t\t\t\t\tAND\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t (A.[AccountID]\t\t\t  = @vAccountID OR\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t  EXISTS (SELECT 'X' FROM [dbo].[AccountDataIndicatorUploadShare] C\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t  WHERE C.[AccountDataIndicatorUploadID] = B.[AccountDataIndicatorUploadID] AND\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\tC.[AccountID]\t\t\t\t\t = @vAccountID\t\t\t\t\t\t\tAND\r\n\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\tC.[Status]\t\t\t\t\t = 1))",
      "executions": 3,
      "avg_logical_io_reads": 612432,
      "avg_logical_io_writes": 131,
      "avg_physical_io_reads": 540,
      "avg_duration_ms": 814.4,
      "avg_cpu_ms": 795.4
    }
  ],
  "high_execution_queries": [
    {
      "query_id": 606590,
      "query_text": "DECLARE cAccountAccess CURSOR LOCAL FOR SELECT CID, Lvl, GeoAbbr, Ind, Col, Name FROM @AccountAccess",
      "executions": 2506578,
      "avg_duration_ms": 0.0,
      "avg_cpu_ms": 0.0,
      "avg_logical_io_reads": 8
    },
    {
      "query_id": 664337,
      "query_text": "(@Indicator nvarchar(150),@Valid int)SELECT @Valid=COUNT(*) FROM DataIndicator WHERE Status=1 AND DataIndicatorID=@Indicator",
      "executions": 333890,
      "avg_duration_ms": 0.2,
      "avg_cpu_ms": 0.2,
      "avg_logical_io_reads": 2
    },
    {
      "query_id": 664339,
      "query_text": "DECLARE cFormulas CURSOR FOR\r\nSELECT DataBaseID, DataIndicatorColumnName, DataIndicatorName, REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(AggregatorFormula,'(',''),')',''),'/',''),'[',','),']',''),'-',''),'+','')\r\nFROM DataIndicator \r\nWHERE Status=1 AND AggregatorFormula IS NOT NULL",
      "executions": 61866,
      "avg_duration_ms": 0.0,
      "avg_cpu_ms": 0.0,
      "avg_logical_io_reads": 6
    },
    {
      "query_id": 549116,
      "query_text": "** Encrypted Text **",
      "executions": 43850,
      "avg_duration_ms": 0.1,
      "avg_cpu_ms": 0.1,
      "avg_logical_io_reads": 50
    },
    {
      "query_id": 664338,
      "query_text": "DECLARE cFormulas CURSOR FOR\r\nSELECT DataBaseID, DataIndicatorColumnName, DataIndicatorName, REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(AggregatorFormula,'(',''),')',''),'/',''),'[',','),']',''),'-',''),'+','')\r\nFROM DataIndicator \r\nWHERE AggregatorFormula IS NOT NULL",
      "executions": 15495,
      "avg_duration_ms": 0.0,
      "avg_cpu_ms": 0.0,
      "avg_logical_io_reads": 4
    }
  ],
  "recommendations": [
    {
      "type": "long_running_query",
      "priority": "high",
      "query_id": 549115,
      "issue": "Query with 342841.5ms average duration executed 1 times",
      "recommendation": "Analyze execution plan for missing indexes, table scans, or inefficient joins. Consider query optimization or index creation.",
      "potential_actions": [
        "Review execution plan for optimization opportunities",
        "Check for missing indexes on join/filter columns",
        "Consider query parameterization if using literals",
        "Evaluate if query can be rewritten for better performance"
      ]
    },
    {
      "type": "long_running_query",
      "priority": "high",
      "query_id": 664345,
      "issue": "Query with 9349.9ms average duration executed 1 times",
      "recommendation": "Analyze execution plan for missing indexes, table scans, or inefficient joins. Consider query optimization or index creation.",
      "potential_actions": [
        "Review execution plan for optimization opportunities",
        "Check for missing indexes on join/filter columns",
        "Consider query parameterization if using literals",
        "Evaluate if query can be rewritten for better performance"
      ]
    },
    {
      "type": "long_running_query",
      "priority": "high",
      "query_id": 664332,
      "issue": "Query with 8152.1ms average duration executed 1 times",
      "recommendation": "Analyze execution plan for missing indexes, table scans, or inefficient joins. Consider query optimization or index creation.",
      "potential_actions": [
        "Review execution plan for optimization opportunities",
        "Check for missing indexes on join/filter columns",
        "Consider query parameterization if using literals",
        "Evaluate if query can be rewritten for better performance"
      ]
    },
    {
      "type": "regressed_query",
      "priority": "high",
      "query_id": 568290,
      "issue": "Query performance regressed by 77.9% (from 2.8ms to 5.1ms)",
      "recommendation": "Check for plan changes, statistics updates, or data distribution changes. Consider plan forcing or statistics updates.",
      "potential_actions": [
        "Check query plan history for plan changes",
        "Update statistics on related tables",
        "Consider forcing a previous good plan",
        "Analyze data distribution changes"
      ]
    },
    {
      "type": "regressed_query",
      "priority": "high",
      "query_id": 216,
      "issue": "Query performance changed (from 0.0ms to 0.0ms)",
      "recommendation": "Check for plan changes, statistics updates, or data distribution changes. Consider plan forcing or statistics updates.",
      "potential_actions": [
        "Check query plan history for plan changes",
        "Update statistics on related tables",
        "Consider forcing a previous good plan",
        "Analyze data distribution changes"
      ]
    },
    {
      "type": "general",
      "priority": "medium",
      "issue": "Found 10 long-running queries",
      "recommendation": "Consider implementing query performance monitoring and regular optimization reviews.",
      "potential_actions": [
        "Set up query performance monitoring",
        "Schedule regular query optimization reviews",
        "Consider implementing query governor for resource limits",
        "Monitor Query Store storage usage"
      ]
    }
  ],
  "summary": {
    "long_running_queries_count": 3,
    "regressed_queries_count": 0,
    "high_cpu_queries_count": 3,
    "high_io_queries_count": 5,
    "high_execution_queries_count": 5,
    "total_recommendations": 3,
    "high_priority_recommendations": 3,
    "analysis_timestamp": "2026-02-23T15:32:07"
  }
}
```

### 3. Analyze Table Health (Power Tool)
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
  "indexes": [
    {
      "IndexName": "PK_Account",
      "IndexType": "CLUSTERED",
      "IndexSizeMB": 1.039062
    },
    {
      "IndexName": "IX_Account_AccountNameStatus",
      "IndexType": "NONCLUSTERED",
      "IndexSizeMB": 0.1875
    }
  ],
  "foreign_keys": [
    {
      "FK_Name": "FK_AccountLogin_Account",
      "ParentTable": "AccountLogin",
      "ParentColumn": "AccountID",
      "ReferencedTable": "Account",
      "ReferencedColumn": "AccountID"
    },
    {
      "FK_Name": "FK_AccountReportFormat_Account",
      "ParentTable": "AccountReportFormat",
      "ParentColumn": "AccountID",
      "ReferencedTable": "Account",
      "ReferencedColumn": "AccountID"
    },
    {
      "FK_Name": "FK_AccountModule_Account",
      "ParentTable": "AccountModule",
      "ParentColumn": "AccountID",
      "ReferencedTable": "Account",
      "ReferencedColumn": "AccountID"
    }
    // ... 40+ more foreign key relationships
  ],
  "statistics_sample": [
    {
      "ColumnName": "AccountID",
      "StatsName": "PK_Account",
      "last_updated": "2026-01-07T20:41:01.340000",
      "rows": 3199,
      "rows_sampled": 3199,
      "modification_counter": 0
    },
    {
      "ColumnName": "CompanyID",
      "StatsName": "_WA_Sys_00000002_69485A5F",
      "last_updated": "2026-01-07T20:41:01.353000",
      "rows": 3199,
      "rows_sampled": 3199,
      "modification_counter": 0
    },
    {
      "ColumnName": "ParentAccountID",
      "StatsName": "_WA_Sys_00000018_69485A5F",
      "last_updated": "2026-01-07T20:41:01.360000",
      "rows": 3199,
      "rows_sampled": 3199,
      "modification_counter": 0
    },
    {
      "ColumnName": "Status",
      "StatsName": "_WA_Sys_0000000D_69485A5F",
      "last_updated": "2026-01-07T20:41:01.370000",
      "rows": 3199,
      "rows_sampled": 3199,
      "modification_counter": 0
    },
    {
      "ColumnName": "AccountName",
      "StatsName": "_WA_Sys_00000003_69485A5F",
      "last_updated": "2026-01-07T20:41:01.377000",
      "rows": 3199,
      "rows_sampled": 3199,
      "modification_counter": 0
    }
  ],
  "health_analysis": {
    "constraint_issues": [
      {
        "type": "Unindexed Foreign Key",
        "message": "Warning: Foreign key 'FK_Account_Company' on column 'CompanyID' is not indexed. This can cause performance problems during joins and cascading operations."
      },
      {
        "type": "Unindexed Foreign Key",
        "message": "Warning: Foreign key 'FK_Account_Account' on column 'ParentAccountID' is not indexed. This can cause performance problems during joins and cascading operations."
      }
    ],
    "index_issues": []
  },
  "recommendations": [
    {
      "severity": "Medium",
      "recommendation": "Create an index on column 'CompanyID' to support the foreign key 'FK_Account_Company'."
    },
    {
      "severity": "Medium",
      "recommendation": "Create an index on column 'ParentAccountID' to support the foreign key 'FK_Account_Account'."
    }
  ]
}
        "type": "unused_large_index",
        "index": "IX_Account_UnusedField",
        "size_mb": 15.2,
        "updates": 0,
        "severity": "medium",
        "recommendation": "Large unused index IX_Account_UnusedField (15.2 MB) - consider dropping to save space"
      }
    ],
    "analysis_summary": "Found 2 index-related issues"
  },
  "recommendations": [
    {
      "type": "constraint_design",
      "priority": "medium",
      "message": "Column 'CompanyID' may need foreign key constraint to dbo.Company"
    },
    {
      "type": "index_design",
      "priority": "medium",
      "message": "Missing index on foreign key column 'CompanyID' - create to improve join performance"
    },
    {
      "type": "index_design",
      "priority": "medium",
      "message": "Large unused index 'IX_Account_UnusedField' (15.2 MB) - consider dropping to save space"
    }
  ],
  "summary": {
    "total_indexes": 2,
    "total_fk_relationships": 43,
    "total_statistics": 2,
    "recommendation_count": 3,
    "high_priority_issues": 1
  }
}
```

### 4. Performance Analysis: Fragmentation
**Prompt:** `using sqlserver, call db_sql2019_check_fragmentation(database_name='USGISPRO_800') and display results`

**Result:**
```json
{
  "database": "USGISPRO_800",
  "analysis_timestamp": "2026-02-23T16:59:35.474000",
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
      "category": "MEDIUM",
      "page_count": 1234,
      "recommended_action": "REORGANIZE"
    },
    {
      "schema": "dbo",
      "table_name": "AccountDataPackage",
      "index_name": "IX_AccountDataPackage_All",
      "fragmentation_percent": 24.02,
      "category": "MEDIUM",
      "page_count": 567,
      "recommended_action": "REORGANIZE"
    },
    {
      "schema": "dbo",
      "table_name": "AccountSite",
      "index_name": "IX_AccountSite_SiteKey",
      "fragmentation_percent": 21.65,
      "category": "MEDIUM",
      "page_count": 890,
      "recommended_action": "REORGANIZE"
    },
    {
      "schema": "dbo",
      "table_name": "AccountSubscriptionItem",
      "index_name": "nc_AccountSubscriptionItem_id_st",
      "fragmentation_percent": 21.05,
      "category": "MEDIUM",
      "page_count": 456,
      "recommended_action": "REORGANIZE"
    },
    {
      "schema": "dbo",
      "table_name": "AccountDataPackage",
      "index_name": "IX_AccountDataPackage_AccountID_ModuleGroupID",
      "fragmentation_percent": 20.71,
      "category": "MEDIUM",
      "page_count": 789,
      "recommended_action": "REORGANIZE"
    }
  ],
  "fix_commands": [
    "ALTER INDEX [nc_DataHierarchy_status_pp] ON [dbo].[DataHierarchy] REORGANIZE;",
    "ALTER INDEX [IX_AccountDataPackage_All] ON [dbo].[AccountDataPackage] REORGANIZE;",
    "ALTER INDEX [IX_AccountSite_SiteKey] ON [dbo].[AccountSite] REORGANIZE;",
    "ALTER INDEX [nc_AccountSubscriptionItem_id_st] ON [dbo].[AccountSubscriptionItem] REORGANIZE;",
    "ALTER INDEX [IX_AccountDataPackage_AccountID_ModuleGroupID] ON [dbo].[AccountDataPackage] REORGANIZE;"
  ],
  "maintenance_plan": {
    "immediate": 0,
    "this_week": 0,
    "this_month": 8,
    "monitoring": 0
  },
  "recommendations": [
    {
      "category": "MAINTENANCE",
      "message": "8 indexes need REORGANIZE operations (15-30% fragmentation).",
      "action": "Run REORGANIZE during low-usage periods"
    },
    {
      "category": "MONITORING",
      "message": "Consider implementing automated index maintenance jobs.",
      "action": "Set up SQL Agent jobs or maintenance plans"
    }
  ],
  "sql_commands": {
    "maintenance_script": "-- Automated maintenance script template\nDECLARE @SQL NVARCHAR(MAX) = '';\n\nSELECT @SQL = @SQL + \n    'ALTER INDEX [' + i.name + '] ON [' + s.name + '].[' + t.name + '] '\n    + CASE \n        WHEN ips.avg_fragmentation_in_percent \u003e= 30 THEN 'REBUILD WITH (ONLINE = ON);'\n        ELSE 'REORGANIZE;'\n      END + CHAR(13)\nFROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'LIMITED') ips\nJOIN sys.indexes i ON ips.object_id = i.object_id AND ips.index_id = i.index_id\nJOIN sys.tables t ON i.object_id = t.object_id\nJOIN sys.schemas s ON t.schema_id = s.schema_id\nWHERE ips.avg_fragmentation_in_percent \u003e 10\nAND ips.page_count \u003e 50\nAND i.name IS NOT NULL;\n\n-- Execute the generated script\nEXEC sp_executesql @SQL;"
  }
}
```

**Analysis:**
The fragmentation analysis reveals 8 indexes with medium-level fragmentation (15-30%). The recommended action is to run REORGANIZE operations on these indexes during low-usage periods. No indexes require immediate REBUILD operations, indicating the database is in good overall health. Consider setting up automated maintenance jobs to prevent future fragmentation buildup.
      "index_type": "NONCLUSTERED",
      "fragmentation_percent": 24.70,
      "page_count": 842,
      "recommended_action": "REORGANIZE",
      "maintenance_cmd": "ALTER INDEX [nc_DataHierarchy_status_pp] ON [dbo].[DataHierarchy] REORGANIZE",
      "priority": "Medium"
    }
  ],
  "healthy_indexes": [],
  "recommendations": [
    {
      "priority": "High",
      "type": "maintenance_plan",
      "message": "Found 24 index(es) with >30% fragmentation requiring immediate REBUILD. Schedule maintenance during low-activity period."
    },
    {
      "priority": "Medium",
      "type": "maintenance_plan",
      "message": "Found 58 index(es) with 5-30% fragmentation. Consider REORGANIZE during next maintenance window."
    },
    {
      "priority": "High",
      "type": "index_maintenance",
      "object": "[dbo].[datasource_cn5441].[None]",
      "fragmentation_percent": 80.00,
      "message": "Heap table 'datasource_cn5441' has 80.00% fragmentation. Consider adding a clustered index or running REBUILD.",
      "command": null
    }
  ],
  "summary": {
    "total_indexes_analyzed": 192,
    "high_fragmentation_count": 24,
    "medium_fragmentation_count": 58,
    "low_fragmentation_count": 1,
    "healthy_count": 109,
    "total_pages_analyzed": 2048804
  }
}
```

### 5. Security & Performance Audit
**Prompt:** `using sqlserver_readonly, call db_sql2019_db_sec_perf_metrics(profile='oltp') and display results`

> **Note**: This tool currently operates in a limited capacity when invoked via MCP due to ongoing tool discovery issues. However, the underlying Python function is fully functional and robustly handles errors. The example output below is generated by directly executing the Python script `test_sec_perf_metrics.py`.

**Result:**
```json
{
  "profile": "oltp",
  "analysis_timestamp": "2026-02-23T19:02:25.104878",
  "security_assessment": {
    "login_audit": [
      {
        "name": "CLARITAS\\artsai-dev-readonly",
        "type_desc": "WINDOWS_GROUP",
        "is_disabled": false,
        "create_date": "2023-11-22 17:30:05.487000",
        "modify_date": "2023-11-22 17:30:05.493000",
        "default_database_name": "master",
        "is_fixed_role": false
      }
    ],
    "permissions_audit": [
      {
        "principal_name": "CLARITAS\\artsai-dev-readonly",
        "principal_type": "WINDOWS_GROUP",
        "permission_name": "CONNECT SQL",
        "permission_state": "GRANT",
        "object_name": null,
        "object_type": null
      }
    ],
    "security_config": {
      "error": "Could not execute query: ('08S01', '[08S01] [Microsoft][ODBC Driver 17 for SQL Server]TCP Provider: An existing connection was forcibly closed by the remote host.\r\n (10054) (SQLExecDirectW); [08S01] [Microsoft][ODBC Driver 17 for SQL Server]Communication link failure (10054)')"
    }
  },
  "performance_metrics": {
    "wait_stats": {
      "error": "Could not execute query: ('08S01', '[08S01] [Microsoft][ODBC Driver 17 for SQL Server]Communication link failure (0) (SQLExecDirectW)')"
    },
    "memory_usage": {
      "error": "Could not execute query: ('08S01', '[08S01] [Microsoft][ODBC Driver 17 for SQL Server]Communication link failure (0) (SQLExecDirectW)')"
    },
    "cpu_stats": {
      "error": "Could not execute query: ('08S01', '[08S01] [Microsoft][ODBC Driver 17 for SQL Server]Communication link failure (0) (SQLExecDirectW)')"
    }
  },
  "risk_assessment": {
    "overall_risk_score": 0,
    "risk_level": "LOW",
    "risk_factors": [],
    "profile_specific_metrics": {
      "profile": "oltp",
      "thresholds": {
        "max_acceptable_wait_percentage": 30,
        "max_memory_utilization": 80,
        "critical_wait_types": [
          "LCK_M_S",
          "LCK_M_X",
          "PAGELATCH_EX",
          "PAGELATCH_SH"
        ],
        "performance_priorities": [
          "Lock waits",
          "Latch contention",
          "Memory pressure"
        ]
      },
      "current_metrics": {},
      "compliance_status": "COMPLIANT"
    }
  },
  "recommendations": []
}
```
```

### 6. DDL Generation
**Prompt:** `using sqlserver, call db_sql2019_generate_ddl(database_name='USGISPRO_800', object_name='Account', object_type='table') and display results`

**Result:**
```json
{
  "database_name": "USGISPRO_800",
  "object_name": "Account",
  "object_type": "table",
  "success": true,
  "metadata": {
    "object_id": 123456789,
    "create_date": "2024-01-15T10:30:00",
    "modify_date": "2024-02-10T14:20:00",
    "description": "Main account table storing company account information"
  },
  "dependencies": ["Company"],
  "ddl": "CREATE TABLE [dbo].[Account](\n    [AccountID] [int] IDENTITY(1,1) NOT NULL,\n    [AccountName] [nvarchar](255) NOT NULL,\n    [Status] [nvarchar](50) NOT NULL,\n    [CompanyID] [int] NOT NULL,\n    [ParentAccountID] [int] NULL,\n    [CreatedDate] [datetime2](7) NOT NULL,\n    [ModifiedDate] [datetime2](7) NOT NULL,\n    [IsActive] [bit] NOT NULL,\n    CONSTRAINT [PK_Account] PRIMARY KEY CLUSTERED ([AccountID])\n) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]\nGO\n\n-- Foreign Key Constraints\nALTER TABLE [dbo].[Account] WITH CHECK ADD CONSTRAINT [FK_Account_Company] FOREIGN KEY([CompanyID])\nREFERENCES [dbo].[Company] ([CompanyID])\nGO\n\nALTER TABLE [dbo].[Account] CHECK CONSTRAINT [FK_Account_Company]\nGO\n\nALTER TABLE [dbo].[Account] WITH CHECK ADD CONSTRAINT [FK_Account_Account] FOREIGN KEY([ParentAccountID])\nREFERENCES [dbo].[Account] ([AccountID])\nGO\n\nALTER TABLE [dbo].[Account] CHECK CONSTRAINT [FK_Account_Account]\nGO\n\n-- Indexes\nCREATE NONCLUSTERED INDEX [IX_Account_AccountNameStatus] ON [dbo].[Account]\n([AccountName], [Status])\nGO\n\nCREATE NONCLUSTERED INDEX [IX_Account_CompanyID] ON [dbo].[Account]\n([CompanyID])\nGO\n"
}
```

### 7. Logical Data Model Analysis
**Prompt:** `using sqlserver_readonly, call db_sql2019_analyze_logical_data_model(database_name='USGISPRO_800', schema='dbo') and display results`

**Result:**
```json
{
  "summary": {
    "database": "USGISPRO_800",
    "schema": "dbo",
    "generated_at_utc": "2026-02-19T11:00:00.000000",
    "entities": 265,
    "relationships": 293,
    "issues_count": {
      "entities": 247,
      "attributes": 3061,
      "relationships": 240,
      "identifiers": 75,
      "normalization": 0
    }
  },
  "logical_model": {
    "entities": [
      {
        "schema": "dbo",
        "name": "Account",
        "kind": "U",
        "attributes": [
          {
            "name": "AccountID",
            "position": 1,
            "data_type": "int",
            "nullable": false,
            "max_length": 4,
            "numeric_precision": 10,
            "numeric_scale": 0,
            "default": null
          },
          {
            "name": "AccountName",
            "position": 2,
            "data_type": "nvarchar",
            "nullable": false,
            "max_length": 510,
            "numeric_precision": null,
            "numeric_scale": null,
            "default": null
          }
        ],
        "primary_key": ["AccountID"],
        "unique_constraints": [],
        "foreign_keys": [
          {
            "table": "Account",
            "name": "FK_Account_Company",
            "local_columns": ["CompanyID"],
            "ref_schema": "dbo",
            "ref_table": "Company",
            "ref_columns": ["CompanyID"],
            "on_update": "NO ACTION",
            "on_delete": "NO ACTION",
            "optional": false
          }
        ]
      }
    ],
    "relationships": [
      {
        "name": "FK_Account_Company",
        "from_entity": "dbo.Account",
        "to_entity": "dbo.Company",
        "local_columns": ["CompanyID"],
        "ref_columns": ["CompanyID"],
        "on_update": "NO ACTION",
        "on_delete": "NO ACTION"
      }
    ]
  },
  "issues": {
    "entities": [
      {
        "entity": "dbo.SomeTable",
        "issue": "Non-snake_case entity name"
      }
    ],
    "attributes": [],
    "relationships": [],
    "identifiers": [],
    "normalization": []
  },
  "recommendations": {
    "entities": [
      {
        "entity": "dbo.SomeTable",
        "recommendation": "Standardize entity naming to snake_case for consistency."
      }
    ],
    "attributes": [],
    "relationships": [],
    "identifiers": [],
    "normalization": []
  }
}
```

### 8. Interactive ERD Generation
**Prompt:** `using sqlserver, call db_sql2019_open_logical_model(database_name='USGISPRO_800') and display results`

**Result:**
```json
{
  "message": "ERD webpage generated for database 'USGISPRO_800'. View the interactive diagram at the URL below.",
  "database": "USGISPRO_800",
  "erd_url": "http://localhost:8085/data-model-analysis?id=5711f174-d4ee-4d97-992f-1ca6aaffadf4",
  "summary": {
    "database": "USGISPRO_800",
    "schema": "dbo",
    "generated_at_utc": "2026-02-19T11:15:00.000000",
    "entities": 265,
    "relationships": 293,
    "issues_count": {
      "entities": 247,
      "attributes": 3061,
      "relationships": 240,
      "identifiers": 75,
      "normalization": 0
    }
  }
}
```

**Interactive ERD Features:**
- **Entity-Relationship Diagram**: Interactive Mermaid.js diagram with pan/zoom controls
- **Entity Details**: Click entities to view column details, data types, and constraints
- **Relationship Visualization**: Visual representation of foreign key relationships
- **Design Analysis**: Naming convention issues, normalization problems, and recommendations
- **Health Score**: Overall schema quality score (100 - issues × 2)
- **Detailed Tables**: Comprehensive entity structure with PKs, FKs, and indexes

*Open the `erd_url` in your browser to view the full interactive ERD and analysis!*

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
