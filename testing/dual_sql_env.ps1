# TEST-ONLY script. Do not use these settings in production.
# This script intentionally supports local insecure test transport and warns when
# credentials are set via DB_01_USER/DB_01_PASSWORD.

param(
    [switch]$WriteMode
)

$ErrorActionPreference = 'Stop'

$env:DB_01_SERVER = '127.0.0.1'
$env:DB_01_PORT = '14331'
$env:DB_01_USER = 'sa'
$env:DB_01_PASSWORD = 'McpTestPassword123!'
$env:DB_01_NAME = 'TEST_DB'
$env:DB_01_DRIVER = 'ODBC Driver 17 for SQL Server'
$env:DB_01_ENCRYPT = 'no'
$env:DB_01_TRUST_CERT = 'yes'

$env:DB_02_SERVER = '127.0.0.1'
$env:DB_02_PORT = '14332'
$env:DB_02_USER = 'sa'
$env:DB_02_PASSWORD = 'McpTestPassword123!'
$env:DB_02_NAME = 'TEST_DB'
$env:DB_02_DRIVER = 'ODBC Driver 17 for SQL Server'
$env:DB_02_ENCRYPT = 'no'
$env:DB_02_TRUST_CERT = 'yes'

$env:MCP_TRANSPORT = 'http'
$env:MCP_HOST = '127.0.0.1'
$env:MCP_PORT = '8085'
$env:MCP_HTTP_URL = 'http://127.0.0.1:8085'
$env:MCP_LOG_LEVEL = 'INFO'
$env:MCP_AUDIT_LOG_QUERIES = 'false'
$env:MCP_ALLOW_RAW_PROMPTS = 'false'

$db01Server = ($env:DB_01_SERVER | ForEach-Object { $_.ToLowerInvariant() })
if ($db01Server -notin @('localhost', '127.0.0.1')) {
    throw "Unsafe DB_01_SERVER '$($env:DB_01_SERVER)'. This test script only allows localhost/127.0.0.1."
}

$db01Encrypt = ($env:DB_01_ENCRYPT | ForEach-Object { $_.ToLowerInvariant() })
$db01TrustCert = ($env:DB_01_TRUST_CERT | ForEach-Object { $_.ToLowerInvariant() })
$isInsecureTls = ($db01Encrypt -eq 'no') -or ($db01TrustCert -eq 'yes')
if ($isInsecureTls) {
    Write-Warning "Insecure test TLS configuration detected (DB_01_ENCRYPT=$($env:DB_01_ENCRYPT), DB_01_TRUST_CERT=$($env:DB_01_TRUST_CERT))."
    Write-Warning "Credentials supplied via DB_01_USER/DB_01_PASSWORD are for local testing only and must never be reused in production."

    if (($env:FORCE_INSECURE_TEST | ForEach-Object { $_.ToLowerInvariant() }) -ne 'true') {
        throw "Refusing insecure test config without explicit opt-in. Set FORCE_INSECURE_TEST=true to continue."
    }
}


# ---
# SECURITY NOTE (OWASP A05, A07):
# The following block sets environment variables for MCP write mode and authentication.
# The hardcoded 'mcp-test-key' and API key authentication are for local testing ONLY.
# Never use these values or this configuration in production environments.
# In production, always manage secrets via environment variables or a secure vault (see users-manual.md).
# Write-mode and test credentials must never be enabled or reused in production.
# ---

# $WriteMode controls whether destructive/write operations are enabled for testing.
#
# If enabled, test API key and write permissions are set for local test automation.
# If disabled, write is blocked and no test credentials are present.
# This ensures that production deployments cannot accidentally run with test credentials or write-mode enabled.
$enableWriteMode = $WriteMode.IsPresent -or (-not $PSBoundParameters.ContainsKey('WriteMode'))

if ($enableWriteMode) {
    $env:MCP_ALLOW_WRITE = 'true'           # Allow write-mode tools for test
    $env:MCP_CONFIRM_WRITE = 'true'         # Auto-confirm write actions for test
    $env:FASTMCP_AUTH_TYPE = 'apikey'       # Use API key auth for test
    $env:FASTMCP_API_KEY = 'mcp-test-key'   # Hardcoded test key (never use in prod)
} else {
    $env:MCP_ALLOW_WRITE = 'false'          # Block write-mode tools
    $env:MCP_CONFIRM_WRITE = 'false'        # Block write confirmations
    $env:FASTMCP_AUTH_TYPE = ''             # No auth for read-only
    $env:FASTMCP_API_KEY = ''               # No API key for read-only
}

Write-Host 'Dual SQL MCP test environment variables configured for current shell.'
Write-Host ("MCP_ALLOW_WRITE={0}, MCP_CONFIRM_WRITE={1}" -f $env:MCP_ALLOW_WRITE, $env:MCP_CONFIRM_WRITE)
