#!/bin/bash
# Install Go on macOS (Apple Silicon - ARM64)

set -e

echo "🚀 Installing Go for Kite MCP Server..."
echo ""

# Download Go for ARM64 macOS
GO_VERSION="1.21.13"
GO_PACKAGE="go${GO_VERSION}.darwin-arm64.tar.gz"
GO_URL="https://go.dev/dl/${GO_PACKAGE}"

echo "📦 Downloading Go ${GO_VERSION} for Apple Silicon..."
cd /tmp
curl -LO "$GO_URL"

echo "📂 Installing to /usr/local/go..."
sudo rm -rf /usr/local/go
sudo tar -C /usr/local -xzf "$GO_PACKAGE"

echo "🔧 Setting up PATH..."
# Add to shell profile if not already there
SHELL_PROFILE=""
if [ -f "$HOME/.zshrc" ]; then
    SHELL_PROFILE="$HOME/.zshrc"
elif [ -f "$HOME/.bash_profile" ]; then
    SHELL_PROFILE="$HOME/.bash_profile"
fi

if [ -n "$SHELL_PROFILE" ]; then
    if ! grep -q "/usr/local/go/bin" "$SHELL_PROFILE"; then
        echo "" >> "$SHELL_PROFILE"
        echo "# Go installation" >> "$SHELL_PROFILE"
        echo 'export PATH=$PATH:/usr/local/go/bin' >> "$SHELL_PROFILE"
        echo 'export PATH=$PATH:$HOME/go/bin' >> "$SHELL_PROFILE"
        echo "✅ Added Go to PATH in $SHELL_PROFILE"
    fi
fi

# Set for current session
export PATH=$PATH:/usr/local/go/bin
export PATH=$PATH:$HOME/go/bin

echo ""
echo "✅ Go installation complete!"
echo ""
echo "🔄 To use Go in this terminal, run:"
echo "   export PATH=\$PATH:/usr/local/go/bin"
echo ""
echo "   Or open a new terminal (PATH will be set automatically)"
echo ""
echo "🧪 Verify installation:"
echo "   go version"
echo ""
echo "🎯 Next steps:"
echo "   cd kite-mcp-server"
echo "   make mcp-setup"
echo "   make mcp-build"
echo ""

# Cleanup
rm -f /tmp/"$GO_PACKAGE"

# Try to show version
if command -v go &> /dev/null; then
    echo "Current Go version:"
    go version
else
    echo "⚠️  Go will be available after you run: export PATH=\$PATH:/usr/local/go/bin"
fi
