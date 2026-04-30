# SQL Server MCP Agent Development Guide

## 🎯 Project Overview

**mcp-sql-server** is a Model Context Protocol (MCP) server exposing 25+ DBA-grade tools for SQL Server inspection, performance analysis, and database administration. It's designed for AI agents (Claude, VS Code extensions, n8n) to safely query and manage SQL Server 2019+ databases.

### Key Architectural Concepts

- **MCP Server Pattern**: Uses FastMCP framework (`@mcp.tool` decorators) to expose async tools
- **Security by Default**: Read-only mode enforced via `ALLOW_WRITE`/`CONFIRM_WRITE` environment variables
- **Multiple Transport Modes**: HTTP (with SSE), stdio, SSH tunneling support
- **No ORM Dependency**: Direct `pyodbc` connections for maximum control and minimal overhead

---

## 🛠️ Core Architecture

### Single-File Monolith Pattern (`server.py`)

The entire MCP server lives in **`server.py`** (6045 lines). All tools follow this structure:

```python
@mcp.tool
def db_sql2019_<tool_name>(param1: str, param2: int) -> dict[str, Any]:
    """Tool description."""
    # Validate write operations
    if not ALLOW_WRITE:
        raise ValueError("Write operations are disabled. Set MCP_ALLOW_WRITE=true...")
    
    # Get connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Query execution
        _execute_safe(cur, "SELECT ...", params)
        rows = _fetch_limited(cur, DEFAULT_MAX_ROWS)
        # Format and return
        return {"status": "success", "data": rows}
    finally:
        conn.close()
```

### Configuration System

**Environment variables** drive all behavior (see `.env.example`):

```python
# Database connection (DB_* or SQL_* conventions)
DB_SERVER, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_DRIVER

# MCP security
MCP_ALLOW_WRITE=true/false      # Required - no default!
MCP_CONFIRM_WRITE=true/false    # Required if ALLOW_WRITE=true
MCP_MAX_ROWS=500                # Default result limit
MCP_STATEMENT_TIMEOUT_MS=120000 # Query timeout

# Authentication (fastmcp)
FASTMCP_AUTH_TYPE=none|oidc|jwt|azure-ad|github|google|apikey
FASTMCP_API_KEY=...             # For apikey auth

# Transport
MCP_TRANSPORT=http|stdio        # Default: http
MCP_HOST=0.0.0.0                # Default
MCP_PORT=8085                   # Default

# SSH Tunneling (optional)
SSH_HOST, SSH_USER, SSH_PASSWORD, SSH_PKEY
```

### Safety Mechanisms

1. **Read-Only Enforcement** (`_require_readonly()`, `_is_sql_readonly()`):
   - Parses SQL to detect write keywords (INSERT, UPDATE, DELETE, etc.)
   - Strips comments and string literals to avoid false negatives
   - Raises `ValueError` if write attempted in read-only mode

2. **Write Mode Guards**:
   ```python
   if ALLOW_WRITE:
       if not CONFIRM_WRITE:
           raise RuntimeError("MCP_CONFIRM_WRITE=true required")
       if TRANSPORT == "http" and not AUTH_TYPE:
           raise RuntimeError("Auth required for HTTP write mode")
   ```

3. **Connection Cleanup**: All tools use `try/finally` to ensure `conn.close()`

---

## 🧬 Tool Categories (25+ Tools)

### **Schema & Structure** (db_sql2019_list_objects, db_sql2019_create_object, db_sql2019_drop_object)
- List tables, indexes, views by database/schema
- Create/alter/drop objects with validation
- Returns schema metadata with dependencies

### **Performance Analysis** (db_sql2019_check_fragmentation, db_sql2019_analyze_index_health)
- Index fragmentation detection (SAMPLED mode for speed)
- Missing/unused index identification via DMVs
- Partitioning recommendations for large tables

### **Data Model** (db_sql2019_analyze_logical_data_model)
- Foreign key relationship discovery
- Table health scoring (row counts, bloat, constraints)
- Caches results with `DATA_MODEL_CACHE` (no TTL yet—add if needed!)

### **Security & Audit** (db_sql2019_sec_perf_metrics, db_sql2019_analyze_sessions)
- Database privilege audit
- Orphaned user detection
- Active session monitoring with query texts

### **Execution & Query** (db_sql2019_run_query, db_sql2019_explain_query)
- Execute parameterized SELECT queries
- STATISTICS XML execution plans (SQL Server 2019+)
- Limited to read-only by default

### **Administration** (db_sql2019_create_db_user, db_sql2019_drop_db_user, db_sql2019_kill_session)
- User creation/deletion with role assignment
- Session termination (prevents self-kill)
- Requires `MCP_ALLOW_WRITE=true`

---

## 📋 Common Patterns

### **Query Result Formatting**

Always return consistent dicts:

```python
# Option 1: Simple data return
return {
    "status": "success",
    "data": rows,
    "count": len(rows)
}

# Option 2: Detailed analysis
return {
    "database": "mydb",
    "schema": "dbo",
    "table": "users",
    "indexes": [{"name": "idx_id", "type": "CLUSTERED", ...}],
    "recommendations": [
        {"type": "fragmentation", "priority": "high", "message": "..."}
    ]
}
```

### **Parameter Passing**

Always use parameterized queries to prevent SQL injection:

```python
# ✅ CORRECT: Use params tuple
_execute_safe(cur, "SELECT * FROM sys.tables WHERE name = ?", (table_name,))

# ❌ WRONG: F-string interpolation (vulnerable)
_execute_safe(cur, f"SELECT * FROM sys.tables WHERE name = '{table_name}'")
```

### **Identifier Validation** (for table/schema names)

SQL Server identifiers must be bracketed:

```python
# ✅ CORRECT: Use brackets
_execute_safe(cur, f"USE [{database_name}]")
_execute_safe(cur, f"SELECT * FROM [{schema}].[{table_name}]")

# ❌ WRONG: Unquoted identifiers fail for special chars
_execute_safe(cur, f"USE {database_name}")
```

### **Error Handling**

Always distinguish between expected and unexpected errors:

```python
try:
    cur.execute(sql)
    result = cur.fetchall()
except pyodbc.Error as e:
    logger.error(f"Database error: {e}")
    raise ValueError(f"Query failed: {e}") from e  # Expected error
except Exception as e:
    logger.exception("Unexpected error")
    raise RuntimeError("Unexpected error") from e  # Unexpected error
```

### **Middleware Patterns**

Custom Starlette middleware for HTTP transport security:

```python
# API Key Authentication (static token)
class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if path.startswith(("/sse", "/messages")):
            auth_type = os.environ.get("FASTMCP_AUTH_TYPE", "").lower()
            if auth_type == "apikey":
                token = self._extract_token(request)
                expected_key = os.environ.get("FASTMCP_API_KEY")
                if not hmac.compare_digest(token, expected_key):
                    return JSONResponse({"detail": "Invalid API Key"}, status_code=403)
        return await call_next(request)

# Browser-friendly responses (HTML fallback for manual testing)
class BrowserFriendlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/mcp" and "text/html" in request.headers.get("accept", ""):
            return HTMLResponse("<html>MCP Endpoint</html>")
        return await call_next(request)
```

Add middleware in `main()` function:
```python
app.add_middleware(APIKeyMiddleware)
app.add_middleware(BrowserFriendlyMiddleware)
```

---

## 🧪 Testing Strategy

### Running Tests Locally

```bash
# 1. Provision SQL Server 2019 test database
python tests/setup_sql_server.py

# 2. Run comprehensive test suite
pytest -v tests/

# 3. Run specific test
pytest tests/test_server.py::test_db_sql2019_list_objects -v
```

### Test Files

- **`tests/test_server.py`**: Integration tests against live SQL Server (needs Docker)
- **`tests/unit_test_mocked.py`**: Unit tests with mocked connections (no DB required)
- **`tests/comprehensive_test.py`**: Stress tests, concurrent access validation

### Test Fixtures

```python
@pytest.fixture
def get_connection():
    """Mocked connection for unit tests."""
    return MagicMock()

@pytest.mark.integration
def test_tool_name():
    """Integration test requiring live SQL Server."""
    # Test code here
```

---

## 🚀 Development Workflow

### Adding a New Tool

1. **Define the tool** in `server.py`:
   ```python
   @mcp.tool
   def db_sql2019_my_new_tool(database: str) -> dict[str, Any]:
       """Short description."""
       # Implementation
   ```

2. **Add security checks** if write-enabled:
   ```python
   if not ALLOW_WRITE:
       raise ValueError("Write operations disabled...")
   ```

3. **Test locally**:
   ```bash
   pytest tests/test_server.py::test_db_sql2019_my_new_tool -v
   ```

4. **Update README.md** tools section to document new tool

### Debugging Tools

- **Logs**: Check `MCP_LOG_FILE` output (default: stderr, configurable via `MCP_LOG_LEVEL`)
- **Connection issues**: Run `python debug_connection.py` to test connectivity
- **Query issues**: Use `python test_tool.py` for standalone tool testing
- **Performance**: Monitor `MCP_STATEMENT_TIMEOUT_MS` (default 120s)

---

## 🔐 Security Model

### Read-Only Mode (Default)

- All tools check `_is_sql_readonly(sql)` via regex-based keyword scanning
- Strips comments + string literals to avoid bypasses
- Safe for untrusted clients

### Write Mode Requirements

1. **MCP_ALLOW_WRITE=true** (prevents accidental enablement)
2. **MCP_CONFIRM_WRITE=true** (confirmation latch)
3. **Authentication** (if running over HTTP)
   - Supports: OIDC, JWT, Azure AD, GitHub, Google, or static API key
   - Required to prevent unauthorized modifications

### **SSH Tunnel Configuration**

Optional bastion host tunneling for remote databases:

```python
# Environment variables
SSH_HOST="bastion.example.com"
SSH_USER="sshuser"
SSH_PASSWORD="..."  # OR
SSH_PKEY="/path/to/private/key"  # Private key path
SSH_PORT=22  # Default
ALLOW_SSH_AGENT=true  # Use local SSH agent

# Runtime behavior:
# 1. Establishes SSHTunnelForwarder in startup
# 2. Rewrites CONNECTION_STRING to use 127.0.0.1:local_port
# 3. Tunnels remote DB traffic through SSH
# 4. Cleanup on graceful shutdown via atexit handlers
```

### **Transport Security**

- **stdio**: Local access only, no auth needed
- **HTTP**: Open to network, requires `FASTMCP_AUTH_TYPE` config
- **SSH Tunnel**: Encrypts connection to bastion host (optional, compatible with all transports)

---

## 📦 Deployment Patterns

### Local Development
```bash
uv run mcp-sql-server  # Uses MCP_TRANSPORT=stdio by default
```

### Docker (Recommended)
```dockerfile
FROM python:3.11-slim
RUN pip install -r requirements.txt
CMD ["python", "server.py"]
```

### Claude Desktop
```json
{
  "mcpServers": {
    "sqlserver": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--env-file", ".env", "harryvaldez/mcp_sqlserver:latest"]
    }
  }
}
```

### n8n Integration
1. Start server: `docker compose up`
2. n8n AI Agent → MCP Tool node
3. Set **Source**: `Remote (SSE)`
4. Set **URL**: `http://mcp-sqlserver:8085/sse`

---

## 🪟 Platform-Specific Details

### **Windows Asyncio Workaround**

On Windows, Python's ProactorEventLoop can raise benign `ConnectionResetError` (WinError 10054) during shutdown. This code suppresses the noise:

```python
# Lines ~80-100 in server.py
if sys.platform == 'win32' and sys.version_info >= (3, 8):
    from asyncio.proactor_events import _ProactorBasePipeTransport
    
    _original_call_connection_lost = _ProactorBasePipeTransport._call_connection_lost
    
    def _silenced_call_connection_lost(self, exc):
        try:
            _original_call_connection_lost(self, exc)
        except ConnectionResetError:
            pass  # Benign: connection forcibly closed by remote host
    
    _ProactorBasePipeTransport._call_connection_lost = _silenced_call_connection_lost
```

**Why?** Prevents spam in logs when the process terminates or connections drop unexpectedly.

### **Startup Confirmation Dialog (Windows)**

On Windows, shows a confirmation dialog before startup (can be skipped with `MCP_SKIP_CONFIRMATION=true`):

```python
# Uses ctypes.windll.user32.MessageBoxW for native Windows dialogs
# Requires explicit user consent for Beta version
```

---

## ⚠️ Known Limitations & TODOs

1. **DATA_MODEL_CACHE** has no TTL—add timestamp-based cleanup for long-running servers
2. **Connection pooling**: Currently 1:1 connections. Consider `queue.Queue` wrapper if needed
3. **Execution plans**: `STATISTICS XML` parsing needs improvement for nested queries
4. **Batch operations**: No bulk INSERT/UPDATE/DELETE support (intentional for safety)
5. **Temporal queries**: No built-in support for `FOR SYSTEM_TIME AS OF`

---

## 🎓 Key Files to Review

| File | Purpose |
|------|---------|
| `server.py` | Main MCP server (6045 lines) |
| `requirements.txt` | Dependencies: fastmcp, pyodbc, uvicorn, sshtunnel |
| `tests/test_server.py` | Integration tests (needs live SQL Server) |
| `README.md` | User documentation |
| `DEPLOYMENT.md` | Deployment guide for Azure/AWS/Docker |
| `.env.example` | Configuration template |

---

## 💡 Pro Tips

- **Fast iteration**: Use `MCP_TRANSPORT=stdio` + `MCP_LOG_LEVEL=DEBUG` locally
- **SSH debugging**: Set `ALLOW_SSH_AGENT=true` to use local SSH keys
- **Result limits**: Adjust `MCP_MAX_ROWS` (default 500) for large datasets
- **Query timeouts**: Increase `MCP_STATEMENT_TIMEOUT_MS` for slow queries (default 120s)
- **Windows shutdown**: Handled by custom asyncio workaround to suppress benign errors

---

## 🛠️ Troubleshooting Guide

### **Connection Issues**

**Problem**: `Connection refused` or timeout
- Check `DB_SERVER`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` env vars
- Run `python debug_connection.py` for diagnostics
- Verify SQL Server is running: `netstat -ano | findstr :1433` (Windows) or `lsof -i :1433` (Linux)
- For SSH tunnels: Verify `SSH_HOST` accessibility and key permissions (`chmod 600 keyfile`)

**Problem**: Auth errors (`Login failed for user`)
- Check credentials in `.env` match SQL Server user permissions
- Verify user has `CONNECT` permission on database: `GRANT CONNECT TO [user];`
- Test directly: `sqlcmd -S SERVER -U user -P pass -d database`

### **Tool Execution Issues**

**Problem**: Tool not discovered
- Missing `@mcp.tool` decorator—add it to function definition
- Function signature must have return type: `-> dict[str, Any]:`
- Check `MCP_LOG_LEVEL=DEBUG` for decorator parsing errors

**Problem**: Query returns empty despite valid SQL
- Check `MCP_MAX_ROWS` (default 500)—query may be truncated
- Verify SQL is `SELECT` not a write operation blocked in read-only mode
- Check query timeout: `MCP_STATEMENT_TIMEOUT_MS=120000`

**Problem**: Write operations fail in expected read-only mode
- Confirm `MCP_ALLOW_WRITE=false` (default)
- If write needed, set `MCP_ALLOW_WRITE=true` AND `MCP_CONFIRM_WRITE=true`
- Verify auth is configured for HTTP transport: `FASTMCP_AUTH_TYPE`

### **Performance Issues**

**Slow queries**
- Increase `MCP_STATEMENT_TIMEOUT_MS` (e.g., 300000 for 5 min)
- Use `db_sql2019_check_fragmentation` with `SAMPLED` mode (not `DETAILED`)
- Reduce `MCP_MAX_ROWS` to fetch fewer rows

**High memory usage**
- Reduce `POOL_MAX_SIZE` (default 20) to limit concurrent connections
- Clear `DATA_MODEL_CACHE` manually (no automatic TTL yet)
- Monitor logs: `MCP_LOG_FILE=server.log` and `MCP_LOG_LEVEL=WARNING`

### **Docker/Container Issues**

**Problem**: Cannot reach SQL Server from container
- Use `--network host` (Linux) or Docker Desktop networking (Windows)
- Use container DNS name if same compose file: `http://mcp-sqlserver:8085/sse`
- Check firewall: `docker logs mcp-sqlserver` for connection errors

**Problem**: SSH tunnel fails in container
- Verify `SSH_PKEY` path is mounted as volume
- Set `ALLOW_SSH_AGENT=true` to use host SSH agent socket
- Test SSH manually: `ssh -v SSH_USER@SSH_HOST` from container

---

## 🔗 External References

- **FastMCP Docs**: https://github.com/zeke/fastmcp
- **Model Context Protocol**: https://modelcontextprotocol.io
- **SQL Server DMVs**: https://learn.microsoft.com/en-us/sql/relational-databases/
- **pyodbc**: https://github.com/mkleehammer/pyodbc/wiki
- **sshtunnel**: https://github.com/pahaz/sshtunnel
