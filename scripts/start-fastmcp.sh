#!/usr/bin/env bash
set -euo pipefail

required=(
  "config/instances.yaml"
  "config/runtime-policy.yaml"
  "config/rate-limit.yaml"
  "policy/sql-allowlist.yaml"
  "policy/sql-denylist.yaml"
)

for f in "${required[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "Missing required file: $f" >&2
    exit 1
  fi
done

if [[ -f "config/tool-flags.override.json" ]]; then
  export FASTMCP_TOOL_ENABLE_FLAGS_JSON
  FASTMCP_TOOL_ENABLE_FLAGS_JSON="$(cat config/tool-flags.override.json)"
  echo "Loaded global tool flag overrides from config/tool-flags.override.json"
fi

if [[ -f "config/instance-tool-flags.override.json" ]]; then
  export FASTMCP_INSTANCE_TOOL_ENABLE_FLAGS_JSON
  FASTMCP_INSTANCE_TOOL_ENABLE_FLAGS_JSON="$(cat config/instance-tool-flags.override.json)"
  echo "Loaded instance tool flag overrides from config/instance-tool-flags.override.json"
fi

docker compose -f docker/docker-compose.yml up -d
