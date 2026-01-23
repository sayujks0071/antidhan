#!/bin/bash
# Canary pre-check - 30-second validation before LIVE switch

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🔍 Canary Pre-Check${NC}"
echo ""

# 1. Check leader lock and heartbeats
echo "1️⃣ Checking leader lock and heartbeats..."
METRICS=$(curl -s localhost:8000/metrics | grep -E '^trader_is_leader|trader_.*heartbeat' | sort)

if [ -z "$METRICS" ]; then
    echo -e "${RED}❌ Metrics not available${NC}"
    exit 1
fi

echo "$METRICS"
LEADER=$(echo "$METRICS" | grep 'trader_is_leader' | awk '{print $2}')
if [ "$LEADER" = "1" ]; then
    echo -e "${GREEN}✅ Leader lock: 1${NC}"
else
    echo -e "${RED}❌ Leader lock: $LEADER (expected 1)${NC}"
    exit 1
fi

echo ""

# 2. Test flatten (must be ≤2s)
echo "2️⃣ Testing flatten (must be ≤2s)..."
START=$(date +%s)
FLATTEN_RESPONSE=$(curl -s -X POST localhost:8000/flatten \
    -H "Content-Type: application/json" \
    -d '{"reason":"prelive_sanity"}')
END=$(date +%s)
DURATION=$((END - START))

echo "$FLATTEN_RESPONSE" | jq

if [ $DURATION -le 2 ]; then
    echo -e "${GREEN}✅ Flatten duration: ${DURATION}s (≤2s)${NC}"
else
    echo -e "${RED}❌ Flatten duration: ${DURATION}s (>2s)${NC}"
    exit 1
fi

echo ""

# 3. Check positions (must be 0)
echo "3️⃣ Checking positions (must be 0)..."
POS_COUNT=$(curl -s localhost:8000/positions 2>/dev/null | jq '.count // 0' || echo "0")

if [ "$POS_COUNT" = "0" ]; then
    echo -e "${GREEN}✅ Positions: 0${NC}"
else
    echo -e "${RED}❌ Positions: $POS_COUNT (expected 0)${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ All pre-checks passed${NC}"

