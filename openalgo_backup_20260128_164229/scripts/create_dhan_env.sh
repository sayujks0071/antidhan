#!/bin/bash
# Create complete .env file for Dhan (Port 5002)
# Copies all required variables from original .env but with Dhan broker config

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$OPENALGO_DIR"

echo "=================================================================================="
echo "  CREATING .env FILE FOR DHAN (PORT 5002)"
echo "=================================================================================="
echo ""

# Backup original .env
if [ -f ".env" ]; then
    BACKUP=".env.backup.$(date +%s)"
    cp .env "$BACKUP"
    echo "✅ Backed up original .env to $BACKUP"
fi

# Read original .env to get all variables
if [ -f ".env" ]; then
    echo "📝 Reading original .env for required variables..."
    
    # Create new .env with Dhan config, copying other vars from original
    {
        # Version
        grep "^ENV_CONFIG_VERSION" .env || echo "ENV_CONFIG_VERSION = '1.0.5'"
        
        # Dhan Broker Configuration (override)
        echo "BROKER_API_KEY = '1105009139:::df1da5de'"
        echo "BROKER_API_SECRET = 'fddc233a-a819-4e40-a282-1acbf9cd70b9'"
        
        # Port Configuration (override)
        echo "FLASK_PORT = '5002'"
        echo "FLASK_HOST_IP = '127.0.0.1'"
        echo "FLASK_DEBUG = 'False'"
        echo "FLASK_ENV = 'development'"
        
        # Redirect URL (override)
        echo "REDIRECT_URL = 'http://127.0.0.1:5002/dhan/callback'"
        echo "HOST_SERVER = 'http://127.0.0.1:5002'"
        
        # Database (override - separate DBs)
        echo "DATABASE_URL = 'sqlite:///db/openalgo_dhan.db'"
        echo "LATENCY_DATABASE_URL = 'sqlite:///db/latency_dhan.db'"
        echo "LOGS_DATABASE_URL = 'sqlite:///db/logs_dhan.db'"
        echo "SANDBOX_DATABASE_URL = 'sqlite:///db/sandbox_dhan.db'"
        
        # Valid Brokers (override - only Dhan)
        echo "VALID_BROKERS = 'dhan,dhan_sandbox'"
        
        # WebSocket (override)
        echo "APP_MODE = 'standalone'"
        echo "WEBSOCKET_HOST = '127.0.0.1'"
        echo "WEBSOCKET_PORT = '8766'"
        echo "WEBSOCKET_URL = 'ws://127.0.0.1:8766'"
        
        # Copy other required variables from original .env
        grep "^APP_KEY" .env
        grep "^API_KEY_PEPPER" .env
        grep "^NGROK_ALLOW" .env || echo "NGROK_ALLOW = 'FALSE'"
        grep "^LOGIN_RATE_LIMIT" .env
        grep "^API_RATE_LIMIT" .env
        grep "^ORDER_RATE_LIMIT" .env
        grep "^SMART_ORDER_RATE_LIMIT" .env
        grep "^WEBHOOK_RATE_LIMIT" .env
        grep "^STRATEGY_RATE_LIMIT" .env
        grep "^SMART_ORDER_DELAY" .env
        grep "^SESSION_EXPIRY_TIME" .env
        grep "^LOG_TO_FILE" .env || echo "LOG_TO_FILE = 'True'"
        grep "^LOG_LEVEL" .env || echo "LOG_LEVEL = 'INFO'"
        grep "^LOG_DIR" .env || echo "LOG_DIR = 'log'"
        grep "^LOG_FORMAT" .env
        grep "^LOG_RETENTION" .env
        
    } > .env.dhan.tmp
    
    mv .env.dhan.tmp .env
    echo "✅ Created .env with Dhan configuration"
    echo ""
    echo "📋 Key changes:"
    echo "   BROKER_API_KEY: Dhan (1105009139:::df1da5de)"
    echo "   FLASK_PORT: 5002"
    echo "   VALID_BROKERS: dhan,dhan_sandbox"
    echo "   APP_MODE: standalone"
else
    echo "❌ Original .env not found!"
    exit 1
fi

echo ""
echo "✅ .env file ready for Dhan (Port 5002)"
echo "📋 Original .env backed up to: $BACKUP"
