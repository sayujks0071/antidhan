#!/bin/bash
# Start Option Strategy with Provided API Key
# Usage: ./start_option_strategy_with_key.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# API Key (from user)
API_KEY="5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163"

echo "=================================================================================="
echo "  STARTING OPTION STRATEGY WITH API KEY"
echo "=================================================================================="
echo ""

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
