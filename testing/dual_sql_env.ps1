param(
    [switch]$WriteMode = $true
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

if ($WriteMode) {
    $env:MCP_ALLOW_WRITE = 'true'
    $env:MCP_CONFIRM_WRITE = 'true'
    $env:FASTMCP_AUTH_TYPE = 'apikey'
    $env:FASTMCP_API_KEY = 'mcp-test-key'
} else {
    $env:MCP_ALLOW_WRITE = 'false'
    $env:MCP_CONFIRM_WRITE = 'false'
    $env:FASTMCP_AUTH_TYPE = ''
    $env:FASTMCP_API_KEY = ''
}

Write-Host 'Dual SQL MCP test environment variables configured for current shell.'
Write-Host ("MCP_ALLOW_WRITE={0}, MCP_CONFIRM_WRITE={1}" -f $env:MCP_ALLOW_WRITE, $env:MCP_CONFIRM_WRITE)
