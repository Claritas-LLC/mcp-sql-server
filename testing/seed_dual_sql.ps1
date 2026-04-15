$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$sqlFile = Join-Path $repoRoot 'setup_test_simple.sql'
if (-not (Test-Path $sqlFile)) {
    throw "Seed SQL file not found: $sqlFile"
}

$containers = @('mcp_sqlserver_test_01', 'mcp_sqlserver_test_02')
$password = 'McpTestPassword123!'

foreach ($container in $containers) {
    Write-Host "Seeding $container ..."

    $null = docker cp $sqlFile "$container`:/tmp/setup_test_database.sql"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to copy $sqlFile to $container:/tmp/setup_test_database.sql"
        exit $LASTEXITCODE
    }

    $resetSql = "IF DB_ID('TEST_DB') IS NOT NULL BEGIN ALTER DATABASE TEST_DB SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE TEST_DB; END"
    $null = docker exec $container /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $password -C -b -Q $resetSql 2>$null
    if ($LASTEXITCODE -ne 0) {
        $null = docker exec $container /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P $password -b -Q $resetSql
    }

    docker exec $container /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $password -C -b -i /tmp/setup_test_database.sql 2>$null
    if ($LASTEXITCODE -ne 0) {
        docker exec $container /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P $password -b -i /tmp/setup_test_database.sql
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to execute setup_test_database.sql in $container using both sqlcmd paths"
            exit $LASTEXITCODE
        }
    }

    $count = docker exec $container /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $password -C -d TEST_DB -Q "SET NOCOUNT ON; SELECT COUNT(*) AS c FROM sales.Customers" -h -1 2>$null
    if ($LASTEXITCODE -ne 0) {
        $count = docker exec $container /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P $password -d TEST_DB -Q "SET NOCOUNT ON; SELECT COUNT(*) AS c FROM sales.Customers" -h -1
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Verification query failed for $container"
    }

    Write-Host ("{0} sales.Customers rows: {1}" -f $container, ($count | Out-String).Trim())
}

Write-Host 'Seeding complete.'
