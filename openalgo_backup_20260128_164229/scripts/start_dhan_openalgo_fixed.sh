#!/bin/bash
# Start OpenAlgo on Port 5002 with Proper Environment Loading
# Usage: ./start_dhan_openalgo_fixed.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$OPENALGO_DIR/.env.dhan"
LOG_FILE="$OPENALGO_DIR/log/dhan_openalgo.log"

echo "=================================================================================="
echo "  STARTING OPENALGO ON PORT 5002 (FIXED)"
echo "=================================================================================="
echo ""

# Check if .env.dhan exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: .env.dhan file not found!"
    exit 1
fi

# Create log directory
mkdir -p "$OPENALGO_DIR/log"

# Load environment variables properly
echo "📝 Loading environment from .env.dhan..."
while IFS='=' read -r key value; do
    # Skip comments and empty lines
    [[ "$key" =~ ^#.*$ ]] && continue
    [[ -z "$key" ]] && continue
    
    # Remove quotes from value
    value=$(echo "$value" | sed "s/^'//" | sed "s/'$//")
    
    # Export variable
    export "$key=$value"
done < <(grep -v '^#' "$ENV_FILE" | grep '=')

# Verify critical variables
if [ -z "$FLASK_PORT" ]; then
    export FLASK_PORT='5002'
fi

echo "✅ Configuration loaded"
echo "   Port: $FLASK_PORT"
echo "   WebSocket Port: ${WEBSOCKET_PORT:-8765}"
echo ""

# Check if port is already in use
if lsof -Pi :$FLASK_PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "⚠️  Port $FLASK_PORT is already in use!"
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

echo "🚀 Starting OpenAlgo..."
echo "   Web UI: http://127.0.0.1:$FLASK_PORT"
echo "   Log: $LOG_FILE"
echo ""

# Start in background
nohup python3 app.py > "$LOG_FILE" 2>&1 &
PID=$!

echo "✅ Started with PID: $PID"
echo ""
echo "⏳ Waiting for startup (10 seconds)..."
sleep 10

# Check if process is still running
if ! ps -p $PID > /dev/null 2>&1; then
    echo "❌ Process crashed! Check log:"
    tail -30 "$LOG_FILE"
    exit 1
fi

# Check if port is listening
if lsof -Pi :$FLASK_PORT -sTCP:LISTEN >/dev/null 2>&1; then
    echo "✅ Port $FLASK_PORT is listening!"
    echo ""
    echo "🌐 Access Web UI: http://127.0.0.1:$FLASK_PORT"
else
    echo "⚠️  Port $FLASK_PORT not listening yet. Check logs:"
    tail -20 "$LOG_FILE"
fi

echo ""
echo "📋 Monitor: tail -f $LOG_FILE"
echo "📋 Stop: kill $PID"
