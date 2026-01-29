#!/bin/bash
# Start Option Strategy on Port 5002 (Dhan)
# Usage: ./start_option_strategy_port5002.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# API Key
API_KEY="5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163"

echo "=================================================================================="
echo "  STARTING OPTION STRATEGY ON PORT 5002 (DHAN)"
echo "=================================================================================="
echo ""

# Set environment
export OPENALGO_HOST="http://127.0.0.1:5002"
export OPENALGO_APIKEY="$API_KEY"

echo "✅ Configuration:"
echo "   Host: $OPENALGO_HOST"
echo "   API Key: ${API_KEY:0:20}..."
echo ""

# Verify port 5002 is accessible
if ! curl -s http://127.0.0.1:5002/api/v1/ping > /dev/null 2>&1; then
    echo "❌ Error: Port 5002 is not accessible!"
    echo "   Start OpenAlgo on port 5002 first"
    exit 1
fi

echo "✅ Port 5002 is accessible"
echo ""

# Change to OpenAlgo directory
cd "$OPENALGO_DIR"

# Start strategy
echo "🚀 Starting Advanced Options Ranker..."
echo ""

python3 strategies/scripts/advanced_options_ranker.py
