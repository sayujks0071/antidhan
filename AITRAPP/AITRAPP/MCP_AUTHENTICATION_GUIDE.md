# MCP Server Authentication Guide

## Understanding the Error

The message **"missing MCP session_id or Kite request_token"** is **normal** when you visit the callback URL directly. 

The `/callback` endpoint is only meant to be accessed by Kite's OAuth redirect after you complete login. It expects specific parameters that Kite provides.

## ✅ Proper Authentication Flow

### Step 1: Register Redirect URL

**IMPORTANT**: Before authenticating, register the callback URL in your Kite Connect app:

1. Go to: https://developers.kite.trade/apps/
2. Find your app (API key: `nhe2vo0afks02ojs`)
3. Add redirect URL: `http://localhost:8080/callback`
4. **Save** the settings

### Step 2: Start MCP Server

```bash
cd /Users/mac/AITRAPP
make mcp-run-readonly
```

Server should be running at: http://localhost:8080/

### Step 3: Authenticate via MCP Client

The authentication happens through an MCP client (like Claude Desktop), not by visiting URLs directly.

#### Option A: Using Claude Desktop

1. **Configure Claude Desktop** (`~/.config/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "kite": {
      "command": "npx",
      "args": ["mcp-remote", "http://localhost:8080/mcp", "--allow-http"],
      "env": {
        "KITE_API_KEY": "nhe2vo0afks02ojs",
        "KITE_API_SECRET": "cs82nkkdvin37nrydnyou6cwn2b8zojl"
      }
    }
  }
}
```

2. **Restart Claude Desktop**

3. **In Claude, use the `login` tool**:
   - Claude will call the MCP server
   - You'll get an authorization URL
   - Open that URL in your browser
   - Login to Kite
   - Kite redirects to `http://localhost:8080/callback` with proper parameters
   - Authentication completes

#### Option B: Using MCP Client Directly

If you have an MCP client, you can call the `login` tool programmatically.

### Step 4: What Happens During Authentication

1. **MCP client calls `login` tool**
2. **Server generates authorization URL** with signed session ID
3. **You open URL in browser** and login to Kite
4. **Kite redirects** to: `http://localhost:8080/callback?request_token=XXX&session_id=YYY`
5. **Server verifies parameters** and completes authentication
6. **Session is established**

## 🔍 Testing the Server

### Check Server Status

```bash
make mcp-status
```

Or visit: http://localhost:8080/

You should see: **"Service Running"**

### Test Callback (Expected to Fail)

If you visit `http://localhost:8080/callback` directly, you'll see the error - **this is normal**. The callback needs OAuth parameters from Kite.

## 📋 Available MCP Tools

Once authenticated, you can use:

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

### Orders (if not in read-only mode)
- `place_order` - Place order
- `modify_order` - Modify order
- `cancel_order` - Cancel order
- `get_orders` - List orders
- `get_trades` - Trade history

## 🐛 Troubleshooting

### "Missing session_id or request_token"

**This is normal** when accessing callback directly. Authentication must go through the OAuth flow.

### "Invalid redirect URI"

- Make sure `http://localhost:8080/callback` is registered in Kite Connect app
- URL must match exactly (no trailing slash)
- Check app settings: https://developers.kite.trade/apps/

### "Session not found"

- Session may have expired (default: 12 hours)
- Start a new authentication flow
- Make sure server is running when you authenticate

### Authentication Not Working

1. **Check server is running**: `make mcp-status`
2. **Verify redirect URL** is registered in Kite Connect
3. **Check API keys** in `.env` file
4. **Try read-only mode first**: `make mcp-run-readonly`

## 💡 Quick Reference

```bash
# Start server
make mcp-run-readonly

# Check status
make mcp-status

# View in browser
open http://localhost:8080/

# Stop server
# Press Ctrl+C in the terminal where it's running
```

## 📚 Next Steps

1. ✅ Server is running
2. ✅ Register redirect URL in Kite Connect
3. ✅ Configure Claude Desktop (or other MCP client)
4. ✅ Use `login` tool to authenticate
5. ✅ Start using MCP tools for market data and portfolio

---

**Remember**: The callback error is normal when accessing it directly. Authentication must go through the proper OAuth flow via an MCP client.

