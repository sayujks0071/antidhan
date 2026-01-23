#!/usr/bin/env bash
# Print latency histogram p50/p95 from Prometheus metrics (EOD sanity check)
set -euo pipefail

API="${API:-http://localhost:8000}"

echo "📊 Latency Histogram Summary (EOD)"
echo "===================================="
echo ""

# Get order latency histogram
echo "Order Latency (ms):"
curl -s "$API/metrics" 2>/dev/null | grep '^trader_order_latency_ms_bucket' | \
  awk '{
    if ($1 ~ /le="0.05"/) p50=$2
    if ($1 ~ /le="0.95"/) p95=$2
    if ($1 ~ /le="1.0"/) p100=$2
  }
  END {
    if (p50) printf "   P50: %.2f ms\n", p50*1000
    if (p95) printf "   P95: %.2f ms\n", p95*1000
    if (p100) printf "   P100: %.2f ms\n", p100*1000
    if (!p50 && !p95) print "   ⚠️  No latency data yet"
  }'

echo ""

# Get tick-to-decision latency
echo "Tick-to-Decision Latency (ms):"
curl -s "$API/metrics" 2>/dev/null | grep '^trader_tick_to_decision_ms_bucket' | \
  awk '{
    if ($1 ~ /le="0.05"/) p50=$2
    if ($1 ~ /le="0.95"/) p95=$2
    if ($1 ~ /le="1.0"/) p100=$2
  }
  END {
    if (p50) printf "   P50: %.2f ms\n", p50*1000
    if (p95) printf "   P95: %.2f ms\n", p95*1000
    if (p100) printf "   P100: %.2f ms\n", p100*1000
    if (!p50 && !p95) print "   ⚠️  No latency data yet"
  }'

echo ""
echo "✅ Latency check complete"


