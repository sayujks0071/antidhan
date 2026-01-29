#!/bin/bash
# Auto-generated deployment script based on daily optimization

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

LOG_DIR=openalgo/strategies/logs
mkdir -p $LOG_DIR

echo 'Stopping strategies...'
pkill -f 'strategies/scripts/.*.py' || true

echo 'Starting optimized strategies...'

echo 'Starting advanced_ml_momentum_strategy...'
nohup python3 openalgo/strategies/scripts/advanced_ml_momentum_strategy.py > openalgo/strategies/logs/advanced_ml_momentum_strategy_live.log 2>&1 &
echo 'Started advanced_ml_momentum_strategy with PID $!'

echo 'Deployment complete.'
