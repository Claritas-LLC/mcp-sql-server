#!/usr/bin/env bash
set -euo pipefail

TS=$(date -u +%Y%m%d-%H%M%S)
OUT="evidence/evidence-$TS"
mkdir -p "$OUT"

docker inspect fastmcp-sql2019 > "$OUT/container-inspect.json"
curl -fsS http://localhost:8080/diagnostics/health > "$OUT/health.json"
curl -fsS http://localhost:8080/diagnostics/security > "$OUT/security.json"
curl -fsS http://localhost:8080/diagnostics/audit-summary > "$OUT/audit-summary.json"

sha256sum config/instances.yaml config/runtime-policy.yaml config/rate-limit.yaml policy/sql-allowlist.yaml policy/sql-denylist.yaml > "$OUT/config-hashes.txt"

tar -czf "evidence/evidence-$TS.tar.gz" -C "$OUT" .
echo "Evidence archived at evidence/evidence-$TS.tar.gz"
