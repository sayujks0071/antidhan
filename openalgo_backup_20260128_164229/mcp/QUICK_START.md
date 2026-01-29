# OpenAlgo MCP - Quick Start Guide

## 🚀 Quick Setup (3 Steps)

### Step 1: Run Setup Script

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo/mcp
./setup_cursor_mcp.sh
```

The script will:
- ✅ Detect your Python installation
- ✅ Ask for your OpenAlgo API key
- ✅ Configure Cursor IDE automatically
- ✅ Create backup of existing settings

### Step 2: Get Your API Key

If you don't have your API key yet:

1. **Start OpenAlgo** (if not running):
   ```bash
   cd /Users/mac/dyad-apps/probable-fiesta/openalgo
   python3 app.py  # Port 5001
   # OR
   FLASK_PORT=5002 python3 app.py  # Port 5002
   ```

2. **Get API Key**:
   - Open: `http://127.0.0.1:5001` (or `5002`)
   - Login: `sayujks0071` / `Apollo@20417`
   - Go to: **Settings → API Keys**
   - Copy your API key

### Step 3: Restart Cursor

1. **Restart Cursor IDE** completely
2. **Test MCP** by asking:
   - "What OpenAlgo tools are available?"
   - "Get my account funds"

## ✅ Verification

Test that MCP is working:

```bash
# Test MCP server directly
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 mcp/mcpserver.py YOUR_API_KEY http://127.0.0.1:5001
```

If it starts without errors, MCP server is working!

## 📝 Manual Configuration

If you prefer manual setup, edit Cursor settings:

```bash
open ~/Library/Application\ Support/Cursor/User/settings.json
```

Add:

```json
{
  "mcpServers": {
    "openalgo": {
      "command": "/opt/homebrew/bin/python3",
      "args": [
        "/Users/mac/dyad-apps/probable-fiesta/openalgo/mcp/mcpserver.py",
        "YOUR_API_KEY_HERE",
        "http://127.0.0.1:5001"
      ]
    }
  }
}
```

## 🎯 Usage Examples

Once configured, try these commands in Cursor:

- **"Place a buy order for 100 shares of RELIANCE at market price"**
- **"Show me my current positions"**
- **"Get the latest quote for NIFTY"**
- **"Cancel all my pending orders"**
- **"What are my account funds?"**
- **"Place an iron condor on NIFTY with 25NOV25 expiry"**
- **"Get option chain for NIFTY with 30DEC25 expiry"**

## 🔧 Troubleshooting

### MCP not connecting?

1. **Check OpenAlgo is running**:
   ```bash
   curl http://127.0.0.1:5001/api/v1/ping
   ```

2. **Verify API key**:
   ```bash
   curl -X POST http://127.0.0.1:5001/api/v1/funds \
     -H "Content-Type: application/json" \
     -H "X-API-Key: YOUR_API_KEY" \
     -d '{}'
   ```

3. **Check Python path**:
   ```bash
   which python3
   ```

### Need Help?

- See [SETUP_MACOS.md](./SETUP_MACOS.md) for detailed setup
- See [README.md](./README.md) for full documentation

## 📚 Available Tools

The MCP server provides 40+ trading tools:

- **Order Management**: place_order, modify_order, cancel_order, etc.
- **Position Management**: get_open_position, close_all_positions
- **Market Data**: get_quote, get_option_chain, get_historical_data
- **Instrument Search**: search_instruments, get_symbol_info
- **Utilities**: get_funds, get_holidays, analyzer_status

See [README.md](./README.md) for complete list.

---

**Ready to trade with AI?** 🚀
