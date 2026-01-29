# Getting Log Details Using OpenAlgo MCP

## ⚠️ Current Status

**OpenAlgo server is not running** on ports 5001 or 5002.

To get log details using OpenAlgo MCP, you need to start the OpenAlgo server first.

---

## 🚀 Step 1: Start OpenAlgo Server

### Option A: Start Port 5001 (Kite/Zerodha)

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 app.py
```

### Option B: Start Port 5002 (Dhan)

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
FLASK_PORT=5002 python3 app.py
```

Or use the startup script:

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./scripts/start_dhan_port5002_final.sh
```

---

## 📋 Step 2: Get Log Details

Once the server is running, you can get log details in several ways:

### Method 1: Using MCP Tools in Cursor Chat

After restarting Cursor (to load MCP), ask:

- **"Get my order book using OpenAlgo"**
- **"Show me my trade book using OpenAlgo"**
- **"Get my position book using OpenAlgo"**
- **"Show me my holdings using OpenAlgo"**

### Method 2: Using the Python Script

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 mcp/get_logs_via_mcp.py
```

Or with specific API key and host:

```bash
python3 mcp/get_logs_via_mcp.py YOUR_API_KEY http://127.0.0.1:5001
```

### Method 3: Direct API Calls

```bash
# Get order book
curl -X POST http://127.0.0.1:5001/api/v1/orderbook \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{}'

# Get trade book
curl -X POST http://127.0.0.1:5001/api/v1/tradebook \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{}'

# Get position book
curl -X POST http://127.0.0.1:5001/api/v1/positionbook \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{}'
```

---

## 📊 Available Log Types

The OpenAlgo MCP provides access to:

1. **Order Book** (`get_order_book`)
   - All pending and executed orders
   - Order status, prices, quantities
   - Order IDs and timestamps

2. **Trade Book** (`get_trade_book`)
   - All executed trades
   - Trade prices and quantities
   - Execution timestamps

3. **Position Book** (`get_position_book`)
   - Current open positions
   - Average prices, LTP
   - P&L information

4. **Holdings** (`get_holdings`)
   - Long-term investments
   - Equity holdings
   - P&L details

---

## 🔧 Troubleshooting

### Issue: "Failed to connect to the server"

**Solution**: Start the OpenAlgo server first (see Step 1 above)

### Issue: "API key invalid"

**Solution**: 
1. Get your API key from: `http://127.0.0.1:5001 → Settings → API Keys`
2. Update the API key in the script or MCP configuration

### Issue: MCP tools not working in Cursor

**Solution**:
1. Restart Cursor IDE completely
2. Verify MCP configuration: `cat ~/.cursor/mcp.json`
3. Check MCP logs in Cursor: View → Output → MCP

---

## ✅ Quick Start Commands

```bash
# 1. Start OpenAlgo server
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 app.py &
# (Server will run in background)

# 2. Wait a few seconds for server to start

# 3. Get logs
python3 mcp/get_logs_via_mcp.py
```

---

## 📝 Example Output

Once the server is running, you'll see:

```
======================================================================
  OPENALGO LOG DETAILS VIA MCP
======================================================================

✅ Connected to OpenAlgo at http://127.0.0.1:5001

📋 ORDER BOOK (All Orders)
----------------------------------------------------------------------
✅ Found 5 orders:
  [1] Order ID: 12345
      Symbol: RELIANCE | Exchange: NSE
      Action: BUY | Qty: 100
      Status: COMPLETE | Price: 2500.00
  ...

📊 TRADE BOOK (Executed Trades)
----------------------------------------------------------------------
✅ Found 10 trades:
  [1] Order ID: 12345
      Symbol: RELIANCE | Exchange: NSE
      Action: BUY | Qty: 100
      Price: 2500.00 | Time: 2026-01-28 14:30:00
  ...

💼 POSITION BOOK (Current Positions)
----------------------------------------------------------------------
✅ Found 3 positions:
  [1] Symbol: RELIANCE | Exchange: NSE
      Product: MIS | Quantity: 100
      Avg Price: 2500.00 | LTP: 2510.00
      P&L: 1000.00
  ...
```

---

**Next Step**: Start the OpenAlgo server, then try getting logs again!
