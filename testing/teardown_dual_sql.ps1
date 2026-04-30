$ErrorActionPreference = 'Continue'

foreach ($name in @('mcp_sqlserver_test_01', 'mcp_sqlserver_test_02')) {
    docker rm -f $name 2>$null | Out-Null
    Write-Host "Removed $name"
}

Write-Host 'Dual SQL teardown complete.'
