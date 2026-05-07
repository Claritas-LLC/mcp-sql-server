#!/usr/bin/env bash
set -euo pipefail

mkdir -p reports/blocking
TS=$(date -u +%Y%m%d-%H%M%S)
OUT="reports/blocking/blocking-$TS.json"

PRIMARY=$(curl -fsS -X POST http://localhost:8080/mcp/tools/db_primary_sql2019_block_report -H 'Content-Type: application/json' -d '{"actor":"reporter"}')
SECONDARY=$(curl -fsS -X POST http://localhost:8080/mcp/tools/db_secondary_sql2019_block_report -H 'Content-Type: application/json' -d '{"actor":"reporter"}')

cat > "$OUT" <<JSON
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "primary": $PRIMARY,
  "secondary": $SECONDARY
}
JSON

echo "Blocking report written to $OUT"
