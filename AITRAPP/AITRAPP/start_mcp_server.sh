#!/bin/bash
# Start MCP Server script

cd "$(dirname "$0")/kite-mcp-server"

# Add Homebrew to PATH (try both locations)
eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv 2>/dev/null || true)"

# Check if binary exists
if [ ! -f "./kite-mcp-server" ]; then
    echo "❌ MCP server binary not found. Run: make mcp-build"
    exit 1
fi

# Check if .env exists and load it
if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Run: make mcp-setup"
    exit 1
fi

# Load environment variables from .env file
export $(grep -v '^#' .env | xargs)

echo "🚀 Starting Kite MCP Server (READ-ONLY mode)..."
echo "📍 Server will be at: http://localhost:8080/"
echo "🛑 Press Ctrl+C to stop"
echo ""

# Start server in read-only mode
EXCLUDED_TOOLS=place_order,modify_order,cancel_order,place_gtt_order,modify_gtt_order,delete_gtt_order ./kite-mcp-server

