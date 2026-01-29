#!/bin/bash
# Start Option Strategies on Dhan OpenAlgo Instance (Port 5002)
# Usage: ./start_option_strategies.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
STRATEGIES_DIR="$OPENALGO_DIR/strategies/scripts"
API_HOST="http://127.0.0.1:5002"
API_KEY="${OPENALGO_APIKEY:-demo_key}"

echo "=================================================================================="
echo "  STARTING OPTION STRATEGIES (DHAN PORT 5002)"
echo "=================================================================================="
echo ""

# Check if OpenAlgo is running on port 5002
if ! curl -s "$API_HOST/api/v1/ping" > /dev/null 2>&1; then
    echo "❌ Error: OpenAlgo is not running on port 5002!"
    echo "   Start it first: ./scripts/start_dhan_openalgo.sh"
    exit 1
fi

echo "✅ OpenAlgo is running on port 5002"
echo ""

# Option strategies
OPTION_STRATEGIES=(
    "advanced_options_ranker.py"
)

# Check which strategies exist
AVAILABLE_STRATEGIES=()
for strategy in "${OPTION_STRATEGIES[@]}"; do
    if [ -f "$STRATEGIES_DIR/$strategy" ]; then
        AVAILABLE_STRATEGIES+=("$strategy")
    else
        echo "⚠️  Strategy not found: $strategy"
    fi
done

if [ ${#AVAILABLE_STRATEGIES[@]} -eq 0 ]; then
    echo "❌ No option strategies found!"
    exit 1
fi

echo "📋 Available Option Strategies:"
for strategy in "${AVAILABLE_STRATEGIES[@]}"; do
    echo "   - $strategy"
done
echo ""

# Start strategies
echo "🚀 Starting option strategies..."
echo ""

for strategy in "${AVAILABLE_STRATEGIES[@]}"; do
    STRATEGY_NAME=$(basename "$strategy" .py)
    echo "Starting: $STRATEGY_NAME"
    
    # Set environment variables
    export OPENALGO_HOST="$API_HOST"
    export OPENALGO_APIKEY="$API_KEY"
    export OPENALGO_PORT="5002"
    
    # Start strategy in background
    cd "$STRATEGIES_DIR"
    nohup python3 "$strategy" > "$OPENALGO_DIR/log/strategies/${STRATEGY_NAME}.log" 2>&1 &
    PID=$!
    
    echo "   ✅ Started with PID: $PID"
    echo "   📄 Log: log/strategies/${STRATEGY_NAME}.log"
    echo ""
done

echo "=================================================================================="
echo "  OPTION STRATEGIES STARTED"
echo "=================================================================================="
echo ""
echo "📊 Monitor logs:"
for strategy in "${AVAILABLE_STRATEGIES[@]}"; do
    STRATEGY_NAME=$(basename "$strategy" .py)
    echo "   tail -f log/strategies/${STRATEGY_NAME}.log"
done
echo ""
echo "🌐 Web UI: http://127.0.0.1:5002/python"
echo ""
