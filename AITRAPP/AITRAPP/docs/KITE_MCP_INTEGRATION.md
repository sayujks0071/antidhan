# Kite MCP Server Integration Guide

## Overview

The [Kite MCP Server](https://github.com/zerodha/kite-mcp-server) is a Model Context Protocol (MCP) server that provides AI assistants with secure access to Kite Connect API. This guide explains how to integrate it with AITRAPP.

## What is MCP?

Model Context Protocol (MCP) is a standardized protocol that allows AI assistants to:
- Access external data sources
- Execute actions through tools
- Provide context-aware assistance

## Kite MCP Server Features

The Kite MCP server provides AI assistants with:

- **Portfolio Management**: View holdings, positions, margins
- **Order Management**: Place, modify, cancel orders
- **Market Data**: Real-time quotes, historical data, OHLC
- **GTT Orders**: Good Till Triggered order management
- **Instrument Search**: Find trading instruments

## Integration Options

### Option 1: Standalone AI Assistant (Recommended)

Run the MCP server as a separate service to provide AI-powered trading assistance alongside AITRAPP.

**Use Case**: Get AI assistance for:
- Market analysis
- Strategy suggestions
- Portfolio review
- Trade execution via AI

**Setup**:

```bash
cd kite-mcp-server

# Create .env file
cat > .env << EOF
KITE_API_KEY=your_api_key
KITE_API_SECRET=your_api_secret
APP_MODE=http
APP_PORT=8080
APP_HOST=localhost
EOF

# Build and run
go build -o kite-mcp-server
./kite-mcp-server
```

**Access**: Server runs at `http://localhost:8080/`

### Option 2: Hosted Version (Easiest)

Use Zerodha's hosted version - no installation required:

```
https://mcp.kite.trade/mcp
```

**Setup for Claude Desktop**:

Edit `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kite": {
      "command": "npx",
      "args": ["mcp-remote", "https://mcp.kite.trade/mcp"]
    }
  }
}
```

### Option 3: Python Integration (Advanced)

Create a Python wrapper to communicate with the MCP server via HTTP:

```python
import httpx
from typing import Dict, Any

class KiteMCPClient:
    """Python client for Kite MCP Server"""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.client = httpx.AsyncClient()
    
    async def get_quotes(self, instruments: list) -> Dict[str, Any]:
        """Get market quotes"""
        # MCP protocol call
        pass
    
    async def get_positions(self) -> Dict[str, Any]:
        """Get current positions"""
        pass
    
    async def place_order(self, order_params: Dict) -> Dict[str, Any]:
        """Place order via MCP"""
        pass
```

## Architecture

```
┌─────────────────┐
│   AITRAPP       │
│   (Python)      │
│                 │
│  - Strategies   │
│  - Risk Mgmt    │
│  - Execution    │
└────────┬────────┘
         │
         │ (Optional Integration)
         │
┌────────▼────────┐
│  Kite MCP       │
│  Server (Go)    │
│                 │
│  - AI Tools     │
│  - Market Data  │
│  - Orders       │
└────────┬────────┘
         │
         │
┌────────▼────────┐
│  AI Assistant   │
│  (Claude/etc)   │
│                 │
│  - Analysis     │
│  - Suggestions  │
└─────────────────┘
```

## Use Cases

### 1. AI-Powered Market Analysis

Use AI assistant to:
- Analyze market conditions
- Suggest strategy parameters
- Review portfolio performance
- Get trade recommendations

**Example**:
```
User: "Analyze NIFTY options chain and suggest Iron Condor strikes"
AI: [Uses MCP tools to fetch data and provide analysis]
```

### 2. Natural Language Trading

Execute trades via natural language:
```
User: "Buy 1 lot of NIFTY 25000 CE at market"
AI: [Uses MCP place_order tool]
```

### 3. Portfolio Monitoring

Get AI insights on portfolio:
```
User: "What's my current portfolio risk?"
AI: [Fetches positions, calculates risk, provides analysis]
```

## Setup Instructions

### Step 1: Build MCP Server

```bash
cd /Users/mac/AITRAPP/kite-mcp-server

# Install Go if needed
# macOS: brew install go
# Linux: sudo apt install golang-go

# Build
go build -o kite-mcp-server

# Or use just (if installed)
just build
```

### Step 2: Configure

```bash
cd kite-mcp-server

# Create .env
cat > .env << EOF
KITE_API_KEY=${KITE_API_KEY}
KITE_API_SECRET=${KITE_API_SECRET}
APP_MODE=http
APP_PORT=8080
APP_HOST=localhost
EOF
```

**Note**: Uses same API keys as AITRAPP (from `.env` in project root)

### Step 3: Run MCP Server

```bash
# Run server
./kite-mcp-server

# Or
go run main.go
```

Server will be available at: `http://localhost:8080/`

### Step 4: Configure AI Client

#### For Claude Desktop

Edit `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kite": {
      "command": "npx",
      "args": ["mcp-remote", "http://localhost:8080/mcp", "--allow-http"],
      "env": {
        "KITE_API_KEY": "your_api_key",
        "KITE_API_SECRET": "your_api_secret"
      }
    }
  }
}
```

Restart Claude Desktop.

## Available MCP Tools

### Market Data
- `get_quotes` - Real-time quotes
- `get_ltp` - Last traded price
- `get_ohlc` - OHLC data
- `get_historical_data` - Historical prices
- `search_instruments` - Find instruments

### Portfolio
- `get_profile` - User profile
- `get_margins` - Account margins
- `get_holdings` - Holdings
- `get_positions` - Current positions
- `get_mf_holdings` - Mutual funds

### Trading
- `place_order` - Place order
- `modify_order` - Modify order
- `cancel_order` - Cancel order
- `get_orders` - List orders
- `get_trades` - Trade history

### GTT
- `get_gtts` - List GTT orders
- `place_gtt_order` - Create GTT
- `modify_gtt_order` - Modify GTT
- `delete_gtt_order` - Delete GTT

## Integration with AITRAPP

### Option A: Parallel Operation

Run both services independently:

```bash
# Terminal 1: AITRAPP
cd /Users/mac/AITRAPP
make paper

# Terminal 2: MCP Server
cd /Users/mac/AITRAPP/kite-mcp-server
./kite-mcp-server
```

**Benefits**:
- AI assistant can query market data
- AI can analyze AITRAPP's positions
- AI can suggest strategy improvements
- No code changes needed

### Option B: Python Integration

Create a bridge between AITRAPP and MCP server:

```python
# packages/core/mcp_client.py
import httpx
import json

class MCPBridge:
    """Bridge between AITRAPP and Kite MCP Server"""
    
    def __init__(self, mcp_url: str = "http://localhost:8080"):
        self.mcp_url = mcp_url
        self.client = httpx.AsyncClient()
    
    async def get_market_analysis(self, symbol: str):
        """Get AI-powered market analysis"""
        # Use MCP tools via HTTP
        pass
    
    async def ai_suggest_strategy(self, current_positions):
        """Get AI strategy suggestions"""
        pass
```

### Option C: Read-Only Mode

Run MCP server in read-only mode (exclude trading tools):

```bash
EXCLUDED_TOOLS=place_order,modify_order,cancel_order,place_gtt_order,modify_gtt_order,delete_gtt_order ./kite-mcp-server
```

**Use Case**: Safe AI assistance without trading risk

## Example Workflows

### Workflow 1: Strategy Optimization

1. AITRAPP runs backtest
2. AI analyzes results via MCP
3. AI suggests parameter tweaks
4. User updates config
5. Re-run backtest

### Workflow 2: Market Analysis

1. AI fetches current market data via MCP
2. AI analyzes conditions
3. AI suggests which strategies to enable
4. User updates AITRAPP config
5. AITRAPP trades based on suggestions

### Workflow 3: Risk Review

1. AI fetches positions via MCP
2. AI calculates portfolio risk
3. AI suggests position adjustments
4. User reviews and acts

## Security Considerations

### API Key Management

- **Shared Keys**: Both AITRAPP and MCP server use same Kite API keys
- **Rate Limits**: Be aware of combined API usage
- **Access Control**: MCP server should run on localhost only

### Read-Only Mode

For safety, run MCP server with trading tools excluded:

```bash
EXCLUDED_TOOLS=place_order,modify_order,cancel_order ./kite-mcp-server
```

### Network Security

- Run MCP server on localhost only
- Don't expose to public internet
- Use HTTPS in production (if needed)

## Troubleshooting

### Issue: MCP server won't start

**Check**:
- Go is installed: `go version`
- API keys are set in `.env`
- Port 8080 is available: `lsof -i :8080`

### Issue: Claude Desktop can't connect

**Check**:
- MCP server is running
- URL is correct in config
- `--allow-http` flag is used for localhost

### Issue: API rate limits

**Solution**:
- Monitor combined usage from AITRAPP + MCP
- Implement rate limiting
- Use caching where possible

## Best Practices

1. **Separate Concerns**: 
   - AITRAPP = Automated trading
   - MCP Server = AI assistance

2. **Read-Only First**: 
   - Start with read-only MCP mode
   - Add trading tools only when comfortable

3. **Monitor Usage**: 
   - Track API calls from both services
   - Stay within rate limits

4. **Test Thoroughly**: 
   - Test AI suggestions in paper mode
   - Validate before live trading

## Resources

- **Kite MCP Server**: https://github.com/zerodha/kite-mcp-server
- **MCP Protocol**: https://modelcontextprotocol.io
- **Kite Connect API**: https://kite.trade/docs/connect/
- **Hosted MCP**: https://mcp.kite.trade

## Summary

The Kite MCP server provides a powerful way to add AI assistance to your trading workflow. You can:

✅ Get AI-powered market analysis  
✅ Execute trades via natural language  
✅ Get strategy suggestions  
✅ Monitor portfolio with AI insights  

**Recommended Setup**: Run MCP server in read-only mode alongside AITRAPP for AI assistance without trading risk.

---

**Note**: The MCP server is a separate Go service. AITRAPP continues to work independently. The MCP server adds AI capabilities on top of your existing trading system.

