# Claude Desktop MCP Configuration

## Current Status

Your Claude Desktop config doesn't have MCP servers configured yet. Let's add the Kite MCP server.

## 📍 Config File Location

**macOS**: `~/Library/Application Support/Claude/config.json`

## 🔧 Setup Instructions

### Step 1: Backup Current Config

```bash
cp ~/Library/Application\ Support/Claude/config.json ~/Library/Application\ Support/Claude/config.json.backup
```

### Step 2: Add MCP Server Configuration

You have two options:

#### Option A: Local MCP Server (Recommended)

Edit the config file and add the MCP servers section:

```bash
# Open config file
open -e ~/Library/Application\ Support/Claude/config.json
```

Or use nano:
```bash
nano ~/Library/Application\ Support/Claude/config.json
```

Add this configuration:

```json
{
	"scale": 0,
	"locale": "en-US",
	"userThemeMode": "system",
	"dxt:allowlistEnabled": false,
	"dxt:allowlistLastUpdated": "2025-11-12T18:45:37.392Z",
	"hasTrackedInitialActivation": true,
	"mcpServers": {
		"kite": {
			"command": "npx",
			"args": [
				"mcp-remote",
				"http://localhost:8080/mcp",
				"--allow-http"
			],
			"env": {
				"KITE_API_KEY": "nhe2vo0afks02ojs",
				"KITE_API_SECRET": "cs82nkkdvin37nrydnyou6cwn2b8zojl"
			}
		}
	}
}
```

#### Option B: Hosted MCP Server (Easier, No Local Server)

```json
{
	"scale": 0,
	"locale": "en-US",
	"userThemeMode": "system",
	"dxt:allowlistEnabled": false,
	"dxt:allowlistLastUpdated": "2025-11-12T18:45:37.392Z",
	"hasTrackedInitialActivation": true,
	"mcpServers": {
		"kite": {
			"command": "npx",
			"args": [
				"mcp-remote",
				"https://mcp.kite.trade/mcp"
			]
		}
	}
}
```

### Step 3: Restart Claude Desktop

1. **Quit Claude Desktop** completely
2. **Reopen Claude Desktop**
3. MCP servers will be loaded

### Step 4: Verify MCP Servers

In Claude Desktop, you can check if MCP servers are connected:

1. Look for MCP indicators in the interface
2. Try using a Kite tool (like `get_quotes`)
3. Check Claude's response - it should mention available tools

## 📋 Available MCP Tools (After Setup)

Once configured, Claude will have access to:

### Market Data
- `get_quotes` - Real-time market quotes
- `get_ltp` - Last traded price
- `get_ohlc` - OHLC data
- `get_historical_data` - Historical prices
- `search_instruments` - Find trading instruments

### Portfolio
- `get_profile` - User profile
- `get_margins` - Account margins
- `get_holdings` - Portfolio holdings
- `get_positions` - Current positions
- `get_mf_holdings` - Mutual fund holdings

### Orders (if not read-only)
- `place_order` - Place orders
- `modify_order` - Modify orders
- `cancel_order` - Cancel orders
- `get_orders` - List orders
- `get_trades` - Trade history

### Authentication
- `login` - Login to Kite and get authorization URL

## 🧪 Testing

### Test 1: Check MCP Connection

Ask Claude:
```
"What MCP tools are available?"
```

Or:
```
"List all available MCP servers"
```

### Test 2: Use a Kite Tool

Ask Claude:
```
"Get the current quote for NIFTY"
```

Claude should use the `get_quotes` tool.

### Test 3: Authenticate

Ask Claude:
```
"Login to Kite Connect"
```

Claude will use the `login` tool and provide an authorization URL.

## 🔍 Troubleshooting

### MCP Server Not Showing

1. **Check config file syntax** - Must be valid JSON
2. **Restart Claude Desktop** - Required after config changes
3. **Check server is running** (if using local): `make mcp-status`
4. **Check npx is installed**: `which npx` or `npm install -g npx`

### "Connection Refused"

- Make sure MCP server is running: `make mcp-run-readonly`
- Check port 8080 is accessible
- Verify URL in config: `http://localhost:8080/mcp`

### "Command Not Found: npx"

Install Node.js:
```bash
brew install node
```

Or use the hosted version (doesn't need npx).

### Authentication Fails

- Make sure redirect URL is registered: `http://localhost:8080/callback`
- Check API keys in config match your Kite Connect app
- Verify server is running when authenticating

## 📝 Quick Setup Script

I can create a script to automatically update your config. Would you like me to do that?

## 🎯 Next Steps

1. ✅ Edit config file (add `mcpServers` section)
2. ✅ Restart Claude Desktop
3. ✅ Test with: "What MCP tools are available?"
4. ✅ Try: "Get NIFTY quote"
5. ✅ Authenticate: "Login to Kite"

---

**Note**: After editing the config, you **must restart Claude Desktop** for changes to take effect.

