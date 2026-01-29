#!/bin/bash
# Start OpenAlgo on Port 5002 with Dhan Configuration
# Final version - uses .env file with Dhan config

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

cd "$OPENALGO_DIR"

# Ensure .env has Dhan config
if ! grep -q "1105009139" .env 2>/dev/null; then
    echo "📝 .env doesn't have Dhan config. Creating it..."
    ./scripts/create_dhan_env.sh
fi

# Verify Dhan config
BROKER_KEY=$(grep "^BROKER_API_KEY" .env | head -1)
if [[ "$BROKER_KEY" == *"1105009139"* ]]; then
    echo "✅ .env has Dhan configuration"
else
    echo "⚠️  Warning: .env may not have Dhan config"
    echo "   Current: $BROKER_KEY"
fi

# Create log directory
mkdir -p "$OPENALGO_DIR/log"

# Set environment (will override .env if needed)
export FLASK_PORT=5002
export APP_MODE=standalone

echo "✅ Starting on port $FLASK_PORT..."
echo ""

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start in background
nohup python3 app.py > "$LOG_FILE" 2>&1 &
PID=$!

echo "✅ Started with PID: $PID"
echo "⏳ Waiting for startup (30 seconds)..."
sleep 30

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
    
    # Verify broker config
    BROKER_KEY=$(ps e -p $PID 2>/dev/null | grep BROKER_API_KEY | head -1 | sed 's/.*BROKER_API_KEY=//' | cut -d' ' -f1)
    if [[ "$BROKER_KEY" == *"1105009139"* ]]; then
        echo "✅ Dhan broker configured correctly"
    else
        echo "⚠️  Broker: ${BROKER_KEY:0:30}..."
    fi
else
    echo "⚠️  Port not listening. Check logs:"
    tail -50 "$LOG_FILE"
fi

echo ""
echo "📋 Monitor: tail -f $LOG_FILE"
echo "📋 Stop: kill $PID"
