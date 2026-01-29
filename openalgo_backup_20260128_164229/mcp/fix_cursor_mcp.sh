#!/bin/bash
# Fix Cursor MCP Configuration - Try multiple locations

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MCP_SERVER="$OPENALGO_DIR/mcp/mcpserver.py"
PYTHON_PATH="/opt/homebrew/bin/python3"
API_KEY="630db05e091812b4c23298ca2d018b62376ddd168860d21fcb4bd2dfc265e49f"
HOST_URL="http://127.0.0.1:5001"

echo "=================================================================================="
echo "  FIXING CURSOR MCP CONFIGURATION"
echo "=================================================================================="
echo ""

# Configuration to add
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

# Location 1: Cursor settings.json (already configured)
CURSOR_SETTINGS="$HOME/Library/Application Support/Cursor/User/settings.json"
echo "📍 Location 1: Cursor settings.json"
if [ -f "$CURSOR_SETTINGS" ]; then
    echo "   ✅ File exists: $CURSOR_SETTINGS"
    if grep -q "openalgo" "$CURSOR_SETTINGS"; then
        echo "   ✅ OpenAlgo MCP already configured"
    else
        echo "   ⚠️  OpenAlgo MCP not found, adding..."
    fi
else
    echo "   ❌ File not found"
fi
echo ""

# Location 2: ~/.cursor/mcp.json
CURSOR_MCP="$HOME/.cursor/mcp.json"
echo "📍 Location 2: ~/.cursor/mcp.json"
mkdir -p "$HOME/.cursor"
if [ -f "$CURSOR_MCP" ]; then
    echo "   ✅ File exists, updating..."
    BACKUP="${CURSOR_MCP}.backup.$(date +%s)"
    cp "$CURSOR_MCP" "$BACKUP"
    echo "   ✅ Backed up to: $BACKUP"
else
    echo "   📝 Creating new file..."
fi

# Write MCP config
echo "$MCP_CONFIG" > "$CURSOR_MCP"
echo "   ✅ Configuration written to: $CURSOR_MCP"
echo ""

# Location 3: ~/.cursor/config/mcp.json
CURSOR_CONFIG_MCP="$HOME/.cursor/config/mcp.json"
echo "📍 Location 3: ~/.cursor/config/mcp.json"
mkdir -p "$HOME/.cursor/config"
if [ -f "$CURSOR_CONFIG_MCP" ]; then
    echo "   ✅ File exists, updating..."
    BACKUP="${CURSOR_CONFIG_MCP}.backup.$(date +%s)"
    cp "$CURSOR_CONFIG_MCP" "$BACKUP"
    echo "   ✅ Backed up to: $BACKUP"
else
    echo "   📝 Creating new file..."
fi

# Write MCP config
echo "$MCP_CONFIG" > "$CURSOR_CONFIG_MCP"
echo "   ✅ Configuration written to: $CURSOR_CONFIG_MCP"
echo ""

# Verify settings.json still has it
echo "📍 Verifying settings.json..."
if grep -q "openalgo" "$CURSOR_SETTINGS" 2>/dev/null; then
    echo "   ✅ OpenAlgo MCP found in settings.json"
else
    echo "   ⚠️  Adding to settings.json..."
    python3 <<PYTHON_SCRIPT
import json
import os

settings_file = "$CURSOR_SETTINGS"
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

# Read existing settings
if os.path.exists(settings_file):
    with open(settings_file, 'r') as f:
        settings = json.load(f)
else:
    settings = {}

# Add MCP servers
if "mcpServers" not in settings:
    settings["mcpServers"] = {}
settings["mcpServers"].update(mcp_config)

# Write back
os.makedirs(os.path.dirname(settings_file), exist_ok=True)
with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)

print("✅ Updated settings.json")
PYTHON_SCRIPT
fi

echo ""
echo "=================================================================================="
echo "  CONFIGURATION COMPLETE"
echo "=================================================================================="
echo ""
echo "✅ MCP configuration added to:"
echo "   1. ~/Library/Application Support/Cursor/User/settings.json"
echo "   2. ~/.cursor/mcp.json"
echo "   3. ~/.cursor/config/mcp.json"
echo ""
echo "🔄 Next Steps:"
echo "   1. Open Cursor Settings (Cmd + ,)"
echo "   2. Search for 'MCP' in settings"
echo "   3. Look for 'MCP Servers' section"
echo "   4. Enable 'openalgo' server if there's a toggle"
echo "   5. Restart Cursor IDE completely (Cmd + Q, then reopen)"
echo ""
echo "💡 If you still don't see it:"
echo "   - Check Cursor version (MCP support may require latest version)"
echo "   - Try: Cursor → Settings → Features → MCP"
echo "   - Or check: Cursor → Preferences → Extensions → MCP"
echo ""
