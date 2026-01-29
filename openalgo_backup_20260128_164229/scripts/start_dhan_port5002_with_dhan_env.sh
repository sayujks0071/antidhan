#!/bin/bash
# Start OpenAlgo on Port 5002 - Create temporary .env with Dhan config
# This creates a minimal .env file with Dhan config to prevent Kite override

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="$OPENALGO_DIR/log/dhan_port5002.log"

echo "=================================================================================="
echo "  STARTING OPENALGO ON PORT 5002 (WITH DHAN .env)"
echo "=================================================================================="
echo ""

# Kill any existing process on port 5002
if lsof -Pi :5002 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "⚠️  Stopping existing process on port 5002..."
    lsof -ti:5002 | xargs kill -9 2>/dev/null || true
    sleep 2
fi

cd "$OPENALGO_DIR"

# Backup original .env
ENV_BACKUP=""
if [ -f ".env" ]; then
    echo "📝 Backing up original .env..."
    ENV_BACKUP=".env.backup.$(date +%s)"
    cp .env "$ENV_BACKUP"
    echo "✅ Backed up to $ENV_BACKUP"
fi

# Create minimal .env file with Dhan config
echo "📝 Creating .env file with Dhan configuration..."
cat > .env << 'ENVEOF'
# Temporary .env for Port 5002 (Dhan)
ENV_CONFIG_VERSION = '1.0.5'

# Dhan Broker Configuration
BROKER_API_KEY = '1105009139:::df1da5de'
BROKER_API_SECRET = 'fddc233a-a819-4e40-a282-1acbf9cd70b9'

# Port Configuration
FLASK_PORT = '5002'
FLASK_HOST_IP = '127.0.0.1'
FLASK_DEBUG = 'False'
FLASK_ENV = 'development'

# Redirect URL
REDIRECT_URL = 'http://127.0.0.1:5002/dhan/callback'

# Host Server
HOST_SERVER = 'http://127.0.0.1:5002'

# Database (separate for Dhan)
DATABASE_URL = 'sqlite:///db/openalgo_dhan.db'
LATENCY_DATABASE_URL = 'sqlite:///db/latency_dhan.db'
LOGS_DATABASE_URL = 'sqlite:///db/logs_dhan.db'
SANDBOX_DATABASE_URL = 'sqlite:///db/sandbox_dhan.db'

# Security
APP_KEY = 'REDACTED_APP_KEY'
API_KEY_PEPPER = 'REDACTED_API_KEY_PEPPER'

# Valid Brokers (only Dhan)
VALID_BROKERS = 'dhan,dhan_sandbox'

# WebSocket (disabled)
APP_MODE = 'standalone'
WEBSOCKET_HOST = '127.0.0.1'
WEBSOCKET_PORT = '8766'

# Logging
LOG_TO_FILE = 'True'
LOG_LEVEL = 'INFO'
LOG_DIR = 'log'
ENVEOF

echo "✅ Created .env with Dhan configuration"

# Create log directory
mkdir -p "$OPENALGO_DIR/log"

# Set environment variables (will override .env)
export FLASK_PORT=5002
export APP_MODE=standalone

echo "✅ Environment configured:"
echo "   FLASK_PORT=$FLASK_PORT"
echo "   APP_MODE=$APP_MODE"
echo ""

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "🚀 Starting OpenAlgo on port $FLASK_PORT..."
echo ""

# Start in background
nohup python3 app.py > "$LOG_FILE" 2>&1 &
PID=$!

echo "✅ Started with PID: $PID"
echo "⏳ Waiting for startup (30 seconds)..."
sleep 30

# Restore original .env after startup
if [ -n "$ENV_BACKUP" ] && [ -f "$ENV_BACKUP" ]; then
    echo "📝 Restoring original .env..."
    mv "$ENV_BACKUP" .env
    echo "✅ Restored original .env"
    echo "⚠️  Note: Port 5002 will continue using Dhan config from its own .env"
fi

# Check if process is running
if ! ps -p $PID > /dev/null 2>&1; then
    echo "❌ Process crashed! Check log:"
    tail -50 "$LOG_FILE"
    # Restore .env before exiting
    if [ -n "$ENV_BACKUP" ] && [ -f "$ENV_BACKUP" ]; then
        mv "$ENV_BACKUP" .env
    fi
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
        echo "⚠️  Broker config check: ${BROKER_KEY:0:30}..."
    fi
else
    echo "⚠️  Port not listening. Check logs:"
    tail -50 "$LOG_FILE"
fi

echo ""
echo "📋 Monitor: tail -f $LOG_FILE"
echo "📋 Stop: kill $PID"
echo ""
echo "⚠️  IMPORTANT: Port 5002 now has its own .env with Dhan config"
echo "   Port 5001 will use the original .env (Kite)"
