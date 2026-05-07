#!/usr/bin/env bash
set -euo pipefail

ITER=10
OUT=()

for _ in $(seq 1 "$ITER"); do
  START=$(date +%s%3N)
  curl -fsS -X POST http://localhost:8080/mcp/tools/db_primary_sql2019_select \
    -H 'Content-Type: application/json' \
    -d '{"sql":"SELECT TOP 1 GETUTCDATE() AS ts","actor":"perf-smoke"}' >/dev/null
  END=$(date +%s%3N)
  OUT+=("$((END-START))")
done

printf "%s\n" "${OUT[@]}" | sort -n > /tmp/latencies.txt
COUNT=$(wc -l < /tmp/latencies.txt)
P50_IDX=$((COUNT * 50 / 100))
P95_IDX=$((COUNT * 95 / 100))
P99_IDX=$((COUNT * 99 / 100))

P50=$(sed -n "$((P50_IDX==0?1:P50_IDX))p" /tmp/latencies.txt)
P95=$(sed -n "$((P95_IDX==0?1:P95_IDX))p" /tmp/latencies.txt)
P99=$(sed -n "$((P99_IDX==0?1:P99_IDX))p" /tmp/latencies.txt)

echo "P50=$P50 ms"
echo "P95=$P95 ms"
echo "P99=$P99 ms"
