$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path "reports/blocking" | Out-Null
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$out = "reports/blocking/blocking-$ts.json"

$payload = @{ actor = "reporter" } | ConvertTo-Json -Compress
$primary = Invoke-RestMethod -Method Post -Uri http://localhost:8080/mcp/tools/db_primary_sql2019_block_report -ContentType "application/json" -Body $payload
$secondary = Invoke-RestMethod -Method Post -Uri http://localhost:8080/mcp/tools/db_secondary_sql2019_block_report -ContentType "application/json" -Body $payload

@{
  timestamp = (Get-Date).ToUniversalTime().ToString("o")
  primary = $primary
  secondary = $secondary
} | ConvertTo-Json -Depth 8 | Out-File $out -Encoding utf8

Write-Host "Blocking report written to $out"
