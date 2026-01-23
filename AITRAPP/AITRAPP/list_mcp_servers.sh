#!/bin/bash
# List MCP servers configured in Claude Desktop

CONFIG_FILE="$HOME/Library/Application Support/Claude/config.json"

echo "🔍 Claude Desktop MCP Servers"
echo "============================"
echo ""

if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Config file not found: $CONFIG_FILE"
    exit 1
fi

# Check if mcpServers exists
if ! grep -q '"mcpServers"' "$CONFIG_FILE"; then
    echo "📭 No MCP servers configured"
    echo ""
    echo "💡 To add Kite MCP server, run:"
    echo "   ./setup_claude_mcp.sh"
    exit 0
fi

# Display MCP servers
echo "📋 Configured MCP Servers:"
echo ""

python3 << 'PYTHON_SCRIPT'
import json
import os

config_file = os.path.expanduser("~/Library/Application Support/Claude/config.json")

try:
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    if 'mcpServers' not in config or not config['mcpServers']:
        print("   (none)")
    else:
        for name, server_config in config['mcpServers'].items():
            print(f"   ✅ {name}")
            if 'command' in server_config:
                print(f"      Command: {server_config['command']}")
            if 'args' in server_config:
                args_str = ' '.join(server_config['args'])
                print(f"      Args: {args_str}")
            if 'env' in server_config:
                env_keys = list(server_config['env'].keys())
                print(f"      Env vars: {', '.join(env_keys)}")
            print()
except Exception as e:
    print(f"❌ Error reading config: {e}")
PYTHON_SCRIPT

echo ""
echo "📝 Config file location:"
echo "   $CONFIG_FILE"
echo ""
echo "💡 To add Kite MCP server:"
echo "   ./setup_claude_mcp.sh"
echo ""
echo "💡 To edit manually:"
echo "   open -e \"$CONFIG_FILE\""

