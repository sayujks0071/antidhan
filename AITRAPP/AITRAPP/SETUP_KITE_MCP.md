# Setup Kite MCP Server for Claude Code

This guide walks through connecting the Kite MCP server to Claude Code for AI-powered trading assistance.

## Prerequisites

The Kite MCP server requires Go. Install it first:

### macOS
```bash
# Using Homebrew (recommended)
# If you don't have Homebrew, install from https://brew.sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Go
brew install go

# Verify installation
go version  # Should show 1.21 or higher
```

### Alternative: Download directly
Download from https://go.dev/dl/ and follow installation instructions.

## Step 1: Configure Kite API Credentials

```bash
# Create .env file from template
cd kite-mcp-server
cp .env.example .env

# Edit with your credentials
nano .env
```

Add your Kite Connect API credentials:
```env
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here

# Configure for HTTP mode (Claude Code compatible)
APP_MODE=http
APP_PORT=8080
APP_HOST=localhost

# Optional: Start in read-only mode (safer)
EXCLUDED_TOOLS=place_order,modify_order,cancel_order,place_gtt_order,modify_gtt_order,delete_gtt_order

LOG_LEVEL=info
```

**Get API credentials**: https://developers.kite.trade/signup

## Step 2: Build the MCP Server

```bash
# From AITRAPP root directory
cd kite-mcp-server

# Download dependencies
go mod download

# Build the server
go build -o kite-mcp-server

# Verify build
./kite-mcp-server --help
```

## Step 3: Start the Server

```bash
# Run in HTTP mode (from kite-mcp-server directory)
./kite-mcp-server

# Server should start on http://localhost:8080
```

**Keep this terminal running** - the server needs to stay active.

## Step 4: Connect to Claude Code

Open a **new terminal** and run:

```bash
# Add the MCP server to Claude Code
claude mcp add --transport http kite http://localhost:8080/mcp

# Verify it's connected
claude mcp list

# Should show:
# kite (http://localhost:8080/mcp)
```

## Step 5: Test the Connection

In Claude Code, you should now have access to Kite tools:

- `get_quote` - Get market quotes
- `get_ohlc` - Get OHLC data
- `get_historical_data` - Historical price data
- `get_holdings` - View portfolio holdings
- `get_positions` - View current positions
- `get_orders` - View order history
- `search_instruments` - Find trading instruments

And more (if not in read-only mode):
- `place_order` - Place new orders
- `modify_order` - Modify existing orders
- `cancel_order` - Cancel orders

## Usage in Claude Code

Once connected, you can ask:

```
"Show me today's top gainers in NSE"
"What's the current price of RELIANCE?"
"Get my current positions"
"Show historical data for SBIN from last week"
```

Claude will automatically use the Kite MCP tools to fetch the data.

## Running Both Services

### Terminal 1: AITRAPP (Automated Trading)
```bash
cd /Users/mac/AITRAPP
make paper  # Or make live
```

### Terminal 2: Kite MCP Server (AI Assistant)
```bash
cd /Users/mac/AITRAPP/kite-mcp-server
./kite-mcp-server
```

### Terminal 3: Claude Code
```bash
# Your Claude Code session automatically connects to the MCP server
```

## Makefile Integration

For convenience, use these commands:

```bash
# Setup (first time only)
make mcp-setup          # Creates .env file

# Build
make mcp-build          # Requires Go installed

# Run
make mcp-run            # Full access mode
make mcp-run-readonly   # Safe read-only mode

# Manage
make mcp-status         # Check if running
```

## Security Considerations

### Read-Only Mode (Recommended for Testing)
Start with `EXCLUDED_TOOLS` to disable order placement:
```env
EXCLUDED_TOOLS=place_order,modify_order,cancel_order,place_gtt_order,modify_gtt_order,delete_gtt_order
```

### Full Trading Mode
Only enable after thorough testing:
```env
# Remove or comment out EXCLUDED_TOOLS
# EXCLUDED_TOOLS=
```

## Troubleshooting

### Go not installed
```bash
# Check Go installation
go version

# If not found, install via Homebrew or download from go.dev
```

### Port already in use
```bash
# Change port in .env
APP_PORT=8081

# Update Claude Code connection
claude mcp remove kite
claude mcp add --transport http kite http://localhost:8081/mcp
```

### Authentication errors
- Verify API key and secret in `.env`
- Check Kite Connect app status: https://kite.trade/apps
- Ensure API key is activated

### Server won't start
```bash
# Check logs
LOG_LEVEL=debug ./kite-mcp-server

# Verify .env file exists
ls -la .env

# Check if port is available
lsof -i :8080
```

## Architecture

```
┌─────────────────┐
│  Claude Code    │  AI Assistant
│   (You here)    │
└────────┬────────┘
         │ HTTP
         ↓
┌─────────────────┐
│  Kite MCP       │  Market Data & Trading Tools
│  Server (Go)    │  localhost:8080
└────────┬────────┘
         │ Kite Connect API
         ↓
┌─────────────────┐
│  Zerodha Kite   │  Trading Platform
│     (API)       │
└─────────────────┘

┌─────────────────┐
│  AITRAPP        │  Automated Trading (runs independently)
│  (Python)       │
└─────────────────┘
```

## Next Steps

1. ✅ Install Go
2. ✅ Configure `.env` with API credentials
3. ✅ Build the server
4. ✅ Start in read-only mode
5. ✅ Connect to Claude Code
6. ✅ Test with market data queries
7. ⚠️  Enable trading tools only after testing

---

**Ready to use!** You can now ask Claude Code about market data and get AI-powered trading insights.
