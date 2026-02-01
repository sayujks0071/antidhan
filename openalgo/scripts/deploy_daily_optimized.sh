#!/bin/bash
# Auto-generated deployment script

echo 'Stopping all strategies...'
pkill -f 'python3 openalgo/strategies/scripts/'

echo 'Starting optimized strategies...'
nohup python3 openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py --symbol BANKNIFTY --api_key $OPENALGO_APIKEY > openalgo/log/strategies/ai_hybrid_reversion_breakout_BANKNIFTY.log 2>&1 &
nohup python3 openalgo/strategies/scripts/supertrend_vwap_strategy.py --symbol NIFTY --api_key $OPENALGO_APIKEY > openalgo/log/strategies/supertrend_vwap_strategy_NIFTY.log 2>&1 &

echo 'Deployment complete.'
