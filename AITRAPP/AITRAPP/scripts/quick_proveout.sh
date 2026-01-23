#!/usr/bin/env bash
# Quick prove-out script for PAPER session
set -euo pipefail

API="${API:-http://localhost:8000}"

echo "🔍 Quick Prove-Out Test"
echo "======================"
echo ""

# 1. Check API health
echo "1️⃣  Checking API health..."
if curl -s "${API}/health" >/dev/null 2>&1; then
    echo "   ✅ API is responding"
    curl -s "${API}/health" | jq '.' 2>/dev/null || curl -s "${API}/health"
else
    echo "   ❌ API not responding - start with: make start-paper"
    exit 1
fi
echo ""

# 2. Check critical metrics
echo "2️⃣  Checking critical metrics..."
METRICS=$(curl -s "${API}/metrics" 2>/dev/null | grep -E '^trader_(is_leader|orders_placed_total|oco_children_created_total|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds)' | sort || echo "")

if [ -n "$METRICS" ]; then
    echo "$METRICS" | while IFS= read -r line; do
        echo "   $line"
    done
    
    # Check leader
    LEADER=$(echo "$METRICS" | grep "trader_is_leader" | awk '{print $2}' || echo "0")
    if [ "$LEADER" = "1" ]; then
        echo "   ✅ Leader lock acquired"
    else
        echo "   ⚠️  Leader lock not acquired (trader_is_leader=$LEADER)"
    fi
    
    # Check heartbeats
    MKT_HB=$(echo "$METRICS" | grep "trader_marketdata_heartbeat_seconds" | awk '{print $2}' || echo "999")
    ORD_HB=$(echo "$METRICS" | grep "trader_order_stream_heartbeat_seconds" | awk '{print $2}' || echo "999")
    
    if [ -n "$MKT_HB" ] && [ -n "$ORD_HB" ]; then
        MKT_VAL=$(echo "$MKT_HB" | awk '{print int($1)}')
        ORD_VAL=$(echo "$ORD_HB" | awk '{print int($1)}')
        if [ "$MKT_VAL" -lt 5 ] && [ "$ORD_VAL" -lt 5 ]; then
            echo "   ✅ Heartbeats OK (marketdata=${MKT_HB}s, order_stream=${ORD_HB}s)"
        else
            echo "   ⚠️  Stale heartbeats (marketdata=${MKT_HB}s, order_stream=${ORD_HB}s)"
        fi
    fi
else
    echo "   ⚠️  Metrics not available yet (orchestrator may not be initialized)"
fi
echo ""

# 3. Check positions
echo "3️⃣  Checking positions..."
POSITIONS=$(curl -s "${API}/positions" 2>/dev/null | jq '.' || echo "{}")
POS_COUNT=$(echo "$POSITIONS" | jq '.count // . | length' 2>/dev/null || echo "0")
echo "   Positions: $POS_COUNT"
if [ "$POS_COUNT" = "0" ] || [ "$POS_COUNT" = "null" ]; then
    echo "   ✅ No open positions"
else
    echo "   📊 Open positions:"
    echo "$POSITIONS" | jq '.' 2>/dev/null || echo "$POSITIONS"
fi
echo ""

# 4. Test kill-switch (flatten)
echo "4️⃣  Testing kill-switch (flatten)..."
FLATTEN_START=$(date +%s%3N 2>/dev/null || python3 -c "import time; print(int(time.time() * 1000))")
FLATTEN_RESP=$(curl -s -X POST "${API}/flatten" \
    -H "Content-Type: application/json" \
    -d '{"reason":"paper_smoke"}' 2>&1)

if echo "$FLATTEN_RESP" | jq -e '.status' >/dev/null 2>&1; then
    echo "   ✅ Flatten command accepted"
    echo "$FLATTEN_RESP" | jq '.' 2>/dev/null || echo "$FLATTEN_RESP"
    
    # Wait and check positions
    sleep 2
    FLATTEN_END=$(date +%s%3N 2>/dev/null || python3 -c "import time; print(int(time.time() * 1000))")
    FLATTEN_MS=$((FLATTEN_END - FLATTEN_START))
    
    POS_AFTER=$(curl -s "${API}/positions" 2>/dev/null | jq '.count // . | length' 2>/dev/null || echo "0")
    
    if [ "$POS_AFTER" = "0" ] || [ "$POS_AFTER" = "null" ]; then
        echo "   ✅ All positions flattened"
    else
        echo "   ⚠️  Positions still open: $POS_AFTER"
    fi
    
    if [ "$FLATTEN_MS" -le 2000 ]; then
        echo "   ✅ Flatten speed OK (${FLATTEN_MS}ms, max=2000ms)"
    else
        echo "   ⚠️  Flatten exceeded 2s: ${FLATTEN_MS}ms"
    fi
else
    echo "   ⚠️  Flatten endpoint error:"
    echo "$FLATTEN_RESP" | head -3
fi
echo ""

# 5. Summary
echo "✅ Quick Prove-Out Complete!"
echo ""
echo "📋 Summary:"
echo "   - API: Responding"
echo "   - Metrics: Checked"
echo "   - Positions: $POS_COUNT"
echo "   - Kill-switch: Tested"
echo ""
echo "🎯 Next: Monitor with dashboard: make live-dashboard && tmux attach -t live"

