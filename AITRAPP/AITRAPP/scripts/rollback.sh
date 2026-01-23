#!/bin/bash
# Rollback procedure: Pause → Flatten → Switch to PAPER → Alert

set -e

echo "🔄 Starting rollback procedure..."
echo ""

# 1. Pause trading
echo "1️⃣ Pausing trading..."
curl -s -X POST localhost:8000/pause | jq '.status' || echo "⚠️  Pause failed"
sleep 1

# 2. Flatten all positions
echo "2️⃣ Flattening all positions..."
curl -s -X POST localhost:8000/flatten | jq '.status' || echo "⚠️  Flatten failed"
sleep 2

# 3. Verify positions closed
echo "3️⃣ Verifying positions closed..."
POSITIONS=$(curl -s localhost:8000/positions | jq '.count')
if [ "$POSITIONS" -eq 0 ]; then
    echo "✅ All positions closed"
else
    echo "⚠️  Warning: $POSITIONS positions still open"
fi

# 4. Switch to PAPER mode
echo "4️⃣ Switching to PAPER mode..."
curl -s -X POST localhost:8000/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"PAPER"}' | jq '.mode' || echo "⚠️  Mode switch failed"

echo ""
echo "✅ Rollback complete"
echo ""
echo "⚠️  IMPORTANT: Restart the API to fully reset to PAPER mode"
echo "   Kill the process and run: make paper"

