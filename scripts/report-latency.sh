#!/usr/bin/env bash
set -euo pipefail

mkdir -p reports/latency
TS=$(date -u +%Y%m%d-%H%M%S)
METRICS_OUT="reports/latency/metrics-$TS.prom"
SUMMARY_OUT="reports/latency/tool-usage-summary-$TS.json"
curl -fsS http://localhost:8080/diagnostics/metrics > "$METRICS_OUT"
curl -fsS http://localhost:8080/diagnostics/tool-usage-summary > "$SUMMARY_OUT"
echo "Latency metrics snapshot: $METRICS_OUT"
echo "Tool usage summary: $SUMMARY_OUT"
