#!/bin/bash
# Start Option Strategy with API Key
# Usage: ./start_option_strategy.sh [api_key]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=================================================================================="
echo "  STARTING OPTION STRATEGY"
echo "=================================================================================="
echo ""

# Get API key from argument or environment
if [ -n "$1" ]; then
    API_KEY="$1"
elif [ -n "$OPENALGO_APIKEY" ]; then
    API_KEY="$OPENALGO_APIKEY"
else
    echo "⚠️  No API key provided!"
    echo ""
    echo "📋 To get your API key:"
    echo "   1. Go to: http://127.0.0.1:5001"
    echo "   2. Navigate to: API Keys (or Settings → API Keys)"
    echo "   3. Generate/Copy your API key"
    echo ""
    echo "Then run:"
    echo "   export OPENALGO_APIKEY='your_api_key_here'"
    echo "   $0"
    echo ""
    echo "OR:"
    echo "   $0 your_api_key_here"
    echo ""
    echo "Using demo_key for now (will need real key for trading)..."
    API_KEY="demo_key"
fi

# Set environment
export OPENALGO_HOST="http://127.0.0.1:5001"
export OPENALGO_APIKEY="$API_KEY"

echo "✅ Configuration:"
echo "   Host: $OPENALGO_HOST"
echo "   API Key: ${API_KEY:0:20}..."
echo ""

# Change to OpenAlgo directory
cd "$OPENALGO_DIR"

# Start strategy
echo "🚀 Starting Advanced Options Ranker..."
echo ""

python3 strategies/scripts/advanced_options_ranker.py
