#!/bin/bash
# Check logs for all strategies that had 403 errors

cd "$(dirname "$0")/.."

echo "=================================================================================="
echo "  CHECKING LOGS FOR ALL FIXED STRATEGIES"
echo "=================================================================================="
echo ""

strategies=(
    "mcx_elite_strategy"
    "mcx_neural_strategy"
    "advanced_ml_momentum_strategy"
    "natural_gas_clawdbot_strategy"
    "crude_oil_enhanced_strategy"
)

for strategy in "${strategies[@]}"; do
    echo "=================================================================================="
    echo "  $strategy"
    echo "=================================================================================="
    
    # Find log file
    log_file=$(find log/strategies -name "*${strategy}*" -type f 2>/dev/null | head -1)
    
    if [ -z "$log_file" ]; then
        echo "  ⚠️  No log file found"
        echo ""
        continue
    fi
    
    echo "  Log File: $log_file"
    echo "  Size: $(ls -lh "$log_file" 2>/dev/null | awk '{print $5}')"
    echo "  Modified: $(ls -lth "$log_file" 2>/dev/null | awk '{print $6, $7, $8}')"
    echo ""
    
    # Show last 20 lines
    echo "  Last 20 lines:"
    echo "  -------------------------------------------------------------------------------"
    tail -20 "$log_file" 2>/dev/null | sed 's/^/  /'
    echo ""
    
    # Check for errors
    error_count=$(grep -iE "ERROR|403|forbidden|invalid.*api" "$log_file" 2>/dev/null | tail -5 | wc -l | tr -d ' ')
    if [ "$error_count" -gt 0 ]; then
        echo "  ⚠️  Recent Errors Found:"
        grep -iE "ERROR|403|forbidden|invalid.*api" "$log_file" 2>/dev/null | tail -5 | sed 's/^/    /'
    else
        echo "  ✅ No recent errors found"
    fi
    
    echo ""
done

echo "=================================================================================="
echo "  SUMMARY"
echo "=================================================================================="
echo ""
echo "To monitor logs in real-time, use:"
echo "  tail -f log/strategies/<strategy_name>*.log"
echo ""
