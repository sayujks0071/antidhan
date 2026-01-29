#!/bin/bash
# Setup script for OpenAlgo MCP Server in Cursor IDE (macOS)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CURSOR_SETTINGS="$HOME/Library/Application Support/Cursor/User/settings.json"

echo "=================================================================================="
echo "  OPENALGO MCP SERVER SETUP FOR CURSOR IDE (macOS)"
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

# Get API key
echo "📋 Please provide your OpenAlgo API key:"
echo "   (Get it from: http://127.0.0.1:5001 → Settings → API Keys)"
read -p "API Key: " API_KEY

if [ -z "$API_KEY" ]; then
    echo "❌ API key is required"
    exit 1
fi

# Get host URL
echo ""
echo "📋 Which OpenAlgo instance do you want to use?"
echo "   1) Port 5001 (Kite/Zerodha) - Default"
echo "   2) Port 5002 (Dhan)"
read -p "Choice [1-2]: " PORT_CHOICE

case $PORT_CHOICE in
    2)
        HOST_URL="http://127.0.0.1:5002"
        ;;
    *)
        HOST_URL="http://127.0.0.1:5001"
        ;;
esac

echo ""
echo "✅ Using host: $HOST_URL"
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

# Create MCP configuration
MCP_CONFIG=$(cat <<EOF
{
  "mcpServers": {
    "openalgo": {
      "command": "$PYTHON_PATH",
      "args": [
        "$MCP_SERVER",
        "$API_KEY",
        "$HOST_URL"
      ]
    }
  }
}
EOF
)

# Merge with existing settings using Python
UPDATED_SETTINGS=$(python3 <<PYTHON_SCRIPT
import json
import sys

try:
    existing = json.loads('''$SETTINGS_JSON''')
except:
    existing = {}

mcp_config = json.loads('''$MCP_CONFIG''')

# Merge MCP servers
if "mcpServers" not in existing:
    existing["mcpServers"] = {}

existing["mcpServers"].update(mcp_config["mcpServers"])

print(json.dumps(existing, indent=2))
PYTHON_SCRIPT
)

# Write updated settings
echo "$UPDATED_SETTINGS" > "$CURSOR_SETTINGS"

echo ""
echo "✅ MCP server configuration added to Cursor settings"
echo ""
echo "📋 Configuration Summary:"
echo "   Python: $PYTHON_PATH"
echo "   MCP Server: $MCP_SERVER"
echo "   API Key: ${API_KEY:0:20}..."
echo "   Host: $HOST_URL"
echo ""
echo "📁 Settings file: $CURSOR_SETTINGS"
echo ""
echo "🔄 Next Steps:"
echo "   1. Restart Cursor IDE to load the MCP configuration"
echo "   2. Test by asking: 'What OpenAlgo tools are available?'"
echo "   3. Try: 'Get my account funds'"
echo ""
echo "✅ Setup complete!"
