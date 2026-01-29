# ✅ OpenAlgo MCP Server - Setup Complete!

**Date**: January 28, 2026  
**Status**: ✅ Successfully Configured

---

## Configuration Summary

- **Python Path**: `/opt/homebrew/bin/python3`
- **MCP Server**: `/Users/mac/dyad-apps/probable-fiesta/openalgo/mcp/mcpserver.py`
- **API Key**: Found from `strategy_env.json` (first 20 chars: `630db05e091812b4c232...`)
- **Host**: `http://127.0.0.1:5001`
- **Settings File**: `~/Library/Application Support/Cursor/User/settings.json`
- **Backup Created**: `settings.json.backup.1769591208`

---

## ✅ What Was Done

1. ✅ Detected Python installation
2. ✅ Found MCP server file
3. ✅ Retrieved API key from `strategy_env.json`
4. ✅ Created backup of existing Cursor settings
5. ✅ Added MCP server configuration to Cursor settings

---

## 🔄 Next Steps

### Step 1: Restart Cursor IDE

**Important**: You must restart Cursor IDE completely for the MCP configuration to load.

1. **Quit Cursor IDE** completely (Cmd + Q)
2. **Reopen Cursor IDE**
3. Wait for it to fully load

### Step 2: Test MCP Connection

Once Cursor is restarted, test the MCP connection:

**Try these commands in Cursor chat:**

1. **"What OpenAlgo tools are available?"**
   - Should list all available trading tools

2. **"Get my account funds"**
   - Should retrieve your account balance and margin information

3. **"Show me my current positions"**
   - Should display your open positions

4. **"Get the latest quote for NIFTY"**
   - Should return current NIFTY price

---

## 🎯 Usage Examples

Once MCP is working, you can use natural language commands:

### Order Management
- **"Place a buy order for 100 shares of RELIANCE at market price"**
- **"Cancel all my pending orders"**
- **"Modify order ID 12345 to quantity 200"**

### Position Management
- **"Show me my current positions"**
- **"Close all positions for strategy Python"**
- **"Get open position for RELIANCE NSE MIS"**

### Market Data
- **"Get the latest quote for NIFTY"**
- **"Get quotes for RELIANCE, INFY, and TCS"**
- **"Get option chain for NIFTY with 30DEC25 expiry"**
- **"Get historical data for RELIANCE from 2025-01-01 to 2025-01-28"**

### Options Trading
- **"Place an iron condor on NIFTY with 25NOV25 expiry using OTM4 and OTM6 strikes"**
- **"Calculate option Greeks for NIFTY 26000 CE expiring on 25NOV25"**
- **"Get synthetic future price for NIFTY 25NOV25 expiry"**

### Account Information
- **"What are my account funds?"**
- **"Show me my order book"**
- **"Get my trade book"**
- **"What are the trading holidays in 2025?"**

---

## 🔧 Troubleshooting

### Issue: MCP tools not appearing

**Solution**:
1. Verify Cursor was restarted completely
2. Check Cursor settings:
   ```bash
   cat ~/Library/Application\ Support/Cursor/User/settings.json | grep -A 5 "openalgo"
   ```
3. Check OpenAlgo server is running:
   ```bash
   curl http://127.0.0.1:5001/api/v1/ping
   ```

### Issue: "API key invalid" errors

**Solution**:
1. Verify API key is correct:
   ```bash
   curl -X POST http://127.0.0.1:5001/api/v1/funds \
     -H "Content-Type: application/json" \
     -H "X-API-Key: YOUR_API_KEY" \
     -d '{}'
   ```
2. Generate new API key from Web UI if needed

### Issue: Connection refused

**Solution**:
1. Start OpenAlgo server:
   ```bash
   cd /Users/mac/dyad-apps/probable-fiesta/openalgo
   python3 app.py
   ```
2. Verify it's running on port 5001

---

## 📋 Configuration Details

The MCP server was configured with:

```json
{
  "mcpServers": {
    "openalgo": {
      "command": "/opt/homebrew/bin/python3",
      "args": [
        "/Users/mac/dyad-apps/probable-fiesta/openalgo/mcp/mcpserver.py",
        "630db05e091812b4c23298ca2d018b62376ddd168860d21fcb4bd2dfc265e49f",
        "http://127.0.0.1:5001"
      ]
    }
  }
}
```

---

## 🔄 Switching to Port 5002 (Dhan)

If you want to use port 5002 (Dhan instance) instead:

1. **Update settings manually** or
2. **Run setup again** with:
   ```bash
   OPENALGO_HOST=http://127.0.0.1:5002 ./setup_cursor_mcp_auto.sh
   ```

---

## 📚 Available Tools

The MCP server provides **40+ trading tools**:

- **Order Management**: place_order, modify_order, cancel_order, place_basket_order, place_split_order, place_options_order, place_options_multi_order
- **Position Management**: get_open_position, close_all_positions
- **Order Status**: get_order_status, get_order_book, get_trade_book, get_position_book, get_holdings
- **Market Data**: get_quote, get_multi_quotes, get_market_depth, get_historical_data, get_option_chain
- **Instrument Search**: search_instruments, get_symbol_info, get_expiry_dates, get_option_symbol
- **Utilities**: get_funds, get_holidays, get_timings, analyzer_status, calculate_margin

See [README.md](./README.md) for complete documentation.

---

## ✅ Setup Status

- ✅ MCP server configured
- ✅ API key configured
- ✅ Cursor settings updated
- ✅ Backup created
- ⏳ **Pending**: Restart Cursor IDE

---

**Next Action**: **Restart Cursor IDE** to activate MCP server!
