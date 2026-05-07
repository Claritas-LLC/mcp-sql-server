$ErrorActionPreference = "Stop"

$iterations = 10
$latencies = @()

for ($i = 0; $i -lt $iterations; $i++) {
  $body = @{ sql = "SELECT TOP 1 GETUTCDATE() AS ts"; actor = "perf-smoke" } | ConvertTo-Json -Compress
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  Invoke-RestMethod -Method Post -Uri http://localhost:8080/mcp/tools/db_primary_sql2019_select -ContentType "application/json" -Body $body | Out-Null
  $sw.Stop()
  $latencies += $sw.ElapsedMilliseconds
}

$sorted = $latencies | Sort-Object
$p50 = $sorted[[int]($sorted.Count * 0.50)]
$p95 = $sorted[[int]([Math]::Min($sorted.Count - 1, [Math]::Floor($sorted.Count * 0.95)))]
$p99 = $sorted[[int]([Math]::Min($sorted.Count - 1, [Math]::Floor($sorted.Count * 0.99)))]

"P50=$p50 ms" | Write-Host
"P95=$p95 ms" | Write-Host
"P99=$p99 ms" | Write-Host
