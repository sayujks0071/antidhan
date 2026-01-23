#!/bin/bash
# Red-team drills - run before Day-1 paper burn-in

set -e

echo "🔴 Red-Team Drills - Testing System Resilience"
echo ""

# 1. WebSocket Drop
echo "1️⃣ Testing WebSocket drop (30s)..."
echo "   Simulate: Kill broker WS for 30s"
echo "   Expected: Reconnects; no duplicate children"
echo "   ⚠️  Manual test required - check logs for reconnection"
echo ""

# 2. LIMIT Rejection
echo "2️⃣ Testing LIMIT rejection..."
echo "   Simulate: Force stale price LIMIT"
echo "   Expected: Dedupe holds; retry bounded"
python scripts/test_idempotency.py
echo ""

# 3. Partial Fill
echo "3️⃣ Testing partial fill..."
echo "   Simulate: Tiny qty partial fill"
echo "   Expected: Reprice within freeze/tick; OCO for remainder"
echo "   ⚠️  Manual test required - simulate partial fill"
echo ""

# 4. Illiquidity
echo "4️⃣ Testing illiquidity..."
echo "   Simulate: Wide spreads > threshold"
echo "   Expected: Risk block fires; no new entries"
echo "   ⚠️  Manual test required - simulate wide spreads"
echo ""

# 5. Redis Down
echo "5️⃣ Testing Redis failure..."
echo "   Stopping Redis..."
docker compose stop redis
sleep 2
echo "   Checking API health..."
curl -s localhost:8000/health | jq '.status' || echo "⚠️  API not responding"
echo "   Starting Redis..."
docker compose start redis
sleep 2
echo "   ✅ Redis restarted"
echo ""

# 6. DB Restart
echo "6️⃣ Testing DB restart..."
echo "   Restarting Postgres..."
docker compose restart postgres
sleep 5
echo "   Checking API health..."
curl -s localhost:8000/health | jq '.status' || echo "⚠️  API not responding"
echo "   Testing idempotency..."
python scripts/test_idempotency.py
echo ""

# 7. Clock Skew
echo "7️⃣ Testing clock skew..."
echo "   Current TZ: $(date +%Z)"
echo "   Config TZ: Asia/Kolkata"
echo "   ⚠️  Verify time-stops use config TZ"
echo ""

# 8. Network Flap
echo "8️⃣ Testing network flap..."
echo "   Simulate: Drop outbound for 10s"
echo "   Expected: No duplicate orders after recover"
echo "   ⚠️  Manual test required - simulate network flap"
echo ""

# 9. EOD Race
echo "9️⃣ Testing EOD race condition..."
echo "   Simulate: Position at 15:19"
echo "   Expected: Tighten at 15:20, flat at 15:25"
echo "   ⚠️  Manual test required - test during EOD"
echo ""

# 10. Kill Switch Under Load
echo "🔟 Testing kill switch under load..."
echo "   Generating load..."
ab -n 50 -c 5 http://localhost:8000/metrics >/dev/null 2>&1 || true
echo "   Pressing kill switch..."
START=$(date +%s)
curl -s -X POST localhost:8000/flatten >/dev/null
END=$(date +%s)
DURATION=$((END - START))
echo "   Duration: ${DURATION}s"
if [ $DURATION -le 2 ]; then
    echo "   ✅ Kill switch ≤ 2s"
else
    echo "   ❌ Kill switch > 2s"
fi
echo ""

echo "✅ Red-team drills complete"
echo ""
echo "📋 Manual tests required:"
echo "   - WebSocket drop"
echo "   - Partial fill"
echo "   - Illiquidity"
echo "   - Network flap"
echo "   - EOD race"
echo ""
echo "Review logs and verify all automated tests passed."

