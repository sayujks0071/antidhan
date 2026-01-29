# Complete MCX Strategy Setup Guide

## ✅ Current Status

- ✅ **OpenAlgo Server**: Running on port 5001
- ✅ **Login**: Successful (username: sayujks0071)
- ⚠️ **Kite Broker**: Needs manual connection
- ⚠️ **MCX Strategies**: Need to be started

## 📋 Step-by-Step Setup

### Step 1: Login to OpenAlgo (✅ Done)

Server is running and login is successful.

### Step 2: Connect Kite Broker

**Via Browser**:
1. Open: `http://127.0.0.1:5001/auth/broker`
2. Find **Zerodha/Kite** in the broker list
3. Click **"Connect Broker"** or **"Login with Kite"**
4. Complete OAuth login on Kite's page
5. You'll be redirected back to OpenAlgo
6. Verify broker status shows "Connected"

### Step 3: Start MCX Strategies

**Via Browser** (Recommended):
1. Navigate to: `http://127.0.0.1:5001/python`
2. Find MCX strategies in the list:
   - MCX Advanced Strategy
   - MCX Commodity Momentum
   - MCX Global Arbitrage
   - MCX Elite Strategy
   - MCX Neural Strategy
3. Click **"Start"** button for each strategy
4. Verify status changes to "Running"

**Via Script** (After Kite is connected):
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 scripts/start_mcx_strategies.py
```

### Step 4: Monitor Status via MCP

**Using Kite MCP**:
- "Using Kite MCP, show my MCX positions"
- "Get my MCX holdings using Kite MCP"

**Using OpenAlgo MCP**:
- "Using OpenAlgo MCP, show my position book"
- "Get my order book using OpenAlgo MCP"

**Using Dual MCP Assistant**:
- "Use the dual MCP assistant to monitor my MCX strategies"
- "Compare my MCX positions between Kite and OpenAlgo"

## 🎯 Quick Commands

### Start Server on Port 5001
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./scripts/start_port5001_kite.sh
```

### Login and Start MCX Strategies
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 scripts/login_kite_and_start_mcx.py
```

### Monitor via MCP (in Cursor)
Ask Cursor:
- "Use the mcx-strategy-monitor to check my MCX strategies"
- "Monitor my MCX positions using both MCP servers"

## 📊 MCX Strategies Available

1. **MCX Advanced Strategy**
2. **MCX Advanced Momentum Strategy**
3. **MCX Elite Strategy**
4. **MCX Neural Strategy**
5. **MCX Quantum Strategy**
6. **MCX AI Enhanced Strategy**
7. **MCX Clawdbot Strategy**
8. **MCX Global Arbitrage Strategy**

## ✅ Verification

After setup, verify:

1. **Kite Broker**: Connected at `http://127.0.0.1:5001/auth/broker`
2. **MCX Strategies**: Running at `http://127.0.0.1:5001/python`
3. **MCP Monitoring**: Working in Cursor chat

## 🔧 Troubleshooting

### Kite Broker Not Connecting
- Check OAuth redirect URL is registered in Kite Connect app
- Verify callback URL matches: `http://127.0.0.1:5001/zerodha/callback`
- Try clearing browser cache and retrying

### MCX Strategies Not Starting
- Ensure Kite broker is connected first
- Check API keys are configured
- Verify strategies are enabled in configuration

### MCP Not Working
- Restart Cursor IDE
- Verify both MCP servers in `~/.cursor/mcp.json`
- Check OpenAlgo server is running on port 5001

---

**Next Action**: Connect Kite broker via browser, then start MCX strategies!
