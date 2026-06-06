$base = 'http://localhost:8085/mcp/'
$initBody = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"0.1.0","capabilities":{},"clientInfo":{"name":"prod-verify","version":"1.0.0"}}}'

function New-McpSession {
    $r = curl.exe -i -s -X POST $base -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d $initBody
    return [regex]::Match($r,'mcp-session-id:\s*([0-9a-f]+)').Groups[1].Value
}

function Invoke-McpTool {
    param([string]$Sid,[string]$ToolName,[string]$Args,[int]$Timeout=90)
    $body = '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"' + $ToolName + '","arguments":' + $Args + '}}'
    $raw = curl.exe -s --max-time $Timeout -X POST $base `
        -H 'Content-Type: application/json' `
        -H 'Accept: application/json, text/event-stream' `
        -H "mcp-session-id: $Sid" `
        -d $body
    $json = (($raw -split 'event: message data: ') | Where-Object { $_ -match '^\{"jsonrpc":"2\.0"' } | Select-Object -Last 1).Trim()
    return $json | ConvertFrom-Json
}

function SC { param($r) return $r.result.structuredContent }
function IsErr { param($r) return $r.result.isError }
function Text0 { param($r) return $r.result.content[0].text }
function Summary { param($r,$label)
    if ($r.result) {
        $sc = SC $r
        if ($sc) {
            Write-Host ("PASS|$label|isError=$(IsErr $r)|keys=$($sc.PSObject.Properties.Name -join ',')")
        } else {
            $t = Text0 $r
            Write-Host ("PASS|$label|isError=$(IsErr $r)|text=$($t.Substring(0,[Math]::Min(160,$t.Length)))")
        }
    } else {
        Write-Host "FAIL|$label|NO_RESULT"
    }
}

# === GROUP A: Instance 1 Named tools ===
$sid = New-McpSession; Write-Host "SID-A=$sid"
$r = Invoke-McpTool $sid 'db_primary_sql2019_latency_report' '{"actor":"vfy-a"}'; Summary $r 'latency_primary'
$r = Invoke-McpTool $sid 'db_primary_sql2019_select' '{"actor":"vfy-a","sql":"SELECT TOP 5 name, create_date FROM sys.tables ORDER BY create_date DESC","database_name":"US_UserData"}'; Summary $r 'select_primary_US_UserData'
$r = Invoke-McpTool $sid 'db_primary_sql2019_exec_proc' '{"actor":"vfy-a","proc_name":"USGISPRO_800.dbo.usp_CaptureProcOutput","params":["sp_who",""],"database_name":"USGISPRO_800"}'; Summary $r 'exec_proc_primary'
$r = Invoke-McpTool $sid 'db_primary_sql2019_block_report' '{"actor":"vfy-a","database_name":"USGISPRO_800"}'; Summary $r 'block_report_primary'
$r = Invoke-McpTool $sid 'db_primary_sql2019_top_queries_report' '{"actor":"vfy-a","limit":10,"database_name":"General"}'; Summary $r 'top_queries_primary'

# === GROUP B: Instance 1 Named tools continued ===
$sid = New-McpSession; Write-Host "SID-B=$sid"
$r = Invoke-McpTool $sid 'db_primary_sql2019_active_sessions_report' '{"actor":"vfy-b","limit":10}'; Summary $r 'active_sessions_primary'
$r = Invoke-McpTool $sid 'db_primary_sql2019_index_health_report' '{"actor":"vfy-b","limit":20,"database_name":"US_RT_User_800"}'; Summary $r 'index_health_primary_USRTUser800'
$r = Invoke-McpTool $sid 'db_secondary_sql2019_latency_report' '{"actor":"vfy-b"}'; Summary $r 'latency_secondary'
$r = Invoke-McpTool $sid 'db_secondary_sql2019_select' '{"actor":"vfy-b","sql":"SELECT TOP 5 name, create_date FROM sys.tables ORDER BY create_date DESC","database_name":"GeoGrid"}'; Summary $r 'select_secondary_GeoGrid'
$r = Invoke-McpTool $sid 'db_secondary_sql2019_exec_proc' '{"actor":"vfy-b","proc_name":"dbo.usp_RunApprovedMaintenance","params":[]}'; Summary $r 'exec_proc_secondary'

# === GROUP C: Instance 2 Named tools ===
$sid = New-McpSession; Write-Host "SID-C=$sid"
$r = Invoke-McpTool $sid 'db_secondary_sql2019_block_report' '{"actor":"vfy-c","database_name":"PrizmPremier"}'; Summary $r 'block_report_secondary'
$r = Invoke-McpTool $sid 'db_secondary_sql2019_top_queries_report' '{"actor":"vfy-c","limit":10,"database_name":"ListGateway"}'; Summary $r 'top_queries_secondary'
$r = Invoke-McpTool $sid 'db_secondary_sql2019_active_sessions_report' '{"actor":"vfy-c","limit":10}'; Summary $r 'active_sessions_secondary'
$r = Invoke-McpTool $sid 'db_secondary_sql2019_index_health_report' '{"actor":"vfy-c","limit":20,"database_name":"US_Spatial_800"}'; Summary $r 'index_health_secondary_USSpatial'
$r = Invoke-McpTool $sid 'db_1_sql2019_list_object' '{"actor":"vfy-c","database_name":"General","object_type":"table"}'; Summary $r 'list_object_inst1_General'

# === GROUP D: Numbered tools + error handling ===
$sid = New-McpSession; Write-Host "SID-D=$sid"
$r = Invoke-McpTool $sid 'db_1_sql2019_execute_query' '{"actor":"vfy-d","database_name":"USGISPRO_800","sql_statement":"SELECT TOP 5 name, type_desc FROM sys.objects WHERE type_desc=''USER_TABLE'' ORDER BY name","view_mode":"COMPACT"}'; Summary $r 'execute_query_inst1'
$r = Invoke-McpTool $sid 'db_2_sql2019_list_tools' '{"actor":"vfy-d"}'; Summary $r 'list_tools_inst2'
$r = Invoke-McpTool $sid 'db_2_sql2019_list_object' '{"actor":"vfy-d","database_name":"ListGateway","object_type":"table"}'; Summary $r 'list_object_inst2_ListGateway'
$r = Invoke-McpTool $sid 'db_2_sql2019_execute_query' '{"actor":"vfy-d","database_name":"PrizmPremier","sql_statement":"SELECT TOP 5 name, type_desc FROM sys.objects WHERE type_desc=''USER_TABLE'' ORDER BY name","view_mode":"COMPACT"}'; Summary $r 'execute_query_inst2'
$r = Invoke-McpTool $sid 'db_primary_sql2019_select' '{"actor":"vfy-d","sql":"SELECT 1","database_name":"NONEXISTENT_DB"}'; Summary $r 'error_invalid_db'
$r = Invoke-McpTool $sid 'db_primary_sql2019_select' '{"actor":"vfy-d","sql":"DROP TABLE test","database_name":"master"}'; Summary $r 'error_write_denied'
$r = Invoke-McpTool $sid 'db_1_sql2019_analyze_tab_health' '{"actor":"vfy-d"}'; Summary $r 'error_missing_required_param'

Write-Host "=== DONE ==="
