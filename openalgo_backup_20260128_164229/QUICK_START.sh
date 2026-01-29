#!/bin/bash
# OpenAlgo Quick Start Script
# Run this before trading each day

echo "=========================================="
echo "   OpenAlgo Live Trading Quick Start"
echo "=========================================="
echo ""

# Check configuration
echo "1. Checking configuration..."
if [ ! -f .env ]; then
    echo "   ❌ .env file missing!"
    exit 1
fi
echo "   ✅ .env file exists"

if [ ! -f db/openalgo.db ]; then
    echo "   ❌ Database missing!"
    exit 1
fi
echo "   ✅ Database exists"

if [ ! -f strategies/strategy_env.json ]; then
    echo "   ⚠️  strategy_env.json missing (may be OK)"
fi

# Check if server is running
echo ""
echo "2. Checking server status..."
if lsof -i :5001 >/dev/null 2>&1; then
    echo "   ✅ Server is already running on port 5001"
    SERVER_RUNNING=true
else
    echo "   ❌ Server is not running"
    SERVER_RUNNING=false
fi

# Check virtual environment
echo ""
echo "3. Checking virtual environment..."
if [ -d "/Users/mac/dyad-apps/openalgo/venv" ]; then
    echo "   ✅ Virtual environment found"
    VENV_PATH="/Users/mac/dyad-apps/openalgo/venv"
else
    echo "   ⚠️  Virtual environment not found at expected location"
    VENV_PATH=""
fi

# Start server if not running
if [ "$SERVER_RUNNING" = false ]; then
    echo ""
    echo "4. Starting server..."
    if [ -n "$VENV_PATH" ]; then
        source "$VENV_PATH/bin/activate"
        echo "   ✅ Virtual environment activated"
    fi
    
    echo "   Starting OpenAlgo server..."
    echo "   (Press Ctrl+C to stop)"
    echo ""
    
    # Use start.sh but ensure we're in the right directory
    # The script will use .env from current directory
    cd /Users/mac/dyad-apps/probable-fiesta/openalgo
    bash start.sh
else
    echo ""
    echo "4. Server is already running"
    echo ""
    echo "Next steps:"
    echo "  - Check authentication: http://127.0.0.1:5001/auth/broker"
    echo "  - Check strategies: http://127.0.0.1:5001/python"
    echo "  - Open dashboard: http://127.0.0.1:5001/dashboard"
fi
