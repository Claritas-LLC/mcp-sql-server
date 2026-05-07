$ErrorActionPreference = "Stop"

Write-Host "Starting SQL Server 2019 test containers..."
docker compose -f testing/sqlserver/docker-compose.yml up -d

Write-Host "Waiting for containers to become healthy..."
$containers = @("mcp-sql2019-1", "mcp-sql2019-2")
foreach ($c in $containers) {
  $healthy = $false
  for ($i = 0; $i -lt 45; $i++) {
    $status = docker inspect --format "{{.State.Health.Status}}" $c 2>$null
    if ($status -eq "healthy") {
      $healthy = $true
      break
    }
    Start-Sleep -Seconds 2
  }
  if (-not $healthy) {
    throw "Container $c did not become healthy in time."
  }
}

Write-Host "Applying seed scripts..."
$sqlcmd1 = "/opt/mssql-tools18/bin/sqlcmd"
$sqlcmd2 = "/opt/mssql-tools/bin/sqlcmd"

$cmd1 = "if [ -x $sqlcmd1 ]; then $sqlcmd1 -S localhost -U sa -P 'YourStrong!Passw0rd1' -No -i /init/instance1.sql; else $sqlcmd2 -S localhost -U sa -P 'YourStrong!Passw0rd1' -No -i /init/instance1.sql; fi"
$cmd2 = "if [ -x $sqlcmd1 ]; then $sqlcmd1 -S localhost -U sa -P 'YourStrong!Passw0rd2' -No -i /init/instance2.sql; else $sqlcmd2 -S localhost -U sa -P 'YourStrong!Passw0rd2' -No -i /init/instance2.sql; fi"

docker exec mcp-sql2019-1 /bin/bash -lc $cmd1
docker exec mcp-sql2019-2 /bin/bash -lc $cmd2

Write-Host "Provisioning complete."
