#!/bin/bash
# Start OpenAlgo on Port 5002 - Clean Start
# This script ensures port 5002 starts correctly

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="$OPENALGO_DIR/log/dhan_port5002.log"

echo "=================================================================================="
echo "  STARTING OPENALGO ON PORT 5002 (DHAN - CLEAN START)"
echo "=================================================================================="
echo ""

# Kill any existing process on port 5002
if lsof -Pi :5002 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "⚠️  Stopping existing process on port 5002..."
    lsof -ti:5002 | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# Create log directory
mkdir -p "$OPENALGO_DIR/log"

# Unset any conflicting environment variables first
unset FLASK_PORT PORT

# Set environment variables directly
export FLASK_PORT=5002
export FLASK_HOST_IP=127.0.0.1
export FLASK_DEBUG=False
export APP_MODE=standalone

# Dhan Broker Credentials
export BROKER_API_KEY='1105009139:::df1da5de'
export BROKER_API_SECRET='fddc233a-a819-4e40-a282-1acbf9cd70b9'
export REDIRECT_URL='http://127.0.0.1:5002/dhan/callback'
export HOST_SERVER='http://127.0.0.1:5002'

# Database (separate for Dhan)
export DATABASE_URL='sqlite:///db/openalgo_dhan.db'
export LATENCY_DATABASE_URL='sqlite:///db/latency_dhan.db'
export LOGS_DATABASE_URL='sqlite:///db/logs_dhan.db'
export SANDBOX_DATABASE_URL='sqlite:///db/sandbox_dhan.db'

# Valid Brokers
export VALID_BROKERS='dhan,dhan_sandbox'

echo "✅ Environment configured:"
echo "   FLASK_PORT=$FLASK_PORT"
echo "   APP_MODE=$APP_MODE (WebSocket disabled)"
echo "   Broker: Dhan"
echo ""

# Change to OpenAlgo directory
cd "$OPENALGO_DIR"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "🚀 Starting OpenAlgo on port $FLASK_PORT..."
echo "   Web UI: http://127.0.0.1:$FLASK_PORT"
echo ""

# Start in background and capture output
nohup env FLASK_PORT=$FLASK_PORT APP_MODE=$APP_MODE python3 app.py > "$LOG_FILE" 2>&1 &
PID=$!

echo "✅ Started with PID: $PID"
echo "⏳ Waiting for startup (25 seconds)..."
sleep 25

# Check if process is running
if ! ps -p $PID > /dev/null 2>&1; then
    echo "❌ Process crashed! Check log:"
    tail -50 "$LOG_FILE"
    exit 1
fi

# Check if port is listening
if lsof -Pi :$FLASK_PORT -sTCP:LISTEN >/dev/null 2>&1; then
    echo "✅ Port $FLASK_PORT is listening!"
    echo ""
    echo "🌐 Web UI: http://127.0.0.1:$FLASK_PORT"
    echo "📋 Login Dhan: http://127.0.0.1:$FLASK_PORT → Broker Login → Dhan"
    
    # Test API
    if curl -s http://127.0.0.1:$FLASK_PORT/api/v1/ping > /dev/null 2>&1; then
        echo "✅ API is responding"
    else
        echo "⚠️  API not responding yet, may need more time"
    fi
else
    echo "⚠️  Port not listening. Check logs:"
    tail -50 "$LOG_FILE"
    echo ""
    echo "Process is running (PID: $PID) but port not listening."
    echo "This may be normal if it's still starting up."
fi

echo ""
echo "📋 Monitor: tail -f $LOG_FILE"
echo "📋 Stop: kill $PID"
echo "📋 Check port: lsof -i :$FLASK_PORT"
