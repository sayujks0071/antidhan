#!/bin/bash
# 60-minute smoke test - validates core functionality

set -e

echo "🧪 Running 60-minute smoke test..."
echo ""

# Health & metrics
echo "1️⃣ Checking health & metrics..."
curl -s localhost:8000/metrics | grep -E '^trader_' | sort | head -10
echo ""

curl -s localhost:8000/state | jq '.mode, .is_paused, .is_market_open' || echo "⚠️  State endpoint not responding"
echo ""

curl -s localhost:8000/risk | jq '.portfolio_heat_pct, .daily_pnl, .can_take_new_position' || echo "⚠️  Risk endpoint not responding"
echo ""

# Kill switch path
echo "2️⃣ Testing kill switch path..."
curl -s -X POST localhost:8000/pause | jq '.status' || echo "⚠️  Pause failed"
echo ""

curl -s -X POST localhost:8000/flatten | jq '.status' || echo "⚠️  Flatten failed"
echo ""

sleep 2

curl -s localhost:8000/positions | jq '.count' || echo "⚠️  Positions endpoint not responding"
echo ""

# Resume after test
curl -s -X POST localhost:8000/resume | jq '.status' || echo "⚠️  Resume failed"
echo ""

# Metrics incrementing
echo "3️⃣ Testing metrics under load..."
ab -n 10 -c 2 http://localhost:8000/metrics >/dev/null 2>&1 || true
curl -s localhost:8000/metrics | grep trader_orders_placed_total || echo "⚠️  Metrics not incrementing"
echo ""

echo "✅ Smoke test complete"
echo ""
echo "📋 Next: Run idempotency test manually:"
echo "   python scripts/test_idempotency.py"

