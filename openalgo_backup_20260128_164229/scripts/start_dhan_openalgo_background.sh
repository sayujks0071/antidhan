#!/bin/bash
# Start OpenAlgo on Port 5002 in Background
# Usage: ./start_dhan_openalgo_background.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$OPENALGO_DIR/.env.dhan"
LOG_FILE="$OPENALGO_DIR/log/dhan_openalgo.log"

echo "=================================================================================="
echo "  STARTING OPENALGO ON PORT 5002 (BACKGROUND)"
echo "=================================================================================="
echo ""

# Check if .env.dhan exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: .env.dhan file not found!"
    echo "   Run: ./scripts/setup_dhan_port5002.sh first"
    exit 1
fi

# Create log directory
mkdir -p "$OPENALGO_DIR/log"

# Load environment variables (handle quotes properly)
set -a
source <(cat "$ENV_FILE" | sed 's/^export //' | sed "s/'//g")
set +a

# Verify port is set
if [ -z "$FLASK_PORT" ]; then
    export FLASK_PORT='5002'
fi

# Check if port is already in use
if lsof -Pi :$FLASK_PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "⚠️  Port $FLASK_PORT is already in use!"
    echo "   Stopping existing process..."
    lsof -ti:$FLASK_PORT | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# Change to OpenAlgo directory
cd "$OPENALGO_DIR"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "✅ Starting OpenAlgo on port $FLASK_PORT..."
echo "   Log file: $LOG_FILE"
echo "   Web UI: http://127.0.0.1:$FLASK_PORT"
echo ""

# Start in background
nohup python3 app.py > "$LOG_FILE" 2>&1 &
PID=$!

echo "✅ OpenAlgo started with PID: $PID"
echo ""
echo "📋 To check status:"
echo "   tail -f $LOG_FILE"
echo ""
echo "📋 To stop:"
echo "   kill $PID"
echo ""
echo "📋 To check if running:"
echo "   curl http://127.0.0.1:$FLASK_PORT/api/v1/ping"
echo ""

# Wait a moment and check if it started
sleep 3
if ps -p $PID > /dev/null 2>&1; then
    echo "✅ Process is running"
else
    echo "❌ Process failed to start. Check log:"
    echo "   tail -20 $LOG_FILE"
    exit 1
fi
