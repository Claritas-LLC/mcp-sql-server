$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path "reports/latency" | Out-Null
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$out = "reports/latency/metrics-$ts.prom"
$summaryOut = "reports/latency/tool-usage-summary-$ts.json"
Invoke-WebRequest -UseBasicParsing -Uri http://localhost:8080/diagnostics/metrics | Select-Object -ExpandProperty Content | Out-File $out -Encoding utf8
Invoke-RestMethod http://localhost:8080/diagnostics/tool-usage-summary | ConvertTo-Json -Depth 8 | Out-File $summaryOut -Encoding utf8
Write-Host "Latency metrics snapshot: $out"
Write-Host "Tool usage summary: $summaryOut"
