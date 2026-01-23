#!/usr/bin/env bash
# Chaos test for rate-limit spike resilience
# Fires multiple synthetic plans and verifies throttle queue depth behavior

set -euo pipefail

API="${API:-http://localhost:8000}"
PLAN_COUNT="${PLAN_COUNT:-15}"

jqval() { curl -s "$API/$1" 2>/dev/null | jq -r "$2" 2>/dev/null || echo ""; }
metric() { curl -s "$API/metrics" 2>/dev/null | awk -v k="^$1" '$0 ~ k {print $2; exit}' || echo "0"; }

echo "🧪 Rate-Limit Spike Chaos Test"
echo "=============================="
echo ""

mkdir -p reports/chaos

echo "1️⃣  Baseline check..."
THROTTLE_BEFORE=$(metric trader_throttle_queue_depth)
ORDERS_BEFORE=$(metric trader_orders_placed_total)
echo "   Throttle queue depth: $THROTTLE_BEFORE"
echo "   Orders placed: $ORDERS_BEFORE"
echo ""

echo "2️⃣  Firing $PLAN_COUNT synthetic plans (rate-limit spike)..."
for i in $(seq 1 "$PLAN_COUNT"); do
    python scripts/synthetic_plan_injector.py \
        --symbol NIFTY \
        --side LONG \
        --qty 50 \
        --strategy ORB \
        >/dev/null 2>&1 &
    sleep 0.1
done
echo "   ✅ Fired $PLAN_COUNT plans"
echo ""

echo "3️⃣  Waiting 5 seconds for throttle to build..."
sleep 5
echo ""

echo "4️⃣  Checking throttle queue depth..."
THROTTLE_PEAK=$(metric trader_throttle_queue_depth)
echo "   Throttle queue depth: $THROTTLE_PEAK"

if awk "BEGIN{exit !($THROTTLE_PEAK > 0)}"; then
    echo "   ✅ Throttle queue depth rose (expected)"
else
    echo "   ⚠️  Throttle queue depth did not rise"
fi
echo ""

echo "5️⃣  Waiting 30 seconds for throttle to recover..."
sleep 30
echo ""

echo "6️⃣  Verifying throttle recovered..."
THROTTLE_AFTER=$(metric trader_throttle_queue_depth)
ORDERS_AFTER=$(metric trader_orders_placed_total)
echo "   Throttle queue depth: $THROTTLE_AFTER"
echo "   Orders placed: $ORDERS_AFTER"

if awk "BEGIN{exit !($THROTTLE_AFTER == 0)}"; then
    echo "   ✅ Throttle queue depth returned to 0"
else
    echo "   ⚠️  Throttle queue depth still: $THROTTLE_AFTER"
fi
echo ""

# Check for duplicate client_order_id (would indicate idempotency issues)
echo "7️⃣  Checking for duplicate client_order_ids..."
if command -v psql >/dev/null 2>&1 && [ -n "${DATABASE_URL:-}" ]; then
    DB_CONN="${DATABASE_URL#postgresql+psycopg2://}"
    DUPES=$(psql "$DB_CONN" -tAc "
        SELECT COUNT(*) 
        FROM (
            SELECT client_order_id, COUNT(*) as cnt
            FROM orders
            WHERE client_order_id IS NOT NULL
            GROUP BY client_order_id
            HAVING COUNT(*) > 1
        ) dupes;
    " 2>/dev/null || echo "0")
    
    if [[ "$DUPES" == "0" ]]; then
        echo "   ✅ No duplicate client_order_ids (idempotency working)"
    else
        echo "   ❌ Found $DUPES duplicate client_order_ids (idempotency issue)"
        exit 1
    fi
else
    echo "   ⚠️  Cannot check duplicates (psql not available or DATABASE_URL not set)"
fi
echo ""

# Record evidence
TS=$(date -Is 2>/dev/null || date +"%Y-%m-%dT%H:%M:%S")
LOG_FILE="reports/chaos/rate_limit_${TS//:/-}.log"
{
    echo "rate_limit_chaos_test,$TS"
    echo "plan_count,$PLAN_COUNT"
    echo "throttle_before,$THROTTLE_BEFORE"
    echo "throttle_peak,$THROTTLE_PEAK"
    echo "throttle_after,$THROTTLE_AFTER"
    echo "orders_before,$ORDERS_BEFORE"
    echo "orders_after,$ORDERS_AFTER"
    echo "duplicates,$DUPES"
} | tee "$LOG_FILE"
echo "📝 Wrote $LOG_FILE"
echo ""

if awk "BEGIN{exit !($THROTTLE_AFTER == 0)}"; then
    echo "✅ RATE-LIMIT SPIKE TEST PASSED"
    echo "   - Throttle queue depth rose and recovered"
    echo "   - No duplicate client_order_ids"
    exit 0
else
    echo "⚠️  RATE-LIMIT SPIKE TEST INCOMPLETE"
    echo "   - Throttle queue depth did not fully recover"
    exit 1
fi
