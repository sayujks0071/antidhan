#!/bin/bash
# Setup script for Go and MCP Server dependencies

set -e

echo "🍺 Installing Homebrew (if needed)..."
echo ""

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "Homebrew not found. Installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Add Homebrew to PATH (for Apple Silicon Macs)
    if [ -f /opt/homebrew/bin/brew ]; then
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
else
    echo "✅ Homebrew is already installed"
fi

echo ""
echo "🔧 Installing Go..."
brew install go

echo ""
echo "✅ Verifying installation..."
go version

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Run: make mcp-setup"
echo "  2. Edit: kite-mcp-server/.env with your API keys"
echo "  3. Run: make mcp-run-readonly"
echo ""

