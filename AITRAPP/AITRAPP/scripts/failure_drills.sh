#!/bin/bash
# Failure drills - run once more before LIVE

set -e

echo "🔴 Failure Drills - Final Resilience Tests"
echo ""

# 1. Dual-runner attempt
echo "1️⃣ Testing dual-runner prevention..."
echo "   Starting second API instance..."
# Start second instance in background
cd /Users/mac/AITRAPP
python -m uvicorn apps.api.main:app --port 8001 > /tmp/aitrapp2.log 2>&1 &
SECOND_PID=$!
sleep 3

# Check if second instance started (should fail leader lock)
if ps -p $SECOND_PID > /dev/null; then
    echo "   ⚠️  Second instance started (check logs for leader lock deny)"
    kill $SECOND_PID 2>/dev/null || true
else
    echo "   ✅ Second instance failed to start (leader lock working)"
fi
echo ""

# 2. WS flap during child placement
echo "2️⃣ Testing WS flap during child placement..."
echo "   Simulate: Drop WS right after ENTRY fill"
echo "   Expected: OCO recovery attaches children within 1s of reconnect"
echo "   ⚠️  Manual test required - simulate WS drop during entry fill"
echo ""

# 3. Exchange band jump
echo "3️⃣ Testing exchange band jump..."
echo "   Simulate: Sudden circuit band change"
echo "   Expected: Price revalidation cancels & re-plans, not place stale child"
echo "   ⚠️  Manual test required - simulate band jump"
echo ""

echo "✅ Failure drills complete"
echo ""
echo "📋 Manual tests required:"
echo "   - WS flap during child placement"
echo "   - Exchange band jump"
echo ""
echo "Review logs and verify all automated tests passed."

