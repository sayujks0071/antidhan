#!/bin/bash
# Restart strategies to pick up OPENALGO_APIKEY environment variable

cd /Users/mac/dyad-apps/openalgo

# Strategy IDs that need restart
STRATEGY_IDS=(
    "ai_hybrid_reversion_breakout_20260120112302"
    "advanced_ml_momentum_strategy_20260120112512"
    "supertrend_vwap_strategy_20260120112816"
)

echo "Restarting strategies to apply OPENALGO_APIKEY..."
echo ""

for strategy_id in "${STRATEGY_IDS[@]}"; do
    # Get PID from config
    PID=$(python3 -c "
import json
from pathlib import Path
configs = json.loads(Path('strategies/strategy_configs.json').read_text())
print(configs.get('$strategy_id', {}).get('pid', ''))
" 2>/dev/null)
    
    if [ -n "$PID" ] && [ "$PID" != "None" ] && [ "$PID" != "null" ]; then
        echo "Stopping strategy $strategy_id (PID: $PID)..."
        kill $PID 2>/dev/null || true
        sleep 2
    fi
done

echo ""
echo "✅ Strategies stopped. Please restart them via:"
echo "   http://127.0.0.1:5001/python/"
echo ""
echo "Or wait for auto-restart if they're scheduled."
