#!/bin/bash
# Strategy Launcher Script
# Easy way to run AITRAPP strategies on OpenAlgo

# Set API Key (use environment variable or export before running)
export OPENALGO_APIKEY="${OPENALGO_APIKEY:-YOUR_OPENALGO_APIKEY}"

# Change to openalgo directory
cd "$(dirname "$0")/openalgo"

# Activate virtual environment
source venv/bin/activate

echo "========================================"
echo "   AITRAPP Strategy Launcher"
echo "========================================"
echo ""
echo "Available Strategies:"
echo "  1) ORB Strategy (Opening Range Breakout)"
echo "  2) Trend Pullback Strategy"
echo "  3) Options Ranker Strategy (Template)"
echo "  4) Test Connection"
echo "  5) Open Web Interface"
echo "  0) Exit"
echo ""

read -p "Select strategy to run (0-5): " choice

case $choice in
    1)
        echo ""
        echo "Starting ORB Strategy..."
        echo "Press Ctrl+C to stop"
        echo "========================================"
        python strategies/scripts/orb_strategy.py
        ;;
    2)
        echo ""
        echo "Starting Trend Pullback Strategy..."
        echo "Press Ctrl+C to stop"
        echo "========================================"
        python strategies/scripts/trend_pullback_strategy.py
        ;;
    3)
        echo ""
        echo "Starting Options Ranker Strategy..."
        echo "Press Ctrl+C to stop"
        echo "========================================"
        python strategies/scripts/options_ranker_strategy.py
        ;;
    4)
        echo ""
        echo "Testing Connection..."
        echo "========================================"
        python strategies/scripts/test_connection.py
        ;;
    5)
        echo ""
        echo "Opening Web Interface..."
        echo "Go to: http://localhost:5000/python"
        open http://localhost:5000/python
        ;;
    0)
        echo "Goodbye!"
        exit 0
        ;;
    *)
        echo "Invalid choice. Please run again."
        exit 1
        ;;
esac
