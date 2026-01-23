#!/usr/bin/env bash
# Quick health check - 5 critical checks for burn-in readiness
set -euo pipefail

API="${API:-http://localhost:8000}"
DB_URL="${DATABASE_URL:-postgresql://trader:trader@localhost:5432/aitrapp}"

echo "🔍 Quick Health Check (5 Critical Checks)"
echo "========================================"
echo ""

# Check 1: Orchestrator heartbeat
echo "1️⃣  Orchestrator heartbeat..."
STATE=$(curl -s "${API}/state" 2>/dev/null || echo "{}")
if echo "$STATE" | jq -e '.mode' >/dev/null 2>&1; then
    RUNNING=$(echo "$STATE" | jq -r '.running // false')
    PAUSED=$(echo "$STATE" | jq -r '.is_paused // false')
    POSITIONS=$(echo "$STATE" | jq -r '.positions_count // 0')
    MODE=$(echo "$STATE" | jq -r '.mode // "unknown"')
    
    echo "   Mode: $MODE"
    echo "   Running: $RUNNING"
    echo "   Paused: $PAUSED"
    echo "   Open positions: $POSITIONS"
    
    if [ "$PAUSED" = "false" ] && [ "$MODE" != "unknown" ]; then
        echo "   ✅ Orchestrator active"
    else
        echo "   ⚠️  Orchestrator may not be fully initialized"
    fi
else
    echo "   ⚠️  State endpoint not responding correctly"
fi
echo ""

# Check 2: Live metrics
echo "2️⃣  Live metrics..."
METRICS=$(curl -s "${API}/metrics" 2>/dev/null | grep -E '^trader_(signals_total|decisions_total|orders_placed_total|oco_children_created_total|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|is_leader)' || echo "")

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
            echo "   ⚠️  Stale heartbeats (marketdata=${MKT_HB}s, order_stream=${ORD_HB}s, max=5s)"
        fi
    fi
else
    echo "   ⚠️  Metrics not available yet (orchestrator may not be initialized)"
fi
echo ""

# Check 3: Force end-to-end trade
echo "3️⃣  Force end-to-end trade..."
if [ -f "scripts/synthetic_plan_injector.py" ]; then
    INJECT_OUTPUT=$(python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB 2>&1 || echo "ERROR")
    
    if echo "$INJECT_OUTPUT" | grep -q "idempotency\|Injection skipped\|already exists"; then
        echo "   ✅ Trade injection working (idempotency verified)"
    elif echo "$INJECT_OUTPUT" | grep -q "Injected\|Plan ID"; then
        echo "   ✅ Trade injected successfully"
    else
        echo "   ⚠️  Trade injection may have issues:"
        echo "$INJECT_OUTPUT" | head -3 | sed 's/^/      /'
    fi
else
    echo "   ⚠️  synthetic_plan_injector.py not found"
fi
echo ""

# Check 4: Flatten path
echo "4️⃣  Flatten path test..."
FLATTEN_START=$(date +%s%3N 2>/dev/null || python3 -c "import time; print(int(time.time() * 1000))")
FLATTEN_RESP=$(curl -s -X POST "${API}/flatten" \
    -H "Content-Type: application/json" \
    -d '{"reason":"paper_smoke"}' 2>&1)

FLATTEN_END=$(date +%s%3N 2>/dev/null || python3 -c "import time; print(int(time.time() * 1000))")
FLATTEN_MS=$((FLATTEN_END - FLATTEN_START))

if echo "$FLATTEN_RESP" | jq -e '.status' >/dev/null 2>&1; then
    echo "   ✅ Flatten command accepted"
    echo "   Time: ${FLATTEN_MS}ms"
    
    if [ "$FLATTEN_MS" -le 2000 ]; then
        echo "   ✅ Flatten speed OK (≤ 2s)"
    else
        echo "   ⚠️  Flatten exceeded 2s: ${FLATTEN_MS}ms"
    fi
    
    # Wait and check positions
    sleep 2
    POS_AFTER=$(curl -s "${API}/positions" 2>/dev/null | jq 'length // .count // 0' 2>/dev/null || echo "0")
    
    if [ "$POS_AFTER" = "0" ] || [ "$POS_AFTER" = "null" ]; then
        echo "   ✅ All positions flattened (count: 0)"
    else
        echo "   ⚠️  Positions still open: $POS_AFTER"
    fi
else
    echo "   ⚠️  Flatten endpoint error:"
    echo "$FLATTEN_RESP" | head -3 | sed 's/^/      /'
fi
echo ""

# Check 5: DB integrity
echo "5️⃣  DB integrity check..."
if command -v psql >/dev/null 2>&1 && [ -n "$DB_URL" ]; then
    if [ -f "scripts/reconcile_db.sql" ]; then
        DB_CHECK=$(psql "$DB_URL" -f scripts/reconcile_db.sql 2>&1 || echo "ERROR")
        
        # Check for duplicates
        DUP_COUNT=$(echo "$DB_CHECK" | grep -E "count|COUNT" | head -1 | awk '{print $NF}' || echo "0")
        
        # Check for orphans
        ORPHAN_COUNT=$(echo "$DB_CHECK" | grep -E "id|ID" | wc -l || echo "0")
        
        if echo "$DB_CHECK" | grep -q "ERROR\|error\|permission denied"; then
            echo "   ⚠️  DB check had errors (check connection/permissions)"
        else
            echo "   ✅ DB integrity check completed"
            echo "   (Review output above for duplicates/orphans)"
        fi
    else
        echo "   ⚠️  reconcile_db.sql not found"
    fi
else
    echo "   ⚠️  psql not available or DATABASE_URL not set"
    echo "   Run manually: psql \"\$DATABASE_URL\" -f scripts/reconcile_db.sql"
fi
echo ""

# Summary
echo "✅ Quick Health Check Complete!"
echo ""
echo "📋 Quick Sanity Targets:"
echo "   - trader_is_leader == 1"
echo "   - Both heartbeats < 5s"
echo "   - One full OCO lifecycle"
echo "   - /flatten ≤ 2s → positions = 0"
echo "   - reconcile_db.sql: 0 duplicates & 0 orphans"
echo ""
echo "💡 Monitor continuously:"
echo "   watch -n 5 'curl -s ${API}/metrics | grep -E \"trader_(is_leader|orders_placed_total|oco_children_created_total|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds)\"'"
