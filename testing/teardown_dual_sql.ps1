$ErrorActionPreference = 'Continue'

foreach ($name in @('mcp_sqlserver_test_01', 'mcp_sqlserver_test_02')) {
    $output = docker rm -f $name 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Removed $name"
    } elseif (($output | Out-String) -match "No such container") {
        Write-Host "Not present $name"
    } else {
        Write-Warning ("Failed to remove {0}: {1}" -f $name, (($output | Out-String).Trim()))
    }
}

Write-Host 'Dual SQL teardown complete.'
