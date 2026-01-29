#!/bin/bash
# Start OpenAlgo on Port 5002 - Direct Method
# Usage: ./start_dhan_port5002_direct.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="$OPENALGO_DIR/log/dhan_port5002.log"

echo "=================================================================================="
echo "  STARTING OPENALGO ON PORT 5002 (DHAN)"
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

# Set environment variables directly (no .env file)
export FLASK_PORT='5002'
export FLASK_HOST_IP='127.0.0.1'
export FLASK_DEBUG='False'
export APP_MODE='standalone'  # Disable WebSocket

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
echo "   Port: $FLASK_PORT"
echo "   WebSocket: DISABLED"
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

echo "🚀 Starting OpenAlgo..."
echo "   Web UI: http://127.0.0.1:$FLASK_PORT"
echo ""

# Start in background
nohup python3 app.py > "$LOG_FILE" 2>&1 &
PID=$!

echo "✅ Started with PID: $PID"
echo "⏳ Waiting for startup (20 seconds)..."
sleep 20

# Check if process is running
if ! ps -p $PID > /dev/null 2>&1; then
    echo "❌ Process crashed! Check log:"
    tail -40 "$LOG_FILE"
    exit 1
fi

# Check if port is listening
if lsof -Pi :$FLASK_PORT -sTCP:LISTEN >/dev/null 2>&1; then
    echo "✅ Port $FLASK_PORT is listening!"
    echo ""
    echo "🌐 Web UI: http://127.0.0.1:$FLASK_PORT"
    echo "📋 Login Dhan: http://127.0.0.1:$FLASK_PORT → Broker Login → Dhan"
else
    echo "⚠️  Port not listening. Check logs:"
    tail -40 "$LOG_FILE"
fi

echo ""
echo "📋 Monitor: tail -f $LOG_FILE"
echo "📋 Stop: kill $PID"
