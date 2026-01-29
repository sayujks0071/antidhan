#!/bin/bash
# Automated setup script for OpenAlgo MCP Server in Cursor IDE (macOS)
# Uses API key from strategy_env.json or environment variable

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CURSOR_SETTINGS="$HOME/Library/Application Support/Cursor/User/settings.json"
STRATEGY_ENV="$OPENALGO_DIR/strategies/strategy_env.json"

echo "=================================================================================="
echo "  OPENALGO MCP SERVER SETUP FOR CURSOR IDE (macOS) - AUTO MODE"
echo "=================================================================================="
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Please install Python 3."
    exit 1
fi

PYTHON_PATH=$(which python3)
echo "✅ Python found: $PYTHON_PATH"
echo ""

# Check if MCP server file exists
MCP_SERVER="$OPENALGO_DIR/mcp/mcpserver.py"
if [ ! -f "$MCP_SERVER" ]; then
    echo "❌ MCP server file not found: $MCP_SERVER"
    exit 1
fi

echo "✅ MCP server found: $MCP_SERVER"
echo ""

# Try to get API key from various sources
API_KEY=""

# 1. Try environment variable
if [ -n "$OPENALGO_APIKEY" ]; then
    API_KEY="$OPENALGO_APIKEY"
    echo "✅ Found API key from environment variable"
fi

# 2. Try strategy_env.json
if [ -z "$API_KEY" ] && [ -f "$STRATEGY_ENV" ]; then
    EXTRACTED_KEY=$(python3 <<PYTHON_SCRIPT
import json
import sys
try:
    with open('$STRATEGY_ENV', 'r') as f:
        data = json.load(f)
    # Get first API key found
    for strategy_id, config in data.items():
        if isinstance(config, dict) and 'OPENALGO_APIKEY' in config:
            print(config['OPENALGO_APIKEY'])
            sys.exit(0)
except:
    pass
PYTHON_SCRIPT
)
    if [ -n "$EXTRACTED_KEY" ]; then
        API_KEY="$EXTRACTED_KEY"
        echo "✅ Found API key from strategy_env.json"
    fi
fi

# 3. Prompt if still not found
if [ -z "$API_KEY" ]; then
    echo "⚠️  No API key found in environment or config files"
    echo ""
    echo "📋 Please provide your OpenAlgo API key:"
    echo "   (Get it from: http://127.0.0.1:5001 → Settings → API Keys)"
    read -p "API Key: " API_KEY
    
    if [ -z "$API_KEY" ]; then
        echo "❌ API key is required"
        exit 1
    fi
fi

# Get host URL (default to port 5001, can override with OPENALGO_HOST env var)
HOST_URL="${OPENALGO_HOST:-http://127.0.0.1:5001}"

echo ""
echo "✅ Using configuration:"
echo "   API Key: ${API_KEY:0:20}..."
echo "   Host: $HOST_URL"
echo ""

# Create Cursor settings directory if it doesn't exist
CURSOR_DIR="$(dirname "$CURSOR_SETTINGS")"
mkdir -p "$CURSOR_DIR"

# Backup existing settings
if [ -f "$CURSOR_SETTINGS" ]; then
    BACKUP_FILE="${CURSOR_SETTINGS}.backup.$(date +%s)"
    cp "$CURSOR_SETTINGS" "$BACKUP_FILE"
    echo "✅ Backed up existing settings to: $BACKUP_FILE"
else
    echo "📝 Creating new settings file"
    echo "{}" > "$CURSOR_SETTINGS"
fi

# Read existing settings
SETTINGS_JSON=$(cat "$CURSOR_SETTINGS" 2>/dev/null || echo "{}")

# Merge with existing settings using Python
UPDATED_SETTINGS=$(python3 <<PYTHON_SCRIPT
import json
import sys

try:
    existing = json.loads('''$SETTINGS_JSON''')
except:
    existing = {}

# Create MCP server configuration
mcp_config = {
    "openalgo": {
        "command": "$PYTHON_PATH",
        "args": [
            "$MCP_SERVER",
            "$API_KEY",
            "$HOST_URL"
        ]
    }
}

# Merge MCP servers
if "mcpServers" not in existing:
    existing["mcpServers"] = {}

existing["mcpServers"].update(mcp_config)

print(json.dumps(existing, indent=2))
PYTHON_SCRIPT
)

# Write updated settings
echo "$UPDATED_SETTINGS" > "$CURSOR_SETTINGS"

echo ""
echo "✅ MCP server configuration added to Cursor settings"
echo ""
echo "📁 Settings file: $CURSOR_SETTINGS"
echo ""
echo "🔄 Next Steps:"
echo "   1. Restart Cursor IDE to load the MCP configuration"
echo "   2. Test by asking: 'What OpenAlgo tools are available?'"
echo "   3. Try: 'Get my account funds'"
echo ""
echo "✅ Setup complete!"
