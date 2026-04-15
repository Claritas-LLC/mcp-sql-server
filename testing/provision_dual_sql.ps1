$ErrorActionPreference = 'Stop'

$container1 = 'mcp_sqlserver_test_01'
$container2 = 'mcp_sqlserver_test_02'
$password = 'McpTestPassword123!'

foreach ($name in @($container1, $container2)) {
    docker rm -f $name 2>$null | Out-Null
}

docker run -d --name $container1 -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD=$password -p 14331:1433 mcr.microsoft.com/mssql/server:2019-latest | Out-Null
docker run -d --name $container2 -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD=$password -p 14332:1433 mcr.microsoft.com/mssql/server:2019-latest | Out-Null

Write-Host 'Waiting for SQL Server instances to accept connections...'

function Wait-SqlReady {
    param(
        [string]$ContainerName
    )

    for ($i = 0; $i -lt 60; $i++) {
        docker exec $ContainerName /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $password -C -Q "SELECT 1" 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            docker exec $ContainerName /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P $password -Q "SELECT 1" 2>$null | Out-Null
        }
        if ($LASTEXITCODE -eq 0) {
            Write-Host "$ContainerName is ready"
            return
        }
        Start-Sleep -Seconds 2
    }

    throw "Timed out waiting for $ContainerName"
}

Wait-SqlReady -ContainerName $container1
Wait-SqlReady -ContainerName $container2

Write-Host 'Provisioning complete.'
