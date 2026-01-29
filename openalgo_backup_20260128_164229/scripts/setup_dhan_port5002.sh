#!/bin/bash
# Setup Dhan Broker Configuration for OpenAlgo on Port 5002
# Usage: ./setup_dhan_port5002.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$OPENALGO_DIR/.env.dhan"

echo "=================================================================================="
echo "  DHAN BROKER SETUP FOR PORT 5002"
echo "=================================================================================="
echo ""

# Dhan Credentials (from user input)
DHAN_CLIENT_ID="1105009139"
DHAN_API_KEY="df1da5de"
DHAN_API_SECRET="fddc233a-a819-4e40-a282-1acbf9cd70b9"
DHAN_APP_NAME="dhan_api"

echo "📋 Dhan Credentials:"
echo "   Client ID: $DHAN_CLIENT_ID"
echo "   API Key: $DHAN_API_KEY"
echo "   API Secret: $DHAN_API_SECRET"
echo "   App Name: $DHAN_APP_NAME"
echo ""

# Create .env.dhan file for port 5002
echo "📝 Creating .env.dhan file..."

cat > "$ENV_FILE" << EOF
# Dhan Broker Configuration for OpenAlgo Port 5002
# Generated: $(date)

# Dhan Broker Credentials
# Format: client_id:::api_key (or just client_id)
BROKER_API_KEY='${DHAN_CLIENT_ID}:::${DHAN_API_KEY}'
BROKER_API_SECRET='${DHAN_API_SECRET}'

# OpenAlgo Port Configuration
FLASK_PORT='5002'
FLASK_HOST_IP='127.0.0.1'
FLASK_DEBUG='False'
FLASK_ENV='development'

# Redirect URL for Dhan OAuth
REDIRECT_URL='http://127.0.0.1:5002/dhan/callback'

# Host Server
HOST_SERVER='http://127.0.0.1:5002'

# WebSocket Configuration
WEBSOCKET_HOST='127.0.0.1'
WEBSOCKET_PORT='8766'
WEBSOCKET_URL='ws://127.0.0.1:8766'

# Database Configuration (separate DB for Dhan instance)
DATABASE_URL='sqlite:///db/openalgo_dhan.db'
LATENCY_DATABASE_URL='sqlite:///db/latency_dhan.db'
LOGS_DATABASE_URL='sqlite:///db/logs_dhan.db'
SANDBOX_DATABASE_URL='sqlite:///db/sandbox_dhan.db'

# Security Configuration (copy from main .env or generate new)
# IMPORTANT: Generate new random values for production!
APP_KEY='REDACTED_APP_KEY'
API_KEY_PEPPER='REDACTED_API_KEY_PEPPER'

# Valid Brokers
VALID_BROKERS='dhan,dhan_sandbox'

# Logging
LOG_TO_FILE='True'
LOG_LEVEL='INFO'
LOG_DIR='log'
EOF

echo "✅ Created .env.dhan file at: $ENV_FILE"
echo ""
echo "=================================================================================="
echo "  NEXT STEPS"
echo "=================================================================================="
echo ""
echo "1. Start OpenAlgo on port 5002:"
echo "   cd $OPENALGO_DIR"
echo "   source .env.dhan && export \$(cat .env.dhan | xargs)"
echo "   python3 app.py"
echo ""
echo "   OR use the start script:"
echo "   ./scripts/start_dhan_openalgo.sh"
echo ""
echo "2. Login to Dhan via Web UI:"
echo "   Open: http://127.0.0.1:5002"
echo "   Go to: Broker Login → Dhan"
echo "   Complete OAuth flow"
echo ""
echo "3. Start Option Strategies:"
echo "   ./scripts/start_option_strategies.sh"
echo ""
echo "=================================================================================="
