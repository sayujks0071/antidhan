#!/bin/bash
# Deploy top-ranked strategies based on backtest results

cd "$(dirname "$0")/.."
SCRIPTS_DIR="scripts"
LOGS_DIR="logs"
mkdir -p "$LOGS_DIR"

echo "=========================================="
echo "DEPLOYING TOP-RANKED STRATEGIES"
echo "=========================================="
echo ""

# Based on backtest rankings (both tied at rank 1)
# Deploy top 2 strategies: NIFTY Greeks Enhanced and NIFTY Multi-Strike Momentum

STRATEGIES=(
    "nifty_greeks_enhanced_20260122.py:NIFTY Greeks Enhanced"
    "nifty_multistrike_momentum_20260122.py:NIFTY Multi-Strike Momentum"
)

deployed=0
already_running=0

for strategy_info in "${STRATEGIES[@]}"; do
    IFS=':' read -r filename name <<< "$strategy_info"
    strategy_path="$SCRIPTS_DIR/$filename"
    
    if [ ! -f "$strategy_path" ]; then
        echo "❌ Strategy file not found: $strategy_path"
        continue
    fi
    
    # Check if already running
    if pgrep -f "$filename" > /dev/null; then
        pid=$(pgrep -f "$filename" | head -1)
        echo "⚠️  Already running: $name (PID: $pid)"
        already_running=$((already_running + 1))
        continue
    fi
    
    # Deploy strategy
    log_file="$LOGS_DIR/${filename}.log"
    nohup python3 "$strategy_path" > "$log_file" 2>&1 &
    pid=$!
    
    sleep 1
    
    # Verify it's running
    if ps -p $pid > /dev/null 2>&1; then
        echo "✅ Deployed: $name"
        echo "   PID: $pid"
        echo "   Log: $log_file"
        deployed=$((deployed + 1))
    else
        echo "❌ Failed to start: $name"
        echo "   Check log: $log_file"
    fi
    echo ""
done

echo "=========================================="
echo "SUMMARY"
echo "=========================================="
echo "✅ Newly deployed: $deployed"
echo "⚠️  Already running: $already_running"
echo ""

# Show all running strategies
echo "Running strategies:"
ps aux | grep -E "nifty.*\.py|sensex.*\.py" | grep python3 | grep -v grep | while read line; do
    pid=$(echo "$line" | awk '{print $2}')
    cmd=$(echo "$line" | awk '{for(i=11;i<=NF;i++) printf "%s ", $i; print ""}')
    echo "  PID $pid: $cmd"
done

echo ""
echo "To view logs:"
echo "  tail -f $LOGS_DIR/nifty_greeks_enhanced_20260122.log"
echo "  tail -f $LOGS_DIR/nifty_multistrike_momentum_20260122.log"
