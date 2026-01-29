#!/bin/bash
# Start OpenAlgo on Port 5002 with Dhan Broker Configuration
# Usage: ./start_dhan_openalgo.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$OPENALGO_DIR/.env.dhan"

echo "=================================================================================="
echo "  STARTING OPENALGO ON PORT 5002 (DHAN BROKER)"
echo "=================================================================================="
echo ""

# Check if .env.dhan exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: .env.dhan file not found!"
    echo "   Run: ./scripts/setup_dhan_port5002.sh first"
    exit 1
fi

# Load environment variables
echo "📝 Loading environment from .env.dhan..."
export $(cat "$ENV_FILE" | grep -v '^#' | xargs)

# Verify port is set
if [ -z "$FLASK_PORT" ]; then
    export FLASK_PORT='5002'
fi

echo "✅ Configuration loaded"
echo "   Port: $FLASK_PORT"
echo "   Broker: Dhan"
echo "   Client ID: $(echo $BROKER_API_KEY | cut -d':' -f1)"
echo ""

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
    echo "🐍 Activating virtual environment..."
    source .venv/bin/activate
elif [ -d "venv" ]; then
    echo "🐍 Activating virtual environment..."
    source venv/bin/activate
fi

# Start OpenAlgo
echo "🚀 Starting OpenAlgo on port $FLASK_PORT..."
echo ""
echo "   Web UI: http://127.0.0.1:$FLASK_PORT"
echo "   Press Ctrl+C to stop"
echo ""
echo "=================================================================================="

python3 app.py
