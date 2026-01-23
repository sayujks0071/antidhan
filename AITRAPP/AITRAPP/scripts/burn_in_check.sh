#!/usr/bin/env bash
# Quick burn-in check script
set -euo pipefail

API="${API:-http://localhost:8000}"

echo "🔥 Burn-In Check"
echo "================"
echo ""

# 1. Leader lock
echo "1️⃣  Leader lock:"
LEADER=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_is_leader[^_]/ {print $2; exit}' || echo "0")
if [[ "${LEADER:-0}" == "1" ]]; then
    echo "   ✅ Leader lock: 1"
else
    echo "   ❌ Leader lock: ${LEADER:-0} (expected 1)"
fi
echo ""

# 2. Heartbeats
echo "2️⃣  Heartbeats:"
MD=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_marketdata_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")
ORD=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_order_stream_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")
SCAN=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_scan_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")

if awk "BEGIN{exit !(${MD:-999} < 5)}"; then
    echo "   ✅ Market data: ${MD}s"
else
    echo "   ❌ Market data: ${MD}s (expected < 5s)"
fi

if awk "BEGIN{exit !(${ORD:-999} < 5)}"; then
    echo "   ✅ Order stream: ${ORD}s"
else
    echo "   ❌ Order stream: ${ORD}s (expected < 5s)"
fi

if awk "BEGIN{exit !(${SCAN:-999} < 5)}"; then
    echo "   ✅ Scan: ${SCAN}s"
else
    echo "   ❌ Scan: ${SCAN}s (expected < 5s)"
fi
echo ""

# 3. Supervisor state
echo "3️⃣  Supervisor state:"
STATE=$(curl -s "$API/debug/supervisor/status" 2>/dev/null | jq -r '.state // 0' || echo "0")
TICKS=$(curl -s "$API/debug/supervisor/status" 2>/dev/null | jq -r '.ticks // 0' || echo "0")
if [[ "$STATE" == "1" ]]; then
    echo "   ✅ Supervisor: running (ticks: $TICKS)"
else
    echo "   ❌ Supervisor: state=$STATE (expected 1)"
fi
echo ""

# 4. Readiness
echo "4️⃣  Readiness:"
READY=$(curl -s "$API/ready" 2>/dev/null | jq -r '.status // "not_ready"' || echo "not_ready")
if [[ "$READY" == "ready" ]]; then
    echo "   ✅ System ready"
else
    echo "   ❌ System not ready"
fi
echo ""

# 5. Summary
echo "📊 Summary:"
if [[ "${LEADER:-0}" == "1" ]] && \
   awk "BEGIN{exit !(${MD:-999} < 5 && ${ORD:-999} < 5 && ${SCAN:-999} < 5)}" && \
   [[ "$STATE" == "1" ]] && \
   [[ "$READY" == "ready" ]]; then
    echo "   ✅ ALL CHECKS PASS"
    exit 0
else
    echo "   ❌ SOME CHECKS FAILED"
    exit 1
fi

