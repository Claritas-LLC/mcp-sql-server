$ErrorActionPreference = "Stop"

Write-Host "Validating required config files..."
$required = @(
  "config/instances.yaml",
  "config/runtime-policy.yaml",
  "config/rate-limit.yaml",
  "policy/sql-allowlist.yaml",
  "policy/sql-denylist.yaml"
)

foreach ($f in $required) {
  if (-not (Test-Path $f)) {
    throw "Missing required file: $f"
  }
}

$globalToolFlagsPath = "config/tool-flags.override.json"
if (Test-Path $globalToolFlagsPath) {
  $env:FASTMCP_TOOL_ENABLE_FLAGS_JSON = (Get-Content $globalToolFlagsPath -Raw)
  Write-Host "Loaded global tool flag overrides from $globalToolFlagsPath"
}

$instanceToolFlagsPath = "config/instance-tool-flags.override.json"
if (Test-Path $instanceToolFlagsPath) {
  $env:FASTMCP_INSTANCE_TOOL_ENABLE_FLAGS_JSON = (Get-Content $instanceToolFlagsPath -Raw)
  Write-Host "Loaded instance tool flag overrides from $instanceToolFlagsPath"
}

Write-Host "Starting FastMCP SQL Server container..."
docker compose -f docker/docker-compose.yml up -d
