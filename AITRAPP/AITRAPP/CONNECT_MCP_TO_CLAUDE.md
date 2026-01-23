# Connect Kite MCP Server to Claude Code

Your MCP server is running! Now connect it to Claude Code.

## ✅ Current Status

- ✅ Go installed (v1.25.4)
- ✅ MCP server built
- ✅ API keys configured
- ✅ Server running at `http://localhost:8080`

## 🔌 Connect to Claude Code

### Step 1: Open a New Terminal

**Important**: Keep your MCP server running in the current terminal. Open a **new terminal window**.

### Step 2: Run the Connection Command

In the new terminal, run:

```bash
claude mcp add --transport http kite http://localhost:8080/mcp
```

Expected output:
```
✓ Added MCP server "kite"
```

### Step 3: Verify Connection

```bash
claude mcp list
```

Expected output:
```
kite (http://localhost:8080/mcp) - local
```

### Step 4: Get Server Details

```bash
claude mcp get kite
```

This shows available tools and configuration.

---

## 🧪 Test the Connection

Come back to your Claude Code session and ask:

```
"What tools are available from the Kite MCP server?"
```

Or test with real queries:

```
"Get the current price of RELIANCE"
"Search for instruments with 'INFY' in the name"
"Show me the LTP for SBIN"
```

---

## 🎯 Available MCP Tools

Once connected, these tools will be available:

### Market Data
- `get_quote` - Get detailed quote for instruments
- `get_ohlc` - Get OHLC data
- `get_ltp` - Get last traded price
- `get_historical_data` - Get historical data

### Portfolio
- `get_holdings` - Get your holdings
- `get_positions` - Get current positions
- `get_margins` - Get margin details

### Orders
- `get_orders` - Get order history
- `get_order_history` - Get order history for specific order
- `get_order_trades` - Get trades for an order
- `get_gtt_orders` - Get GTT orders
- `get_gtt_order` - Get specific GTT order

### Search
- `search_instruments` - Search for tradeable instruments

### Authentication
- `login` - Initiate Kite login (generates OAuth URL)
- `logout` - Clear session

---

## 🔐 Authentication Flow

Before using the tools, you need to authenticate:

1. Ask Claude: "Help me login to Kite"
2. Claude will call the `login` tool
3. You'll get a Kite login URL
4. Open it in browser and authorize
5. After redirect, you're authenticated!

**Note**: You need to add the redirect URL to your Kite app:
- Go to: https://developers.kite.trade/apps/
- Add redirect URL: `http://localhost:8080/callback`

---

## 🛠️ Troubleshooting

### "claude: command not found"

Make sure you're in a new terminal (not inside Claude Code). The `claude` command runs from your system shell.

### Connection timeout

Check if the server is running:
```bash
curl http://localhost:8080/
```

Should return: `{"status":"ok","message":"Service Running"}`

### Port already in use

If port 8080 is taken, edit `kite-mcp-server/.env`:
```env
APP_PORT=8081
```

Then reconnect:
```bash
claude mcp remove kite
claude mcp add --transport http kite http://localhost:8081/mcp
```

### Authentication issues

1. Verify redirect URL is registered: https://developers.kite.trade/apps/
2. Check API key and secret in `kite-mcp-server/.env`
3. Try the `logout` then `login` tools

---

## 🎉 Next Steps

1. **Connect**: Run the `claude mcp add` command in a new terminal
2. **Authenticate**: Ask Claude to help you login to Kite
3. **Test**: Query market data and portfolio info
4. **Explore**: Try different MCP tools

---

## 📊 Example Usage

Once connected and authenticated:

```
User: "Get me the current quote for RELIANCE"
Claude: [Uses get_quote tool via MCP]
        Here's the latest quote for RELIANCE:
        LTP: ₹2,456.75
        Change: +12.50 (+0.51%)
        Volume: 2.3M shares
        ...

User: "Show my current positions"
Claude: [Uses get_positions tool via MCP]
        You have 3 open positions:
        1. SBIN: +50 shares @ ₹623.45 (P&L: +₹245)
        2. INFY: -25 shares @ ₹1,456.20 (P&L: -₹120)
        ...
```

---

**Ready!** Your MCP server is running. Just connect it with the `claude mcp add` command and you're all set! 🚀
