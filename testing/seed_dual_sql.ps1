$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$sqlFile = Join-Path $repoRoot 'setup_test_simple.sql'
if (-not (Test-Path $sqlFile)) {
    throw "Seed SQL file not found: $sqlFile"
}

$targets = @(
    @{ Container = 'mcp_sqlserver_test_01'; Database = 'test1' },
    @{ Container = 'mcp_sqlserver_test_02'; Database = 'test2' }
)
$password = 'McpTestPassword123!'
$templateSql = Get-Content $sqlFile -Raw

foreach ($target in $targets) {
    $container = $target.Container
    $databaseName = $target.Database
    $tempFile = Join-Path $env:TEMP ("setup_{0}.sql" -f $databaseName)
    $seedSql = $templateSql.Replace('TEST_DB', $databaseName)
    Set-Content -Path $tempFile -Value $seedSql -Encoding UTF8

    Write-Host "Seeding $container with database $databaseName ..."

    docker cp $tempFile "$container`:/tmp/setup_test_database.sql" | Out-Null

    $resetSql = "IF DB_ID('$databaseName') IS NOT NULL BEGIN ALTER DATABASE [$databaseName] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [$databaseName]; END"
    docker exec $container /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $password -C -b -Q $resetSql 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        docker exec $container /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P $password -b -Q $resetSql | Out-Null
    }

    docker exec $container /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $password -C -b -i /tmp/setup_test_database.sql 2>$null
    if ($LASTEXITCODE -ne 0) {
        docker exec $container /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P $password -b -i /tmp/setup_test_database.sql
    }

    $count = docker exec $container /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $password -C -d $databaseName -Q "SET NOCOUNT ON; SELECT COUNT(*) AS c FROM sales.Customers" -h -1 2>$null
    if ($LASTEXITCODE -ne 0) {
        $count = docker exec $container /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P $password -d $databaseName -Q "SET NOCOUNT ON; SELECT COUNT(*) AS c FROM sales.Customers" -h -1
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Verification query failed for $container ($databaseName)"
    }

    Remove-Item $tempFile -ErrorAction SilentlyContinue
    Write-Host ("{0} {1}.sales.Customers rows: {2}" -f $container, $databaseName, ($count | Out-String).Trim())
}

Write-Host 'Seeding complete.'
