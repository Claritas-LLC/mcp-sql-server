$ErrorActionPreference = "Stop"

$image = "ghcr.io/company/fastmcp-sql2019:1.0.0"
Write-Host "Pulling pinned image $image"
docker pull $image

$globalToolFlagsPath = "config/tool-flags.override.json"
$instanceToolFlagsPath = "config/instance-tool-flags.override.json"

if (Test-Path $globalToolFlagsPath) {
	$env:FASTMCP_TOOL_ENABLE_FLAGS_JSON = (Get-Content $globalToolFlagsPath -Raw)
	Write-Host "Loaded global tool flag overrides from $globalToolFlagsPath"
}

if (Test-Path $instanceToolFlagsPath) {
	$env:FASTMCP_INSTANCE_TOOL_ENABLE_FLAGS_JSON = (Get-Content $instanceToolFlagsPath -Raw)
	Write-Host "Loaded instance tool flag overrides from $instanceToolFlagsPath"
}

Write-Host "Deploying service"
docker compose -f docker/docker-compose.yml up -d --force-recreate

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$manifest = "evidence/deploy-manifest-$ts.txt"
New-Item -ItemType Directory -Force -Path "evidence" | Out-Null
"image=$image" | Out-File $manifest -Encoding utf8
"timestamp=$ts" | Out-File $manifest -Append -Encoding utf8
"tool_flags_override_file=$globalToolFlagsPath" | Out-File $manifest -Append -Encoding utf8
"instance_tool_flags_override_file=$instanceToolFlagsPath" | Out-File $manifest -Append -Encoding utf8

docker ps --filter "name=fastmcp-sql2019" --format "{{.ID}} {{.Image}} {{.Status}}" | Out-File $manifest -Append -Encoding utf8
Write-Host "Deployment manifest written to $manifest"
