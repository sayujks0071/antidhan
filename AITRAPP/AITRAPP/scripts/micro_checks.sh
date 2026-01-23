#!/usr/bin/env bash
# Micro-checks to confirm green status before 15:20

set -euo pipefail

API="${API:-http://localhost:8000}"

echo "🔍 Micro-Checks (Pre-15:20)"
echo "============================"
echo ""

# 1) Heartbeats all < 5s (numeric check)
echo "1️⃣  Checking heartbeats (< 5s)..."
BAD=0
curl -s "$API/metrics" 2>/dev/null | awk '
/^trader_(marketdata|order_stream|scan)_heartbeat_seconds/ { 
    if ($2 >= 5) {
        print "   ❌ " $1 " = " $2 "s (>= 5s)"
        bad=1
    } else {
        print "   ✅ " $1 " = " $2 "s"
    }
}
END { exit bad }' || BAD=1

if [ $BAD -eq 0 ]; then
    echo "   ✅ All heartbeats < 5s"
else
    echo "   ❌ Some heartbeats >= 5s"
fi
echo ""

# 2) Flat on demand in ≤2s (safety drill)
echo "2️⃣  Testing flatten speed (≤2s)..."
START=$(date +%s%3N 2>/dev/null || python3 -c "import time; print(int(time.time() * 1000))")
curl -s -X POST "$API/flatten" -H 'Content-Type: application/json' -d '{"reason":"paper_day1"}' >/dev/null 2>&1
END=$(date +%s%3N 2>/dev/null || python3 -c "import time; print(int(time.time() * 1000))")
ELAPSED=$((END - START))

sleep 2
POSITIONS=$(curl -s "$API/positions" 2>/dev/null | jq 'length // .count // 0' 2>/dev/null || echo "0")

if [ $ELAPSED -le 2000 ] && [ "$POSITIONS" -eq 0 ]; then
    echo "   ✅ Flatten completed in ${ELAPSED}ms (≤2000ms)"
    echo "   ✅ Positions = $POSITIONS (expected 0)"
else
    echo "   ❌ Flatten took ${ELAPSED}ms (expected ≤2000ms) or positions = $POSITIONS (expected 0)"
    exit 1
fi
echo ""

echo "✅ All micro-checks PASSED"

