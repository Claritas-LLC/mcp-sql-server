import asyncio
import html
import json
import hashlib
import logging
import os
import re
import sys
import time
import uuid
import threading
from dotenv import load_dotenv

# Load .env file at startup
load_dotenv()
import atexit
import signal
import decimal
from datetime import datetime, date, timedelta

def _json_safe_dict(data):
    if isinstance(data, dict):
        return {k: _json_safe_dict(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_json_safe_dict(i) for i in data]
    if isinstance(data, datetime):
        return data.isoformat()
    return data
from urllib.parse import quote, urlparse, urlunparse, urlsplit, urlunsplit
from typing import Any, Optional

from sshtunnel import SSHTunnelForwarder
from fastmcp import FastMCP
import pyodbc
from starlette.requests import Request
from starlette.responses import PlainTextResponse, JSONResponse, HTMLResponse, RedirectResponse
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware import Middleware
from starlette.applications import Starlette
from starlette.routing import Route
import uvicorn

# Startup Confirmation Dialog
# As requested: "once this MCP is loaded, it will load a dialog box asking the user's confirmation"
if sys.platform == 'win32':
    try:
        import ctypes
        def show_startup_confirmation():
            # MessageBox constants
            MB_YESNO = 0x04
            MB_ICONQUESTION = 0x20
            MB_TOPMOST = 0x40000
            MB_SETFOREGROUND = 0x10000
            IDYES = 6

            result = ctypes.windll.user32.MessageBoxW(
                0, 
                "This MCP server is in Beta version.  Review all commands before running.  Do you want to proceed?", 
                "MCP Server Confirmation", 
                MB_YESNO | MB_ICONQUESTION | MB_TOPMOST | MB_SETFOREGROUND
            )
            
            if result != IDYES:
                sys.exit(0)

        if os.environ.get("MCP_SKIP_CONFIRMATION", "").lower() != "true":
            show_startup_confirmation()
    except Exception as e:
        # If dialog fails, log it but proceed (or exit? safe to proceed if UI fails, but maybe log to stderr)
        sys.stderr.write(f"Warning: Could not show startup confirmation dialog: {e}\n")

# Configure structured logging
log_level_str = os.environ.get("MCP_LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
log_file = os.environ.get("MCP_LOG_FILE")

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=log_file,
    filemode='a' if log_file else None
)
logger = logging.getLogger("mcp-sqlserver")

# Patch for Windows asyncio ProactorEventLoop "ConnectionResetError" noise on shutdown
# References:
# - https://bugs.python.org/issue39232 (bpo-39232)
# - https://github.com/python/cpython/issues/83413
# Rationale:
# On Windows, when the ProactorEventLoop is closing, if a connection is forcibly closed
# by the remote (or the process is terminating), _call_connection_lost can raise
# ConnectionResetError (WinError 10054). This is harmless but noisy in logs.
if sys.platform == 'win32':
    # This issue primarily affects Python 3.8+, where Proactor is the default.
    if sys.version_info >= (3, 8):
        try:
            from asyncio.proactor_events import _ProactorBasePipeTransport

            _original_call_connection_lost = _ProactorBasePipeTransport._call_connection_lost

            def _silenced_call_connection_lost(self, exc):
                try:
                    _original_call_connection_lost(self, exc)
                except ConnectionResetError:
                    pass  # Benign: connection forcibly closed by remote host during shutdown

            _ProactorBasePipeTransport._call_connection_lost = _silenced_call_connection_lost
            logger.debug("Applied workaround for asyncio ProactorEventLoop ConnectionResetError")
        except ImportError:
            logger.info("Could not import asyncio.proactor_events._ProactorBasePipeTransport; skipping workaround")
    else:
        logger.debug("Skipping asyncio ProactorEventLoop workaround (Python version < 3.8)")

def _get_auth() -> Any:
    auth_type = os.environ.get("FASTMCP_AUTH_TYPE")
    if not auth_type:
        return None

    auth_type_lower = auth_type.lower()
    allowed_auth_types = {"oidc", "jwt", "azure-ad", "github", "google", "oauth2", "none"}
    
    if auth_type_lower not in allowed_auth_types:
        raise ValueError(
            f"Invalid FASTMCP_AUTH_TYPE: '{auth_type}'. "
            f"Accepted values are: {', '.join(sorted(allowed_auth_types))}"
        )

    if auth_type_lower == "none":
        return None

    # Full OIDC Proxy (handles login flow)
    if auth_type_lower == "oidc":
        from fastmcp.server.auth.providers.oidc import OIDCProxy

        config_url = os.environ.get("FASTMCP_OIDC_CONFIG_URL")
        client_id = os.environ.get("FASTMCP_OIDC_CLIENT_ID")
        client_secret = os.environ.get("FASTMCP_OIDC_CLIENT_SECRET")
        base_url = os.environ.get("FASTMCP_OIDC_BASE_URL")

        if not all([config_url, client_id, client_secret, base_url]):
            raise RuntimeError(
                "OIDC authentication requires FASTMCP_OIDC_CONFIG_URL, FASTMCP_OIDC_CLIENT_ID, "
                "FASTMCP_OIDC_CLIENT_SECRET, and FASTMCP_OIDC_BASE_URL"
            )

        return OIDCProxy(
            config_url=config_url,
            client_id=client_id,
            client_secret=client_secret,
            base_url=base_url,
            audience=os.environ.get("FASTMCP_OIDC_AUDIENCE"),
        )

    # Pure JWT Verification (resource server mode)
    if auth_type_lower == "jwt":
        from fastmcp.server.auth.providers.jwt import JWTVerifier

        jwks_uri = os.environ.get("FASTMCP_JWT_JWKS_URI")
        issuer = os.environ.get("FASTMCP_JWT_ISSUER")

        if not all([jwks_uri, issuer]):
            raise RuntimeError(
                "JWT verification requires FASTMCP_JWT_JWKS_URI and FASTMCP_JWT_ISSUER"
            )

        return JWTVerifier(
            jwks_uri=jwks_uri,
            issuer=issuer,
            audience=os.environ.get("FASTMCP_JWT_AUDIENCE"),
        )

    # Azure AD (Microsoft Entra ID) simplified configuration
    if auth_type_lower == "azure-ad":
        tenant_id = os.environ.get("FASTMCP_AZURE_AD_TENANT_ID")
        client_id = os.environ.get("FASTMCP_AZURE_AD_CLIENT_ID")
        
        if not all([tenant_id, client_id]):
            raise RuntimeError(
                "Azure AD authentication requires FASTMCP_AZURE_AD_TENANT_ID and FASTMCP_AZURE_AD_CLIENT_ID"
            )
            
        # Determine if we should use full OIDC flow or just JWT verification
        # If client_secret and base_url are provided, we use OIDC Proxy
        client_secret = os.environ.get("FASTMCP_AZURE_AD_CLIENT_SECRET")
        base_url = os.environ.get("FASTMCP_AZURE_AD_BASE_URL")
        
        config_url = f"https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration"
        
        if client_secret and base_url:
            from fastmcp.server.auth.providers.oidc import OIDCProxy
            return OIDCProxy(
                config_url=config_url,
                client_id=client_id,
                client_secret=client_secret,
                base_url=base_url,
                audience=os.environ.get("FASTMCP_AZURE_AD_AUDIENCE", client_id),
            )
        else:
            from fastmcp.server.auth.providers.jwt import JWTVerifier
            jwks_uri = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
            issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
            return JWTVerifier(
                jwks_uri=jwks_uri,
                issuer=issuer,
                audience=os.environ.get("FASTMCP_AZURE_AD_AUDIENCE", client_id),
            )
            
    # GitHub OAuth2
    if auth_type_lower == "github":
        from fastmcp.server.auth.providers.github import GitHubProvider
        
        client_id = os.environ.get("FASTMCP_GITHUB_CLIENT_ID")
        client_secret = os.environ.get("FASTMCP_GITHUB_CLIENT_SECRET")
        if not all([client_id, client_secret]):
            raise RuntimeError(
                "GitHub authentication requires FASTMCP_GITHUB_CLIENT_ID and FASTMCP_GITHUB_CLIENT_SECRET"
            )

        # Default to public GitHub URL if the env var is not set
        base_url = os.environ.get("FASTMCP_GITHUB_BASE_URL", "https://github.com")

        return GitHubProvider(
            client_id=client_id,
            client_secret=client_secret,
            base_url=base_url
        )

    # Google OAuth2
    if auth_type_lower == "google":
        from fastmcp.server.auth.providers.google import GoogleProvider
        
        client_id = os.environ.get("FASTMCP_GOOGLE_CLIENT_ID")
        client_secret = os.environ.get("FASTMCP_GOOGLE_CLIENT_SECRET")
        base_url = os.environ.get("FASTMCP_GOOGLE_BASE_URL")
        
        if not all([client_id, client_secret, base_url]):
            raise RuntimeError(
                "Google authentication requires FASTMCP_GOOGLE_CLIENT_ID, "
                "FASTMCP_GOOGLE_CLIENT_SECRET, and FASTMCP_GOOGLE_BASE_URL"
            )
            
        return GoogleProvider(
            client_id=client_id,
            client_secret=client_secret,
            base_url=base_url
        )

    # Generic OAuth2 Proxy
    if auth_type_lower == "oauth2":
        from fastmcp.server.auth import OAuthProxy
        from fastmcp.server.auth.providers.jwt import JWTVerifier
        
        auth_url = os.environ.get("FASTMCP_OAUTH_AUTHORIZE_URL")
        token_url = os.environ.get("FASTMCP_OAUTH_TOKEN_URL")
        client_id = os.environ.get("FASTMCP_OAUTH_CLIENT_ID")
        client_secret = os.environ.get("FASTMCP_OAUTH_CLIENT_SECRET")
        base_url = os.environ.get("FASTMCP_OAUTH_BASE_URL")
        
        # Token verifier details
        jwks_uri = os.environ.get("FASTMCP_OAUTH_JWKS_URI")
        issuer = os.environ.get("FASTMCP_OAUTH_ISSUER")
        
        if not all([auth_url, token_url, client_id, client_secret, base_url, jwks_uri, issuer]):
            raise RuntimeError(
                "Generic OAuth2 requires FASTMCP_OAUTH_AUTHORIZE_URL, FASTMCP_OAUTH_TOKEN_URL, "
                "FASTMCP_OAUTH_CLIENT_ID, FASTMCP_OAUTH_CLIENT_SECRET, FASTMCP_OAUTH_BASE_URL, "
                "FASTMCP_OAUTH_JWKS_URI, and FASTMCP_OAUTH_ISSUER"
            )
            
        token_verifier = JWTVerifier(
            jwks_uri=jwks_uri,
            issuer=issuer,
            audience=os.environ.get("FASTMCP_OAUTH_AUDIENCE")
        )
        
        return OAuthProxy(
            upstream_authorization_endpoint=auth_url,
            upstream_token_endpoint=token_url,
            upstream_client_id=client_id,
            upstream_client_secret=client_secret,
            token_verifier=token_verifier,
            base_url=base_url
        )
            
def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return int(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


# Initialize FastMCP
auth_type = os.environ.get("FASTMCP_AUTH_TYPE", "").lower()
mcp = FastMCP(
    name=os.environ.get("MCP_SERVER_NAME", "SQL Server MCP Server"),
    auth=_get_auth() if auth_type != "apikey" else None
)

# API Key Middleware for simple static token auth
class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # DEBUG LOG
        # logger.info(f"APIKeyMiddleware checking path: {path}")

        # 1. Compatibility Redirect: Redirect /mcp to /sse
        # Many users might try /mcp based on old docs or assumptions
        # Only redirect GET requests; POST requests might be for stateless JSON-RPC
        if path == "/mcp" and request.method == "GET":
            return RedirectResponse(url="/sse")

        # 2. Enforce API Key on SSE and Message endpoints
        # FastMCP mounts SSE at /sse and messages at /messages
        # We must protect both to prevent unauthorized access
        if path.startswith("/sse") or path.startswith("/messages"):
            auth_type = os.environ.get("FASTMCP_AUTH_TYPE", "").lower()
            logger.info(f"APIKeyMiddleware match. Auth type: {auth_type}")
            if auth_type == "apikey":
                auth_header = request.headers.get("Authorization")
                expected_key = os.environ.get("FASTMCP_API_KEY")
                
                if not expected_key:
                    logger.error("FASTMCP_API_KEY not configured but auth type is apikey")
                    return JSONResponse({"detail": "Server configuration error"}, status_code=500)
                
                # Check query param for SSE as fallback (standard for EventSource in some clients)
                token = None
                if auth_header and auth_header.startswith("Bearer "):
                    token = auth_header.split(" ")[1]
                elif "token" in request.query_params:
                    token = request.query_params["token"]
                elif "api_key" in request.query_params:
                    token = request.query_params["api_key"]
                
                if not token:
                    return JSONResponse({"detail": "Missing Authorization header or token"}, status_code=401)
                
                if token != expected_key:
                    return JSONResponse({"detail": "Invalid API Key"}, status_code=403)
        
        return await call_next(request)

# Browser-friendly middleware to handle direct visits to the SSE endpoint
class BrowserFriendlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # If visiting the MCP endpoint with a browser (Accept: text/html)
        # and NOT providing the required text/event-stream header
        if request.url.path == "/mcp":
            accept = request.headers.get("accept", "")
            if "text/html" in accept and "text/event-stream" not in accept:
                logger.info(f"Interposing browser-friendly response for {request.url.path}")
                return HTMLResponse(f'''
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>SQL Server MCP Server</title>
                        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
                        <style>
                            .bg-gradient {{ background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); }}
                        </style>
                    </head>
                    <body class="bg-gray-50 min-h-screen flex items-center justify-center p-4">
                        <div class="bg-white rounded-2xl shadow-2xl max-w-2xl w-full overflow-hidden">
                            <div class="bg-gradient p-8 text-white">
                                <h1 class="text-4xl font-extrabold mb-2">SQL Server MCP Server</h1>
                                <p class="text-blue-100 text-lg opacity-90">Protocol Endpoint Detected</p>
                            </div>
                            
                            <div class="p-8">
                                <div class="flex items-start mb-6 bg-blue-50 p-4 rounded-xl border border-blue-100">
                                    <div class="bg-blue-500 text-white rounded-full p-2 mr-4 mt-1">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="id-circle" />
                                            <circle cx="12" cy="12" r="9" />
                                            <line x1="12" y1="8" x2="12" y2="12" />
                                            <line x1="12" y1="16" x2="12.01" y2="16" />
                                        </svg>
                                    </div>
                                    <div>
                                        <h3 class="text-blue-800 font-bold text-lg mb-1">MCP Protocol Active</h3>
                                        <p class="text-blue-700">
                                            This endpoint (<code class="bg-blue-100 px-1 rounded">/mcp</code>) is reserved for <strong>Model Context Protocol</strong> clients.
                                        </p>
                                    </div>
                                </div>

                                <p class="text-gray-600 mb-8 leading-relaxed">
                                    You are seeing this page because your browser cannot speak the <code>text/event-stream</code> protocol required for MCP. 
                                    To use this server, add this URL to your MCP client configuration (e.g., Claude Desktop).
                                </p>

                                <div class="space-y-4">
                                    <h4 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-2">Available Dashboards</h4>
                                    
                                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <a href="/data-model-analysis" class="group flex flex-col p-5 border border-gray-100 rounded-xl hover:border-blue-300 hover:shadow-md transition-all bg-white">
                                            <span class="text-blue-600 font-bold mb-1 group-hover:text-blue-700">Data Model Analysis</span>
                                            <span class="text-sm text-gray-500">View interactive ERD and schema health score.</span>
                                        </a>
                                        
                                        <a href="/sessions-monitor" class="group flex flex-col p-5 border border-gray-100 rounded-xl hover:border-blue-300 hover:shadow-md transition-all bg-white">
                                            <span class="text-blue-600 font-bold mb-1 group-hover:text-blue-700">Sessions Monitor</span>
                                            <span class="text-sm text-gray-500">Track real-time database connections and queries.</span>
                                        </a>
                                    </div>
                                </div>

                                <div class="mt-10 pt-6 border-t border-gray-100 flex justify-between items-center">
                                    <a href="/health" class="text-sm text-gray-400 hover:text-gray-600 transition-colors italic">Server Status: Healthy</a>
                                    <a href="/" class="bg-gray-900 text-white px-6 py-2 rounded-lg font-medium hover:bg-black transition-colors shadow-sm">
                                        View Server Info
                                    </a>
                                </div>
                            </div>
                        </div>
                    </body>
                    </html>
                ''')
        return await call_next(request)

# Add the middleware to the FastMCP app
# MOVED to main() to ensure transport-specific app is configured correctly
# mcp.http_app().add_middleware(APIKeyMiddleware)
# mcp.http_app().add_middleware(BrowserFriendlyMiddleware)


def _build_connection_string_from_env() -> str | None:
    # Try DB_* convention first (DOCKER.md), then SQL_* fallback
    server = os.environ.get("DB_SERVER") or os.environ.get("SQL_SERVER")
    port = os.environ.get("DB_PORT") or os.environ.get("SQL_PORT", "1433")
    user = os.environ.get("DB_USER") or os.environ.get("SQL_USER")
    password = os.environ.get("DB_PASSWORD") or os.environ.get("SQL_PASSWORD")
    database = os.environ.get("DB_NAME") or os.environ.get("SQL_DATABASE")
    driver = os.environ.get("DB_DRIVER") or os.environ.get("SQL_DRIVER", "ODBC Driver 18 for SQL Server")
    
    # If no server is specified, assume no DB connection is desired
    if not server:
        return None
        
    conn_str = f"DRIVER={{{driver}}};SERVER={server},{port};"
    if database:
        conn_str += f"DATABASE={database};"
        
    # Use integrated security if no user/password is provided
    if user and password:
        conn_str += f"UID={user};PWD={password};"
    else:
        conn_str += "Trusted_Connection=yes;"
        
    # Standard security settings
    conn_str += f"Encrypt={os.environ.get('DB_ENCRYPT', 'yes')};"
    conn_str += f"TrustServerCertificate={os.environ.get('DB_TRUST_CERT', 'no')};"
    
    return conn_str

# Global variable for the SSH tunnel
ssh_tunnel: SSHTunnelForwarder | None = None

def get_connection(database: Optional[str] = None, autocommit: bool = False):
    global ssh_tunnel
    
    use_ssh = _env_bool("DB_SSH_ENABLE", False)
    
    if use_ssh and (ssh_tunnel is None or not ssh_tunnel.is_active):
        ssh_host = os.environ.get("DB_SSH_HOST")
        ssh_port = _env_int("DB_SSH_PORT", 22)
        ssh_user = os.environ.get("DB_SSH_USER")
        ssh_pass = os.environ.get("DB_SSH_PASS")
        ssh_pkey = os.environ.get("DB_SSH_PKEY")
        
        db_server = os.environ.get("DB_SERVER")
        db_port = _env_int("DB_PORT", 1433)

        if not all([ssh_host, ssh_user]):
            raise ValueError("DB_SSH_HOST and DB_SSH_USER are required when DB_SSH_ENABLE is true")
            
        if not ssh_pass and not ssh_pkey:
            raise ValueError("Either DB_SSH_PASS or DB_SSH_PKEY is required for SSH connections")

        ssh_tunnel = SSHTunnelForwarder(
            (ssh_host, ssh_port),
            ssh_username=ssh_user,
            ssh_password=ssh_pass,
            ssh_pkey=ssh_pkey,
            remote_bind_address=(db_server, db_port)
        )
        ssh_tunnel.start()
        logger.info(f"SSH tunnel started, local bind port: {ssh_tunnel.local_bind_port}")
        
        # Ensure tunnel is closed on exit
        atexit.register(stop_ssh_tunnel)

    conn_str = _build_connection_string_from_env()
    if not conn_str:
        raise ValueError("Database connection string could not be built from environment variables.")
        
    # If SSH is active, override the server and port
    if use_ssh and ssh_tunnel and ssh_tunnel.is_active:
        conn_str = re.sub(r"SERVER=[^,;]+", f"SERVER=127.0.0.1", conn_str)
        conn_str = re.sub(r",\d+", f",{ssh_tunnel.local_bind_port}", conn_str)

    # Override database if provided
    if database:
        if "DATABASE=" in conn_str:
            conn_str = re.sub(r"DATABASE=[^;]+", f"DATABASE={database}", conn_str, flags=re.IGNORECASE)
        else:
            conn_str += f"DATABASE={database};"

    conn = pyodbc.connect(conn_str, autocommit=autocommit)
    return conn

def stop_ssh_tunnel():
    global ssh_tunnel
    if ssh_tunnel and ssh_tunnel.is_active:
        logger.info("Closing SSH tunnel.")
        ssh_tunnel.close()
        ssh_tunnel = None

@mcp.tool(
    name="db.sql2019.analyze_table_health",
    description="Provides a detailed health analysis for a specific table, including size, indexes, foreign key dependencies, and statistics.",
)
def db_sql2019_analyze_table_health(
    schema: str,
    table_name: str,
    database_name: Optional[str] = None,
) -> dict:
    """
    Provides a detailed health analysis for a specific table.

    Includes:
    - Table size and row count.
    - Detailed index information (size, type, fragmentation).
    - Foreign key dependencies (tables that reference this table, and tables this table references).
    - Table and index statistics details.
    - Tuning recommendations.
    """
    conn = None
    try:
        conn = get_connection(database=database_name)
        is_sqlite = "sqlite" in str(type(conn))

        if is_sqlite:
            return {
                "warning": "Skipping table health analysis for SQLite. This feature is specific to SQL Server."
            }

        # Use a transaction to ensure all queries are consistent
        with conn.cursor() as cur:
            # 1. Table Size and Row Count
            size_sql = '''
            SELECT
                s.name AS [schem-name],
                t.name AS table_name,
                p.rows AS row_count,
                CAST(ROUND((SUM(a.total_pages) * 8.0) / 1024.0, 2) AS NUMERIC(36, 2)) AS total_space_mb,
                CAST(ROUND((SUM(a.used_pages) * 8.0) / 1024.0, 2) AS NUMERIC(36, 2)) AS used_space_mb,
                CAST(ROUND((SUM(a.data_pages) * 8.0) / 1024.0, 2) AS NUMERIC(36, 2)) AS data_space_mb
            FROM sys.tables t
            JOIN sys.indexes i ON t.object_id = i.object_id
            JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
            JOIN sys.allocation_units a ON p.partition_id = a.container_id
            LEFT JOIN sys.schemas s ON t.schem-id = s.schem-id
            WHERE t.name = ? AND s.name = ?
            GROUP BY t.name, s.name, p.rows;
            '''
            _execute_safe(cur, size_sql, [table_name, schema])
            size_info = cur.fetchone()
            size_columns = [column[0] for column in cur.description]
            table_size = dict(zip(size_columns, size_info)) if size_info else {}

            # 2. Index Details
            index_sql = '''
            SELECT
                i.name AS index_name,
                i.type_desc,
                ps.avg_fragmentation_in_percent,
                ps.page_count
            FROM sys.indexes i
            JOIN sys.dm_db_index_physical_stats(DB_ID(), OBJECT_ID(?), NULL, NULL, 'SAMPLED') ps
                ON i.object_id = ps.object_id AND i.index_id = ps.index_id
            WHERE i.object_id = OBJECT_ID(?);
            '''
            full_table_name = f'"{schema}"."{table_name}"'
            _execute_safe(cur, index_sql, [full_table_name, full_table_name])
            indexes_result = cur.fetchall()
            index_columns = [column[0] for column in cur.description]
            indexes = [dict(zip(index_columns, row)) for row in indexes_result]

            # 3. Foreign Key Dependencies
            # Tables that reference THIS table (dependent tables)
            referencing_sql = '''
            SELECT
                OBJECT_SCHEMA_NAME(fk.parent_object_id) AS referencing_schema,
                OBJECT_NAME(fk.parent_object_id) AS referencing_table,
                fk.name AS fk_name
            FROM sys.foreign_keys AS fk
            WHERE fk.referenced_object_id = OBJECT_ID(?);
            '''
            _execute_safe(cur, referencing_sql, [full_table_name])
            referencing_result = cur.fetchall()
            ref_columns = [column[0] for column in cur.description]
            referencing_tables = [dict(zip(ref_columns, row)) for row in referencing_result]

            # Tables THIS table references
            referenced_sql = '''
            SELECT
                OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS referenced_schema,
                OBJECT_NAME(fk.referenced_object_id) AS referenced_table,
                fk.name AS fk_name
            FROM sys.foreign_keys AS fk
            WHERE fk.parent_object_id = OBJECT_ID(?);
            '''
            _execute_safe(cur, referenced_sql, [full_table_name])
            referenced_result = cur.fetchall()
            referenced_cols = [column[0] for column in cur.description]
            referenced_tables = [dict(zip(referenced_cols, row)) for row in referenced_result]

            # 4. Statistics Info
            stats_sql = '''
            SELECT
                s.name AS stats_name,
                sp.last_updated,
                sp.rows,
                sp.rows_sampled,
                sp.modification_counter
            FROM sys.stats AS s
            CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) AS sp
            WHERE s.object_id = OBJECT_ID(?);
            '''
            _execute_safe(cur, stats_sql, [full_table_name])
            stats_result = cur.fetchall()
            stats_cols = [column[0] for column in cur.description]
            statistics = [dict(zip(stats_cols, row)) for row in stats_result]


        # 5. Tuning Recommendations
        recommendations = []
        # Index fragmentation
        for index in indexes:
            if index['avg_fragmentation_in_percent'] > 30:
                recommendations.append(
                    f"Index '{index['index_name']}' is {index['avg_fragmentation_in_percent']:.2f}% fragmented. "
                    f"Consider running ALTER INDEX ... REBUILD."
                )
            elif index['avg_fragmentation_in_percent'] > 5:
                recommendations.append(
                    f"Index '{index['index_name']}' is {index['avg_fragmentation_in_percent']:.2f}% fragmented. "
                    f"Consider running ALTER INDEX ... REORGANIZE."
                )

        # Stale statistics
        for stat in statistics:
            if table_size.get('row_count', 0) > 0:
                modified_fraction = stat['modification_counter'] / table_size['row_count'] if table_size['row_count'] > 0 else 0
                if modified_fraction > 0.20: # 20% modification threshold
                     recommendations.append(
                        f"Statistics '{stat['stats_name']}' are potentially stale "
                        f"({stat['modification_counter']} modifications since last update). "
                        f"Consider updating statistics with UPDATE STATISTICS."
                    )

        # Large table check
        if table_size.get('total_space_mb', 0) > 10240: # 10 GB
            recommendations.append(
                f"Table is large ({table_size['total_space_mb']:.2f} MB). "
                f"Consider table partitioning if not already implemented."
            )


        return {
            "table_size": table_size,
            "indexes": indexes,
            "dependencies": {
                "referenced_by_this_table": referenced_tables,
                "referencing_this_table": referencing_tables,
            },
            "statistics": statistics,
            "recommendations": recommendations,
        }
    except Exception as e:
        logger.error(f"Error in analyze_table_health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database operation failed: {str(e)}")
    finally:
        if conn:
            conn.close()
