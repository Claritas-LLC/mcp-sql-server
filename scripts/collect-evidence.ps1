$ErrorActionPreference = "Stop"

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$out = "evidence/evidence-$ts"
New-Item -ItemType Directory -Force -Path $out | Out-Null

docker inspect fastmcp-sql2019 | Out-File "$out/container-inspect.json" -Encoding utf8
Invoke-RestMethod http://localhost:8080/diagnostics/health | ConvertTo-Json -Depth 8 | Out-File "$out/health.json"
Invoke-RestMethod http://localhost:8080/diagnostics/security | ConvertTo-Json -Depth 8 | Out-File "$out/security.json"
Invoke-RestMethod http://localhost:8080/diagnostics/audit-summary | ConvertTo-Json -Depth 8 | Out-File "$out/audit-summary.json"

Get-FileHash config/instances.yaml, config/runtime-policy.yaml, config/rate-limit.yaml, policy/sql-allowlist.yaml, policy/sql-denylist.yaml -Algorithm SHA256 |
  Format-Table -AutoSize | Out-String | Out-File "$out/config-hashes.txt"

Compress-Archive -Path "$out/*" -DestinationPath "evidence/evidence-$ts.zip" -Force
Write-Host "Evidence archived at evidence/evidence-$ts.zip"
