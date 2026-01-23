#!/bin/bash
set -e

# Default to NIFTY if not set
SYMBOL=${SYMBOL:-NIFTY}
STRATEGY=${STRATEGY:-IronCondor}

echo "Starting Live Trading for $SYMBOL with $STRATEGY"

# Safety flags
export TRADING_MODE=live
export I_UNDERSTAND_LIVE_TRADING=true

# Check if keys are present (basic check, runner does deeper check)
if [ -z "$KITE_API_KEY" ] || [ -z "$KITE_ACCESS_TOKEN" ]; then
    echo "Error: KITE_API_KEY and KITE_ACCESS_TOKEN must be set."
    echo "Please source your .env file or export these variables."
    exit 1
fi

# Run the runner module
python -m packages.core.runner live --strategy "$STRATEGY" --symbol "$SYMBOL"
