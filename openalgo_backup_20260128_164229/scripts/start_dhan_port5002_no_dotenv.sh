#!/bin/bash
# Start OpenAlgo on Port 5002 - Prevent .env from loading
# This temporarily moves .env to prevent it from overriding Dhan config

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="$OPENALGO_DIR/log/dhan_port5002.log"

echo "=================================================================================="
echo "  STARTING OPENALGO ON PORT 5002 (PREVENT .env LOADING)"
echo "=================================================================================="
echo ""

# Kill any existing process on port 5002
if lsof -Pi :5002 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "⚠️  Stopping existing process on port 5002..."
    lsof -ti:5002 | xargs kill -9 2>/dev/null || true
    sleep 2
fi

cd "$OPENALGO_DIR"

# Backup and temporarily move .env to prevent loading
ENV_BACKUP=""
if [ -f ".env" ]; then
    echo "📝 Temporarily moving .env to prevent Kite config override..."
    ENV_BACKUP=".env.backup.$(date +%s)"
    mv .env "$ENV_BACKUP"
    echo "✅ Moved .env to $ENV_BACKUP"
fi

# Create log directory
mkdir -p "$OPENALGO_DIR/log"

# Set environment variables directly (Dhan config)
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

# Valid Brokers (only Dhan)
export VALID_BROKERS='dhan,dhan_sandbox'

# Security (use same as main instance)
export APP_KEY='REDACTED_APP_KEY'
export API_KEY_PEPPER='REDACTED_API_KEY_PEPPER'

echo "✅ Environment configured:"
echo "   FLASK_PORT=$FLASK_PORT"
echo "   BROKER_API_KEY=$BROKER_API_KEY"
echo "   APP_MODE=$APP_MODE"
echo ""

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "🚀 Starting OpenAlgo on port $FLASK_PORT (without .env)..."
echo ""

# Start in background
nohup python3 app.py > "$LOG_FILE" 2>&1 &
PID=$!

echo "✅ Started with PID: $PID"
echo "⏳ Waiting for startup (30 seconds)..."
sleep 30

# Restore .env after startup
if [ -n "$ENV_BACKUP" ] && [ -f "$ENV_BACKUP" ]; then
    mv "$ENV_BACKUP" .env
    echo "✅ Restored .env file"
fi

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
    echo ""
    echo "🔍 Verifying broker configuration..."
    BROKER_KEY=$(ps e -p $PID 2>/dev/null | grep BROKER_API_KEY | head -1 | sed 's/.*BROKER_API_KEY=//' | cut -d' ' -f1)
    if [[ "$BROKER_KEY" == *"1105009139"* ]]; then
        echo "✅ Dhan broker configured correctly"
    else
        echo "⚠️  Broker config: $BROKER_KEY"
    fi
else
    echo "⚠️  Port not listening. Check logs:"
    tail -50 "$LOG_FILE"
fi

echo ""
echo "📋 Monitor: tail -f $LOG_FILE"
echo "📋 Stop: kill $PID"
