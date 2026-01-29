# OpenAlgo MCP Server - macOS Setup Guide

This guide helps you configure the OpenAlgo MCP server for macOS systems, specifically for Cursor IDE.

## Prerequisites

✅ **Verified**: MCP is installed and available  
✅ **Python**: `/opt/homebrew/bin/python3` (Python 3.14.0)  
✅ **OpenAlgo Server**: Should be running on port 5001 or 5002

## Step 1: Get Your OpenAlgo API Key

1. **Start OpenAlgo Server** (if not running):
   ```bash
   cd /Users/mac/dyad-apps/probable-fiesta/openalgo
   # For port 5001 (Kite)
   python3 app.py
   
   # OR for port 5002 (Dhan)
   FLASK_PORT=5002 python3 app.py
   ```

2. **Get API Key**:
   - Open browser: `http://127.0.0.1:5001` (or `http://127.0.0.1:5002`)
   - Login: `sayujks0071` / `Apollo@20417`
   - Navigate to: **Settings → API Keys**
   - Generate or copy your API key

## Step 2: Configure Cursor IDE

### Option A: Using Cursor Settings UI

1. Open Cursor IDE
2. Go to **Settings** (Cmd + ,)
3. Search for "MCP" or "Model Context Protocol"
4. Add new MCP server configuration:

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

### Option B: Manual Configuration File

Edit the Cursor settings file directly:

```bash
# Open Cursor settings
open ~/Library/Application\ Support/Cursor/User/settings.json
```

Add the MCP server configuration:

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

**Important**: Replace `YOUR_API_KEY_HERE` with your actual API key from Step 1.

## Step 3: Configure for Port 5002 (Dhan)

If you want to use port 5002 (Dhan instance) instead:

```json
{
  "mcpServers": {
    "openalgo": {
      "command": "/opt/homebrew/bin/python3",
      "args": [
        "/Users/mac/dyad-apps/probable-fiesta/openalgo/mcp/mcpserver.py",
        "YOUR_API_KEY_HERE",
        "http://127.0.0.1:5002"
      ]
    }
  }
}
```

## Step 4: Test the Configuration

1. **Restart Cursor IDE** to load the new MCP configuration
2. **Test MCP connection**:
   - Open a new chat in Cursor
   - Try asking: "What OpenAlgo tools are available?"
   - Or: "Get my account funds"

## Step 5: Verify MCP Server Works

Test the MCP server directly:

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 mcp/mcpserver.py YOUR_API_KEY_HERE http://127.0.0.1:5001
```

If it starts without errors, the server is working correctly.

## Usage Examples

Once configured, you can use natural language commands in Cursor:

- **"Place a buy order for 100 shares of RELIANCE at market price"**
- **"Show me my current positions"**
- **"Get the latest quote for NIFTY"**
- **"Cancel all my pending orders"**
- **"What are my account funds?"**
- **"Place an iron condor on NIFTY with 25NOV25 expiry"**
- **"Get option chain for NIFTY with 30DEC25 expiry"**

## Troubleshooting

### Issue: MCP server not connecting

**Solution**:
1. Verify OpenAlgo server is running:
   ```bash
   curl http://127.0.0.1:5001/api/v1/ping
   ```

2. Check API key is valid:
   ```bash
   curl -X POST http://127.0.0.1:5001/api/v1/funds \
     -H "Content-Type: application/json" \
     -H "X-API-Key: YOUR_API_KEY_HERE" \
     -d '{}'
   ```

3. Verify Python path:
   ```bash
   which python3
   # Should show: /opt/homebrew/bin/python3
   ```

### Issue: Permission denied

**Solution**:
```bash
chmod +x /Users/mac/dyad-apps/probable-fiesta/openalgo/mcp/mcpserver.py
```

### Issue: Module not found

**Solution**:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
pip3 install mcp fastmcp
```

## Quick Reference

**MCP Server Path**: `/Users/mac/dyad-apps/probable-fiesta/openalgo/mcp/mcpserver.py`  
**Python Path**: `/opt/homebrew/bin/python3`  
**Port 5001**: Kite/Zerodha instance  
**Port 5002**: Dhan instance  
**Settings File**: `~/Library/Application Support/Cursor/User/settings.json`

## Security Note

⚠️ **Important**: 
- Keep your API key secure
- Don't commit API keys to version control
- Consider using environment variables for API keys in production

## Next Steps

1. ✅ Configure MCP server in Cursor
2. ✅ Test with simple commands
3. ✅ Start using AI-powered trading assistance!

For more information, see the main [README.md](./README.md) file.
