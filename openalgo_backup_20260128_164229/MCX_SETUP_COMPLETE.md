# MCX Strategy Setup - Complete Guide

## ✅ What's Been Done

1. ✅ **OpenAlgo Server**: Running on port 5001
2. ✅ **Login Script**: Created and tested
3. ✅ **Subagents Created**:
   - `mcp-manager` - Manages both MCP servers
   - `dual-mcp-trading-assistant` - Uses both MCPs together
   - `mcx-strategy-monitor` - Monitors MCX strategies
4. ✅ **Skills Created**:
   - `dual-mcp-operations` - Coordinates both MCPs
   - `mcp-integration` - Manages MCP configurations
   - `mcx-monitoring` - MCX-specific monitoring

## 📋 Manual Setup Steps (Browser)

Since browser automation needs manual interaction for OAuth, follow these steps:

### Step 1: Login to OpenAlgo

1. **Open browser**: `http://127.0.0.1:5001/auth/login`
2. **Enter credentials**:
   - Username: `sayujks0071`
   - Password: `Apollo@20417`
3. **Click Login**

### Step 2: Connect Kite Broker

1. **Navigate to**: `http://127.0.0.1:5001/auth/broker`
2. **Find Zerodha/Kite** in the broker list
3. **Click**: "Connect Broker" or "Login with Kite"
4. **Complete OAuth** on Kite's page
5. **Verify**: Broker status shows "Connected" ✅

### Step 3: Start MCX Strategies

1. **Navigate to**: `http://127.0.0.1:5001/python`
2. **Find MCX strategies**:
   - MCX Advanced Strategy
   - MCX Commodity Momentum
   - MCX Global Arbitrage
   - MCX Elite Strategy
   - MCX Neural Strategy
   - MCX Quantum Strategy
   - MCX AI Enhanced Strategy
   - MCX Clawdbot Strategy
3. **Click "Start"** for each strategy you want to run
4. **Verify**: Status badge changes to "Running" ✅

## 🔍 Monitor Status via MCP

After completing the setup above, use the subagents and skills in Cursor:

### Using the MCX Strategy Monitor Subagent

Ask Cursor:
```
"Use the mcx-strategy-monitor to check my MCX strategies"
"Monitor my MCX positions using the mcx-strategy-monitor"
```

### Using the Dual MCP Trading Assistant

Ask Cursor:
```
"Use the dual-mcp-trading-assistant to show my MCX positions from both platforms"
"Compare my MCX holdings between Kite and OpenAlgo using the dual MCP assistant"
```

### Direct MCP Queries

**Kite MCP**:
```
"Using Kite MCP, show my MCX positions"
"Get my MCX holdings using Kite MCP"
"Show my MCX orders using Kite MCP"
```

**OpenAlgo MCP**:
```
"Using OpenAlgo MCP, get my position book and filter for MCX symbols"
"Show my MCX orders using OpenAlgo MCP"
"Get my trade book using OpenAlgo MCP for MCX trades"
```

## 📊 Expected MCX Monitoring Output

After setup, you should see:

### From Kite MCP:
- MCX positions (GOLD, SILVER, CRUDEOIL, etc.)
- MCX holdings
- MCX order status

### From OpenAlgo MCP:
- MCX strategy execution status
- MCX orders in order book
- MCX positions in position book
- MCX trades in trade book

### Unified Report:
- Combined MCX positions from both platforms
- Strategy execution status
- Open orders summary
- P&L for MCX positions

## 🎯 Quick Reference

**Server**: `http://127.0.0.1:5001`
**Login**: `sayujks0071` / `Apollo@20417`
**Broker Login**: `http://127.0.0.1:5001/auth/broker`
**Strategies**: `http://127.0.0.1:5001/python`

**MCP Config**: `~/.cursor/mcp.json`
- Kite MCP: Hosted
- OpenAlgo MCP: Local (port 5001)

## ✅ Verification Checklist

- [ ] OpenAlgo server running on port 5001
- [ ] Logged into OpenAlgo web UI
- [ ] Kite broker connected
- [ ] MCX strategies started
- [ ] MCP tools working in Cursor
- [ ] Can monitor via MCP queries

## 🚀 Next Steps

1. **Complete manual setup** (Steps 1-3 above)
2. **Restart Cursor IDE** to ensure MCPs are loaded
3. **Test MCP monitoring** with the queries above
4. **Use subagents** for automated monitoring

---

**Status**: Setup scripts and subagents ready. Complete manual browser steps, then use MCP for monitoring!
