#!/usr/bin/env bash
# Prometheus flare: print key metrics panel
set -euo pipefail

API="${API:-http://localhost:8000}"

echo "📊 Prometheus Flare - Key Metrics"
echo "=================================="
echo ""

# Get metrics
METRICS=$(curl -s "$API/metrics" 2>/dev/null || echo "")

if [ -z "$METRICS" ]; then
    echo "❌ API not responding"
    exit 1
fi

# Leader changes (delta today - approximate from current value)
LEADER_CHANGES=$(echo "$METRICS" | awk '/^trader_leader_changes_total/ {print $2; exit}' || echo "0")
echo "🔄 Leader Changes (total): $LEADER_CHANGES"

# Order ack latency p95
ORDER_ACK_P95=$(echo "$METRICS" | awk '/^trader_order_ack_latency_ms{quantile="0.95"}/ {print $2; exit}' || echo "N/A")
if [[ "$ORDER_ACK_P95" != "N/A" ]]; then
    ORDER_ACK_P95_MS=${ORDER_ACK_P95%.*}
    echo "⚡ Order Ack Latency P95: ${ORDER_ACK_P95_MS}ms"
else
    echo "⚡ Order Ack Latency P95: N/A (no data yet)"
fi

# Scan heartbeat max (last 15m - approximate from current value)
SCAN_HB=$(echo "$METRICS" | awk '/^trader_scan_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")
SCAN_HB_MS=$(awk "BEGIN{printf \"%.0f\", $SCAN_HB * 1000}")
echo "🔍 Scan Heartbeat: ${SCAN_HB_MS}ms"

# Additional useful metrics
IS_LEADER=$(echo "$METRICS" | awk '/^trader_is_leader[^_]/ {print $2; exit}' || echo "0")
MD_HB=$(echo "$METRICS" | awk '/^trader_marketdata_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")
ORDER_HB=$(echo "$METRICS" | awk '/^trader_order_stream_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")

echo ""
echo "📈 Status:"
echo "   Leader: $IS_LEADER"
echo "   Market Data HB: ${MD_HB}s"
echo "   Order Stream HB: ${ORDER_HB}s"
echo "   Scan HB: ${SCAN_HB}s"

echo ""
echo "✅ Flare complete"


