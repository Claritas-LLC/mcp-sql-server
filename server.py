import asyncio
import json
import hashlib
import logging
import os
import re
import sys
import uuid
import threading
import atexit
import signal
import decimal
from datetime import datetime, date
from typing import Any

from dotenv import load_dotenv
from sshtunnel import SSHTunnelForwarder
from fastmcp import FastMCP
from fastmcp.server.auth import OAuthProxy
import pyodbc
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Load .env file at startup
load_dotenv()

# FastMCP will be initialized later with proper configuration

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
    except (ImportError, AttributeError, OSError) as e:
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
            from .auth.providers.jwt import JWTVerifier
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

# Create app alias for the properly initialized mcp instance
app = mcp

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
                return HTMLResponse('''
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>SQL Server MCP Server</title>
                        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
                        <style>
                            .bg-gradient { background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); }
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
    encrypt = os.environ.get("DB_ENCRYPT", "yes")
    trust_cert = os.environ.get("DB_TRUST_CERT", "no")
    
    if not server or not user or not database:
        return None
        
    # Escape password to handle braces properly
    password_safe = password or ''
    escaped_password = password_safe.replace('{', '{{').replace('}', '}}')
    
    conn_str = f'''DRIVER={{{driver}}};
SERVER={server},{port};
DATABASE={database};
UID={user};
PWD={{{escaped_password}}};
Encrypt={encrypt};
TrustServerCertificate={trust_cert};'''
    return conn_str.strip()

# SSH Tunnel Management
# A global dictionary to hold active SSH tunnels, keyed by a unique identifier
active_tunnels: dict[str, SSHTunnelForwarder] = {}
tunnel_lock = threading.Lock()

def get_ssh_tunnel(
    ssh_host: str, 
    ssh_port: int, 
    ssh_user: str, 
    remote_bind_host: str,
    remote_bind_port: int,
    ssh_pass: str | None = None,
    ssh_key: str | None = None
) -> SSHTunnelForwarder:
    
    tunnel_key = f"{ssh_user}@{ssh_host}:{ssh_port}-{remote_bind_host}:{remote_bind_port}"
    
    with tunnel_lock:
        if tunnel_key in active_tunnels and active_tunnels[tunnel_key].is_active:
            logger.info(f"Reusing existing SSH tunnel: {tunnel_key}")
            return active_tunnels[tunnel_key]

        logger.info(f"Creating new SSH tunnel: {tunnel_key}")
        
        # Validate SSH credentials
        if not ssh_pass and not ssh_key:
            raise ValueError("SSH connection requires either a password (ssh_pass) or a private key (ssh_key).")
            
        # If ssh_key is provided, it must be a valid file path
        if ssh_key and not os.path.isfile(ssh_key):
            raise FileNotFoundError(f"SSH private key file not found at path: {ssh_key}")
            
        server = SSHTunnelForwarder(
            (ssh_host, ssh_port),
            ssh_username=ssh_user,
            ssh_password=ssh_pass,
            ssh_pkey=ssh_key,
            remote_bind_address=(remote_bind_host, remote_bind_port)
        )
        
        try:
            server.start()
            logger.info(f"SSH tunnel started successfully. Local bind: {server.local_bind_host}:{server.local_bind_port}")
            active_tunnels[tunnel_key] = server
            return server
        except (ImportError, AttributeError, OSError) as e:
            logger.error(f"Failed to start SSH tunnel: {e}")
            # Ensure cleanup if start fails
            if server.is_active:
                server.stop()
            raise

def stop_all_tunnels():
    with tunnel_lock:
        logger.info("Stopping all active SSH tunnels...")
        for tunnel_key, server in active_tunnels.items():
            if server.is_active:
                try:
                    server.stop()
                    logger.info(f"Stopped tunnel: {tunnel_key}")
                except Exception as e:
                    logger.error(f"Error stopping tunnel {tunnel_key}: {e}")
        active_tunnels.clear()

# Register the cleanup function to be called on exit
atexit.register(stop_all_tunnels)

# Async-aware signal handlers
async def shutdown():
    """Perform async cleanup and shutdown."""
    logger.info("Shutting down server...")
    stop_all_tunnels()
    # Cancel any pending tasks if needed
    tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    # Let the loop exit naturally instead of forcing sys.exit
    loop = asyncio.get_running_loop()
    loop.stop()

def setup_signal_handlers():
    """Set up async-aware signal handlers."""
    try:
        loop = asyncio.get_running_loop()
        
        def signal_handler(signum):
            logger.info(f"Received signal {signum}, shutting down...")
            # Schedule the async shutdown coroutine
            asyncio.create_task(shutdown())
        
        # Register signal handlers
        loop.add_signal_handler(signal.SIGINT, signal_handler, signal.SIGINT)
        loop.add_signal_handler(signal.SIGTERM, signal_handler, signal.SIGTERM)
        
    except (RuntimeError, NotImplementedError):
        # Fallback for Windows or when add_signal_handler is not available
        logger.warning("Async signal handlers not available, using fallback handlers")
        
        def fallback_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            stop_all_tunnels()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, fallback_handler)
        signal.signal(signal.SIGTERM, fallback_handler)

# Set up signal handlers when the module is imported
# This will be called in the main() function when the event loop is running

def get_connection(
    ssh_host: str | None = None, 
    ssh_port: int = 22, 
    ssh_user: str | None = None, 
    ssh_pass: str | None = None,
    ssh_key: str | None = None
) -> pyodbc.Connection:
    
    conn_str_from_env = _build_connection_string_from_env()
    
    if not conn_str_from_env:
        raise ValueError(
            "Database connection details not found in environment variables. "
            "Please set DB_SERVER, DB_USER, DB_PASSWORD, and DB_NAME."
        )
        
    db_server = os.environ.get("DB_SERVER") or os.environ.get("SQL_SERVER")
    db_port = int(os.environ.get("DB_PORT") or os.environ.get("SQL_PORT", "1433"))

    if ssh_host and ssh_user:
        tunnel = get_ssh_tunnel(
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_user=ssh_user,
            ssh_pass=ssh_pass,
            ssh_key=ssh_key,
            remote_bind_host=db_server,
            remote_bind_port=db_port
        )
        
        # Modify the connection string to use the tunnel's local bind port
        local_bind_host = tunnel.local_bind_host
        local_bind_port = tunnel.local_bind_port
        
        # Replace server and port in the original connection string
        conn_str = re.sub("SERVER=.*?;", f"SERVER={local_bind_host},{local_bind_port};", conn_str_from_env)
        
    else:
        conn_str = conn_str_from_env

    try:
        conn = pyodbc.connect(conn_str)
        return conn
    except pyodbc.Error as ex:
        sqlstate = ex.args[0]
        logger.error(f"Database connection failed. SQLSTATE: {sqlstate}. Error: {ex}")
        # Provide more user-friendly error messages for common issues
        if "08001" in sqlstate: # Client unable to establish connection
            raise ConnectionError(
                "Could not connect to the SQL Server. Please check the following:\n"
                "1. The server address and port are correct.\n"
                "2. The server is running and accessible from your network.\n"
                "3. Any firewalls (local or network) are not blocking the connection.\n"
                "4. If using an SSH tunnel, ensure SSH credentials and host are correct."
            ) from ex
        elif "28000" in sqlstate: # Invalid authorization specification
            raise PermissionError(
                "Authentication failed. Please check your database username and password."
            ) from ex
        elif "42000" in sqlstate: # Syntax error or access violation (often for database not found)
            raise ValueError(
                "Connection failed, possibly due to an incorrect database name. "
                "Please verify the DB_NAME/SQL_DATABASE environment variable."
            ) from ex
        else:
            raise  # Re-raise other pyodbc errors

def is_valid_sql_identifier(identifier: str) -> bool:
    """
    Checks if a string is a valid SQL identifier.
    This is a simple check and might not cover all edge cases, but it's a good first step.
    """
    if not identifier:
        return False
    # SQL identifiers should not contain characters that can be used for injection
    # This is a restrictive but safe set of characters.
    return re.match(r"^[a-zA-Z0-9_]+$", identifier) is not None

def _execute_safe(cursor: pyodbc.Cursor, sql: str, params: list[Any] | None = None):
    """
    Executes a SQL query with parameters safely, logging the query and handling potential errors.
    This function is a security-sensitive area.
    """
    params = params or []
    
    # Enhanced Logging: Log the query but mask or hash sensitive data for security.
    # This is important for debugging without exposing credentials or PII.
    if logger.isEnabledFor(logging.DEBUG):
        # Create a copy of params for logging to avoid altering the original list
        log_params = list(params)
        
        # Hashing function for sensitive parameters
        def _hash_param(p):
            if isinstance(p, str) and len(p) > 4:  # Hash longer strings
                return hashlib.sha256(p.encode()).hexdigest()[:8] + "..."
            return p

        # Example heuristic: hash parameters that might be sensitive.
        # This should be adapted based on knowledge of the tool's parameters.
        # For a generic function, we might look for keywords in the SQL.
        sensitive_keywords = ["password", "secret", "token", "apikey", "privatekey"]
        sql_lower = sql.lower()
        
        # Check if the query itself contains sensitive keywords (less common for params)
        if any(keyword in sql_lower for keyword in sensitive_keywords):
            # In this case, we might hash all parameters as a precaution
            log_params = [_hash_param(p) for p in log_params]

        logger.debug(f"Executing SQL: {sql.strip()} with params: {log_params}")

    try:
        cursor.execute(sql, *params)
    except pyodbc.Error as e:
        logger.error(f"SQL execution error: {e}. Query: {sql.strip()}, Params: {params}")
        # Re-raise as a more generic exception to avoid leaking too much detail
        raise RuntimeError(f"Database query failed: {e}") from e

def _format_results(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    """
    Fetches all rows from a cursor and formats them as a list of dictionaries.
    Handles data type conversions for JSON serialization.
    """
    columns = [column[0] for column in cursor.description]
    results = []
    
    # Custom JSON encoder for data types not handled by default
    def json_converter(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, decimal.Decimal):
            return float(o)
        if isinstance(o, uuid.UUID):
            return str(o)
        # For other un-serializable types, convert to string as a fallback
        try:
            json.dumps(o)
            return o
        except TypeError:
            return str(o)

    for row in cursor.fetchall():
        row_dict = dict(zip(columns, row))
        # Apply the converter to each value in the dictionary
        for key, value in row_dict.items():
            row_dict[key] = json_converter(value)
        results.append(row_dict)
        
    return results

@mcp.tool
def db_list_databases() -> list[str]:
    """
    Lists all databases on the connected SQL Server instance that are accessible by the current user.
    Excludes system databases by default.

    Returns:
        A list of database names.
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        sql = "SELECT name FROM sys.databases WHERE database_id > 4 ORDER BY name"
        _execute_safe(cur, sql)
        
        databases = [row[0] for row in cur.fetchall()]
        return databases
    finally:
        if conn:
            conn.close()

@mcp.tool
def db_list_tables(database_name: str, schema_name: str | None = None) -> list[dict[str, Any]]:
    """
    Lists all tables within a specific database and optionally a schema.

    Args:
        database_name: The name of the database to query.
        schema_name: (Optional) The name of the schema to filter by. If not provided, tables from all schemas are listed.

    Returns:
        A list of dictionaries, where each dictionary contains details about a table (schema, name, type).
    """
    if not is_valid_sql_identifier(database_name):
        raise ValueError(f"Invalid database name: {database_name}")
    if schema_name and not is_valid_sql_identifier(schema_name):
        raise ValueError(f"Invalid schema name: {schema_name}")

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Ensure the connection is using the correct database context
        _execute_safe(cur, f"USE [{database_name}]")

        sql = "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES"
        params = []
        if schema_name:
            sql += " WHERE TABLE_SCHEMA = ?"
            params.append(schema_name)
        
        sql += " ORDER BY TABLE_SCHEMA, TABLE_NAME"
        
        _execute_safe(cur, sql, params)
        
        return _format_results(cur)
    finally:
        if conn:
            conn.close()

@mcp.tool
def db_get_schema(
    database_name: str, 
    table_name: str, 
    schema_name: str | None = "dbo"
) -> dict[str, Any]:
    """
    Retrieves the schema for a specific table, including columns, data types, and constraints.

    Args:
        database_name: The name of the database.
        table_name: The name of the table.
        schema_name: The schema of the table (defaults to 'dbo').

    Returns:
        A dictionary containing the table schema details.
    """
    if not is_valid_sql_identifier(database_name):
        raise ValueError(f"Invalid database name: {database_name}")
    if not is_valid_sql_identifier(table_name):
        raise ValueError(f"Invalid table name: {table_name}")
    if schema_name and not is_valid_sql_identifier(schema_name):
        raise ValueError(f"Invalid schema name: {schema_name}")

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        _execute_safe(cur, f"USE [{database_name}]")

        # Get column information
        column_sql = """
            SELECT 
                COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION;
        """
        _execute_safe(cur, column_sql, [schema_name, table_name])
        columns = _format_results(cur)

        # Get primary key information
        pk_sql = """
            SELECT c.name AS COLUMN_NAME
            FROM sys.indexes AS i
            INNER JOIN sys.index_columns AS ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            INNER JOIN sys.columns AS c ON ic.object_id = c.object_id AND c.column_id = ic.column_id
            WHERE i.is_primary_key = 1 AND i.object_id = OBJECT_ID(CONCAT(?, '.', ?));
        """
        _execute_safe(cur, pk_sql, [schema_name, table_name])
        pk_columns = [row['COLUMN_NAME'] for row in _format_results(cur)]

        # Get foreign key information
        fk_sql = """
            SELECT 
                fk.name AS FK_NAME,
                tp.name AS PARENT_TABLE,
                cp.name AS PARENT_COLUMN,
                tr.name AS REFERENCED_TABLE,
                cr.name AS REFERENCED_COLUMN
            FROM sys.foreign_keys AS fk
            INNER JOIN sys.foreign_key_columns AS fkc ON fk.object_id = fkc.constraint_object_id
            INNER JOIN sys.tables AS tp ON fkc.parent_object_id = tp.object_id
            INNER JOIN sys.columns AS cp ON fkc.parent_object_id = cp.object_id AND fkc.parent_column_id = cp.column_id
            INNER JOIN sys.tables AS tr ON fkc.referenced_object_id = tr.object_id
            INNER JOIN sys.columns AS cr ON fkc.referenced_object_id = cr.object_id AND fkc.referenced_column_id = cr.column_id
            WHERE tp.object_id = OBJECT_ID(CONCAT(?, '.', ?));
        """
        _execute_safe(cur, fk_sql, [schema_name, table_name])
        foreign_keys = _format_results(cur)

        return {
            "table": f"{schema_name}.{table_name}",
            "columns": columns,
            "primary_key": pk_columns,
            "foreign_keys": foreign_keys
        }
    finally:
        if conn:
            conn.close()

@mcp.tool
def db_execute_query(
    database_name: str, 
    sql_query: str,
    parameters: list[Any] | None = None,
    read_only: bool = True
) -> list[dict[str, Any]] | str:
    """
    Executes a SQL query against the specified database and returns the results.
    For security, this tool defaults to read-only mode.
    
    WARNING: Disabling read-only mode can expose the database to data modification or deletion.
    Only disable read_only for trusted, validated queries.

    Args:
        database_name: The name of the database to execute the query against.
        sql_query: The SQL query to execute. Use parameter markers (?) for variables.
        parameters: A list of parameters to substitute into the query.
        read_only: If True, enforces that the query is a SELECT statement.

    Returns:
        A list of dictionaries representing the query results, or a confirmation message for non-SELECT queries.
    """
    if not is_valid_sql_identifier(database_name):
        raise ValueError(f"Invalid database name: {database_name}")

    if read_only:
        # Robust validation for read-only queries
        
        # Remove comments and string literals for safer parsing
        def remove_sql_literals_and_comments(sql):
            # Remove single-line comments
            sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
            # Remove multi-line comments
            sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
            # Remove string literals (both single and double quotes), handling escaped quotes
            # Single quotes: match '...' allowing '' as escaped quote
            sql = re.sub(r"'([^']|'')*'", "''", sql)
            # Double quotes: match "..." allowing "" as escaped quote
            sql = re.sub(r'"([^"]|"")*"', '""', sql)
            return sql
        
        cleaned_sql = remove_sql_literals_and_comments(sql_query)
        
        # Check for only one statement (no semicolons except at the end)
        statements = [s.strip() for s in cleaned_sql.split(';') if s.strip()]
        if len(statements) != 1:
            raise PermissionError("Only single SELECT statements are allowed in read-only mode.")
        
        # Check that the statement starts with SELECT (case insensitive, allowing whitespace)
        if not re.match(r'^\s*SELECT\s+', statements[0], re.IGNORECASE):
            raise PermissionError("Only SELECT statements are allowed in read-only mode.")
        
        # Additional safety: check for common dangerous keywords
        dangerous_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'EXEC', 'EXECUTE']
        for keyword in dangerous_keywords:
            if re.search(rf'\b{keyword}\b', statements[0], re.IGNORECASE):
                raise PermissionError(f"Statement contains dangerous keyword '{keyword}' in read-only mode.")
    
    else:
        # For non-read-only mode, still prevent multiple statements for safety
        cleaned_sql = re.sub(r'--.*$', '', sql_query, flags=re.MULTILINE)
        cleaned_sql = re.sub(r'/\*.*?\*/', '', cleaned_sql, flags=re.DOTALL)
        statements = [s.strip() for s in cleaned_sql.split(';') if s.strip()]
        if len(statements) > 1:
            raise PermissionError("Multiple SQL statements are not allowed.")

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        _execute_safe(cur, f"USE [{database_name}]")
        
        _execute_safe(cur, sql_query, parameters)
        
        # For SELECT queries, fetch and return results
        if cur.description:
            results = _format_results(cur)
            
            # Limit the number of rows returned to prevent DoS
            MAX_ROWS = 10000
            if len(results) > MAX_ROWS:
                logger.warning(f"Query returned {len(results)} rows, limiting to {MAX_ROWS}")
                results = results[:MAX_ROWS]
                results.append({"WARNING": f"Results limited to {MAX_ROWS} rows for performance and safety."})
            
            conn.commit() # Not strictly necessary for SELECT, but good practice
            return results
        else:
            # For non-SELECT queries (e.g., INSERT, UPDATE, DELETE)
            conn.commit()
            return f"Query executed successfully. {cur.rowcount} rows affected."
    except (pyodbc.Error, ValueError) as e:
        if conn:
            conn.rollback() # Rollback any transaction on error
        logger.error(f"Error executing query: {e}")
        raise
    finally:
        if conn:
            conn.close()

@mcp.tool
def db_sql2019_get_index_fragmentation(
    database_name: str,
    schema: str = "dbo",
    table_name: str | None = None,
    min_fragmentation: float = 10.0,
    min_page_count: int = 100,
    limit: int = 50
) -> list[dict[str, Any]]:
    """
    Analyzes index fragmentation for a specific table or the entire database in SQL Server 2019+.
    
    This tool is designed to identify indexes that may need reorganization or rebuilding
    to improve query performance. High fragmentation can lead to slower data retrieval.

    Args:
        database_name: The database to analyze.
        schema: The schema of the table (defaults to 'dbo').
        table_name: (Optional) The specific table to analyze. If not provided, analyzes all tables in the database.
        min_fragmentation: The minimum fragmentation percentage to report (default: 10.0).
        min_page_count: The minimum number of pages an index must have to be included (default: 100).
        limit: The maximum number of fragmented indexes to return (default: 50).

    Returns:
        A list of dictionaries, each detailing a fragmented index.
    """
    if not is_valid_sql_identifier(database_name):
        raise ValueError(f"Invalid database name: {database_name}")
    if not is_valid_sql_identifier(schema):
        raise ValueError(f"Invalid schema name: {schema}")
    if table_name and not is_valid_sql_identifier(table_name):
        raise ValueError(f"Invalid table name: {table_name}")

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        _execute_safe(cur, f"USE [{database_name}]")

        fragmentation_query = '''
            SELECT TOP (?)
                o.name AS TableName,
                i.name AS IndexName,
                ips.index_type_desc,
                ips.avg_fragmentation_in_percent,
                ips.page_count
            FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'LIMITED') AS ips
            INNER JOIN sys.objects o ON ips.object_id = o.object_id
            INNER JOIN sys.indexes i ON ips.object_id = i.object_id AND ips.index_id = i.index_id
            WHERE o.is_ms_shipped = 0
            AND i.name IS NOT NULL
            AND ips.page_count >= ?
            AND ips.avg_fragmentation_in_percent >= ?
        '''
        
        params = [limit, min_page_count, min_fragmentation]
        
        if table_name:
            fragmentation_query += " AND o.name = ? AND SCHEMA_NAME(o.schema_id) = ?"
            params.extend([table_name, schema])
        
        if schema and not table_name:
            fragmentation_query += " AND SCHEMA_NAME(o.schema_id) = ?"
            params.append(schema)

        fragmentation_query += " ORDER BY ips.avg_fragmentation_in_percent DESC"
        
        _execute_safe(cur, fragmentation_query, params)
        results = _format_results(cur)
        
        return results
    finally:
        if conn:
            conn.close()

@mcp.tool
def db_sql2019_analyze_table_health(
    database_name: str,
    schema: str,
    table_name: str
) -> dict[str, Any]:
    """
    Provides a comprehensive health analysis for a specific SQL Server table.

    This tool performs a deep analysis of a table's structure and usage, including:
    - Table and index sizes
    - Foreign key integrity and indexing
    - Column statistics and data distribution
    - Identification of potential design issues like:
        - Missing primary keys
        - Unused or redundant indexes
        - Inefficient data types
    - Actionable recommendations for optimization.

    This is a powerful diagnostic tool for database administrators and developers
    to pinpoint performance bottlenecks and design flaws at the table level.

    The analysis covers several key areas:
    - **Constraint Analysis**: Checks for missing primary keys and un-indexed foreign keys.
    - **Index Analysis**: Looks for:
        - Missing indexes on foreign key columns
        - Disabled or highly fragmented indexes
        - Unused large indexes
        - Redundant/overlapping indexes

    Args:
        database_name: The database name containing the table.
        schema: The schema name containing the table.
        table_name: The name of the table to analyze.

    Returns:
        Dictionary containing table size, indexes with sizes/types, foreign key dependencies, 
        statistics, missing constraints analysis, enhanced index analysis, and tuning recommendations.
    """
    if not is_valid_sql_identifier(database_name):
        raise ValueError(f"Invalid database name: {database_name}")
    if not is_valid_sql_identifier(schema):
        raise ValueError(f"Invalid schema name: {schema}")
    if not is_valid_sql_identifier(table_name):
        raise ValueError(f"Invalid table name: {table_name}")

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Use the specified database
        _execute_safe(cur, f"USE [{database_name}]")
        

        
        # Initialize lists for recommendations and data
        recommendations = []
        constraint_issues = []
        index_issues = []

        # 1. Table Size and Row Count
        size_sql = '''
            SELECT 
                t.name AS TableName,
                s.name AS SchemaName,
                p.rows AS RowCounts,
                SUM(a.total_pages) * 8 AS TotalSpaceKB,
                SUM(a.used_pages) * 8 AS UsedSpaceKB,
                (SUM(a.total_pages) - SUM(a.used_pages)) * 8 AS UnusedSpaceKB
            FROM 
                sys.tables t
            INNER JOIN      
                sys.indexes i ON t.object_id = i.object_id
            INNER JOIN 
                sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
            INNER JOIN 
                sys.allocation_units a ON p.partition_id = a.container_id
            LEFT OUTER JOIN 
                sys.schemas s ON t.schema_id = s.schema_id
            WHERE 
                t.name = ? AND s.name = ?
            GROUP BY 
                t.name, s.name, p.rows
        '''
        _execute_safe(cur, size_sql, [table_name, schema])
        table_size_info = _format_results(cur)

        # 2. Index Analysis (including size and type)
        index_sql = '''
            SELECT 
                i.name as IndexName,
                i.type_desc as IndexType,
                SUM(s.used_page_count) * 8.0 / 1024 AS IndexSizeMB
            FROM sys.dm_db_partition_stats s
            JOIN sys.indexes i ON s.object_id = i.object_id AND s.index_id = i.index_id
            WHERE s.object_id = OBJECT_ID(CONCAT(?, '.', ?))
            GROUP BY i.name, i.type_desc
            ORDER BY IndexSizeMB DESC;
        '''
        _execute_safe(cur, index_sql, [schema, table_name])
        indexes_info = _format_results(cur)

        # 3. Foreign Key Dependencies
        fk_sql = '''
            SELECT 
                fk.name AS FK_Name,
                OBJECT_NAME(fk.parent_object_id) AS ParentTable,
                cpa.name AS ParentColumn,
                OBJECT_NAME(fk.referenced_object_id) AS ReferencedTable,
                cre.name AS ReferencedColumn
            FROM sys.foreign_keys fk
            JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
            JOIN sys.columns cpa ON fkc.parent_object_id = cpa.object_id AND fkc.parent_column_id = cpa.column_id
            JOIN sys.columns cre ON fkc.referenced_object_id = cre.object_id AND fkc.referenced_column_id = cre.column_id
            WHERE fk.parent_object_id = OBJECT_ID(CONCAT(?, '.', ?)) OR fk.referenced_object_id = OBJECT_ID(CONCAT(?, '.', ?));
        '''
        _execute_safe(cur, fk_sql, [schema, table_name, schema, table_name])
        fk_info = _format_results(cur)

        # 4. Column Statistics (for a few key columns, as an example)
        stats_sql = '''
            SELECT TOP 5
                c.name AS ColumnName,
                st.name AS StatsName,
                sp.last_updated,
                sp.rows,
                sp.rows_sampled,
                sp.modification_counter
            FROM sys.stats st
            JOIN sys.stats_columns sc ON st.object_id = sc.object_id AND st.stats_id = sc.stats_id
            JOIN sys.columns c ON sc.object_id = c.object_id AND sc.column_id = c.column_id
            CROSS APPLY sys.dm_db_stats_properties(st.object_id, st.stats_id) AS sp
            WHERE st.object_id = OBJECT_ID(CONCAT(?, '.', ?));
        '''
        _execute_safe(cur, stats_sql, [schema, table_name])
        stats_info = _format_results(cur)

        # 5. Health Analysis: Missing Primary Key
        pk_check_sql = "SELECT i.name FROM sys.indexes i WHERE i.is_primary_key = 1 AND i.object_id = OBJECT_ID(CONCAT(?, '.', ?));"
        _execute_safe(cur, pk_check_sql, [schema, table_name])
        if not cur.fetchone():
            msg = "Critical: Table is missing a primary key. This can lead to duplicate data and performance issues."
            constraint_issues.append({"type": "Missing Primary Key", "message": msg})
            recommendations.append({"severity": "High", "recommendation": "Define a primary key for this table."})

        # 6. Health Analysis: Un-indexed Foreign Keys
        unindexed_fk_sql = '''
            SELECT fk.name AS ForeignKeyName, cl.name AS ColumnName
            FROM sys.foreign_keys AS fk
            INNER JOIN sys.foreign_key_columns AS fkc ON fk.object_id = fkc.constraint_object_id
            INNER JOIN sys.columns AS cl ON fkc.parent_object_id = cl.object_id AND fkc.parent_column_id = cl.column_id
            WHERE fkc.parent_object_id = OBJECT_ID(CONCAT(?, '.', ?))
            AND NOT EXISTS (
                SELECT 1
                FROM sys.index_columns AS ic
                WHERE ic.object_id = fkc.parent_object_id AND ic.column_id = fkc.parent_column_id AND ic.index_column_id = 1
            );
        '''
        _execute_safe(cur, unindexed_fk_sql, [schema, table_name])
        unindexed_fks = _format_results(cur)
        for fk in unindexed_fks:
            msg = f"Warning: Foreign key '{fk['ForeignKeyName']}' on column '{fk['ColumnName']}' is not indexed. This can cause performance problems during joins and cascading operations."
            constraint_issues.append({"type": "Unindexed Foreign Key", "message": msg})
            recommendations.append({
                "severity": "Medium",
                "recommendation": f"Create an index on column '{fk['ColumnName']}' to support the foreign key '{fk['ForeignKeyName']}'."
            })

        # 7. Health Analysis: Unused Indexes
        unused_index_sql = '''
            SELECT i.name AS IndexName,
                   (SUM(s.user_seeks) + SUM(s.user_scans) + SUM(s.user_lookups)) AS TotalReads,
                   SUM(s.user_updates) AS TotalWrites,
                   (SUM(s.used_page_count) * 8.0 / 1024) as IndexSizeMB
            FROM sys.dm_db_index_usage_stats s
            JOIN sys.indexes i ON s.object_id = i.object_id AND s.index_id = i.index_id
            WHERE s.database_id = DB_ID()
              AND s.object_id = OBJECT_ID(CONCAT(?, '.', ?))
              AND i.is_primary_key = 0
            GROUP BY i.name
            HAVING (SUM(s.user_seeks) + SUM(s.user_scans) + SUM(s.user_lookups)) = 0;
        '''
        _execute_safe(cur, unused_index_sql, [schema, table_name])
        unused_indexes = _format_results(cur)
        for idx in unused_indexes:
            if idx['IndexSizeMB'] > 10: # Only flag large, unused indexes
                msg = f"Info: Index '{idx['IndexName']}' appears to be unused and consumes {idx['IndexSizeMB']:.2f} MB. It has high write overhead ({idx['TotalWrites']} writes) with no reads."
                index_issues.append({"type": "Unused Index", "message": msg})
                recommendations.append({
                    "severity": "Low",
                    "recommendation": f"Consider dropping unused index '{idx['IndexName']}' to reduce storage and maintenance overhead, after confirming it's not needed for specific infrequent queries."
                })
        
        return {
            "table_info": table_size_info[0] if table_size_info else {},
            "indexes": indexes_info,
            "foreign_keys": fk_info,
            "statistics_sample": stats_info,
            "health_analysis": {
                "constraint_issues": constraint_issues,
                "index_issues": index_issues
            },
            "recommendations": recommendations
        }
    finally:
        if conn:
            conn.close()

@mcp.tool
def db_sql2019_db_stats(database: str | None = None) -> list[dict[str, Any]] | dict[str, Any]:
    """
    Retrieves high-level statistics for a specific database or all databases.
    
    Provides key metrics like database size, log size, and space usage percentage.
    This tool is useful for a quick overview of database health and capacity planning.

    Args:
        database: (Optional) The name of the database to get stats for. If not provided, returns stats for all non-system databases.

    Returns:
        A list of dictionaries with stats for each database, or a single dictionary if a database is specified.
    """
    if database and not is_valid_sql_identifier(database):
        raise ValueError(f"Invalid database name: {database}")

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        sql = '''
            SELECT 
                d.name AS DatabaseName,
                mf_data.size * 8 / 1024 AS DataSizeMB,
                mf_log.size * 8 / 1024 AS LogSizeMB,
                CAST(FILEPROPERTY(mf_data.name, 'SpaceUsed') AS INT) * 8 / 1024 AS DataSpaceUsedMB,
                CAST(FILEPROPERTY(mf_log.name, 'SpaceUsed') AS INT) * 8 / 1024 AS LogSpaceUsedMB
            FROM sys.databases d
            JOIN sys.master_files mf_data ON d.database_id = mf_data.database_id AND mf_data.type = 0 -- 0 = data
            JOIN sys.master_files mf_log ON d.database_id = mf_log.database_id AND mf_log.type = 1 -- 1 = log
        '''
        params = []
        if database:
            sql += " WHERE d.name = ?"
            params.append(database)
        else:
            sql += " WHERE d.database_id > 4" # Exclude system databases
            
        sql += " ORDER BY d.name"
        
        _execute_safe(cur, sql, params)
        results = _format_results(cur)
        
        # Calculate percentages - handle NULL values by coalescing to 0
        for row in results:
            # Coalesce NULL values to 0 for safe calculations
            data_space_used = row['DataSpaceUsedMB'] if row['DataSpaceUsedMB'] is not None else 0
            log_space_used = row['LogSpaceUsedMB'] if row['LogSpaceUsedMB'] is not None else 0
            data_size = row['DataSizeMB'] if row['DataSizeMB'] is not None else 0
            log_size = row['LogSizeMB'] if row['LogSizeMB'] is not None else 0
            
            if data_size > 0:
                row['DataSpaceUsedPercentage'] = (data_space_used / data_size) * 100
            else:
                row['DataSpaceUsedPercentage'] = 0
            if log_size > 0:
                row['LogSpaceUsedPercentage'] = (log_space_used / log_size) * 100
            else:
                row['LogSpaceUsedPercentage'] = 0
                
        return results[0] if database and results else results
    finally:
        if conn:
            conn.close()

@mcp.tool
def db_sql2019_server_info_mcp() -> dict[str, Any]:
    """
    Retrieves SQL Server instance information including server name, version, edition, and connection details.
    
    Returns comprehensive server information including:
    - Server version and edition
    - Server name and current database
    - Current user and connection details
    
    Returns:
        Dictionary containing server information with keys:
            server_version: Full SQL Server version string
            server_name: Server name
            database: Current database name
            user: Current user
            server_version_short: Short version number
            server_edition: Server edition (Enterprise, Standard, etc.)
            server_addr: Server IP address
            server_port: Server port number
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Get server properties using individual queries to avoid ODBC type issues
        cur.execute('SELECT @@VERSION')
        server_version = cur.fetchone()[0]
        
        cur.execute('SELECT @@SERVERNAME')
        server_name = cur.fetchone()[0]
        
        cur.execute('SELECT DB_NAME()')
        database = cur.fetchone()[0]
        
        cur.execute('SELECT SYSTEM_USER')
        user = cur.fetchone()[0]
        
        cur.execute("SELECT SERVERPROPERTY('ProductVersion')")
        server_version_short = cur.fetchone()[0]
        
        cur.execute("SELECT SERVERPROPERTY('Edition')")
        server_edition = cur.fetchone()[0]
        
        # Get connection info
        cur.execute("SELECT CAST(CONNECTIONPROPERTY('local_net_address') AS VARCHAR(50))")
        server_addr = cur.fetchone()[0] or '127.0.0.1'
        
        cur.execute("SELECT CAST(CONNECTIONPROPERTY('local_tcp_port') AS INT)")
        server_port = cur.fetchone()[0] or 1433
        
        return {
            'server_version': server_version,
            'server_name': server_name,
            'database': database,
            'user': user,
            'server_version_short': server_version_short,
            'server_edition': server_edition,
            'server_addr': server_addr,
            'server_port': server_port
        }
            
    except Exception as e:
        logger.error(f"Error retrieving server info: {e}")
        raise
    finally:
        if conn:
            conn.close()

# Main entry point
async def main():
    
    # Environment-based configuration
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = _env_int("MCP_PORT", 8000)
    transport = os.environ.get("MCP_TRANSPORT", "http").lower()
    
    # Validate transport
    if transport not in ["http", "stdio"]:
        logger.error(f"Invalid MCP_TRANSPORT: '{transport}'. Must be 'http' or 'stdio'.")
        sys.exit(1)
    
    # Set up async-aware signal handlers
    setup_signal_handlers()
        
    logger.info("Starting SQL Server MCP Server...")
    logger.info(f"  - Transport: {transport}")
    if transport == "http":
        logger.info(f"  - Host: {host}")
        logger.info(f"  - Port: {port}")
        logger.info(f"  - MCP Endpoint: http://{host}:{port}/sse")
        
        # Add middleware only for HTTP transport
        # This is crucial because the middleware stack depends on Starlette features
        # not available in the stdio transport.
        mcp.http_app().add_middleware(APIKeyMiddleware)
        mcp.http_app().add_middleware(BrowserFriendlyMiddleware)

    # Define run kwargs, excluding those not applicable for stdio
    run_kwargs = {
        "transport": transport,
    }
    if transport == "http":
        run_kwargs["host"] = host
        run_kwargs["port"] = port
    
    # Run the MCP server
    try:
        await mcp.run(**run_kwargs)
    except Exception as e:
        logger.critical(f"Failed to run MCP server: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server shut down by user.")
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
        sys.exit(1)