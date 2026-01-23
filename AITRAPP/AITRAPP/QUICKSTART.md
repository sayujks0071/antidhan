# AITRAPP Quick Start Guide

Get AITRAPP running in **5 minutes**!

## Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Zerodha Kite Connect API credentials
- macOS/Linux (Windows with WSL2)

## Step 1: Clone & Setup (2 min)

```bash
cd /Users/mac/AITRAPP

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp env.example .env
```

## Step 2: Configure Credentials (1 min)

Edit `.env` file:

```bash
nano .env
```

**Required fields**:
```bash
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
KITE_ACCESS_TOKEN=your_access_token_here
KITE_USER_ID=your_user_id_here
```

**How to get Kite API credentials**:
1. Visit https://developers.kite.trade/
2. Create an app (or use existing)
3. Copy API Key and Secret
4. Generate access token (see Kite docs)

Save and exit (`Ctrl+X`, then `Y`, then `Enter`).

## Step 3: Start Infrastructure (1 min)

```bash
# Start Postgres and Redis
make dev

# Wait 30 seconds for services to initialize
```

Verify services are running:
```bash
docker-compose ps
```

You should see `postgres` and `redis` with status "Up".

## Step 4: Launch AITRAPP (1 min)

```bash
# Start in PAPER mode (safe simulation)
make paper
```

**Expected output**:
```
Starting AITRAPP
Mode: PAPER
Loading strategies...
Syncing instruments...
Building universe...
WebSocket connected
AITRAPP started successfully
```

## Step 5: Verify It's Working (<1 min)

Open a **new terminal** and run:

```bash
# Check system health
curl http://localhost:8000/health | jq

# View system state
curl http://localhost:8000/state | jq

# See positions (should be empty initially)
curl http://localhost:8000/positions | jq
```

**Success!** AITRAPP is now running in paper mode. 🎉

---

## What's Happening?

1. **Instrument sync**: Downloading all NSE/NFO instruments
2. **Universe building**: Selecting tradeable instruments (NIFTY, BANKNIFTY, etc.)
3. **WebSocket connection**: Streaming live market data
4. **Strategies loaded**: ORB, TrendPullback, OptionsRanker active
5. **Risk management**: All safety limits active

---

## Next Steps

### Monitor in Real-Time

```bash
# Watch logs
tail -f logs/aitrapp.log | jq

# Monitor system state (updates every 2s)
watch -n 2 'curl -s http://localhost:8000/state | jq'
```

### Test the Kill Switch

**IMPORTANT**: Test this before market hours!

```bash
# Activate kill switch
curl -X POST http://localhost:8000/flatten

# Should return:
# {
#   "status": "flattened",
#   "closed_positions": 0,
#   "errors": [],
#   "timestamp": "..."
# }
```

### Review Configuration

```bash
# View main config
cat configs/app.yaml

# Key settings:
# - mode: PAPER (safe)
# - risk limits
# - enabled strategies
```

### Paper Trade for a Session

1. Let AITRAPP run during market hours (9:15 AM - 3:30 PM IST)
2. Monitor logs and positions
3. Verify risk limits respected
4. Review trades at end of day

---

## Common Issues & Fixes

### Issue: "Connection refused" to database

**Fix**: Ensure Docker services are running
```bash
docker-compose ps
make dev
```

### Issue: "Kite authentication failed"

**Fix**: Check your access token
- Kite access tokens expire daily
- Generate a fresh token: https://kite.trade/
- Update `.env` with new token
- Restart AITRAPP

### Issue: "No ticks received"

**Fix**: Check WebSocket connection
- Verify `KITE_ACCESS_TOKEN` is current
- Check Kite API status: https://status.kite.trade
- Ensure firewall allows WebSocket connections

### Issue: "Port already in use"

**Fix**: Change port or kill existing process
```bash
# Find process on port 8000
lsof -i :8000

# Kill it
kill -9 <PID>

# Or change port in .env
echo "API_PORT=8001" >> .env
```

---

## Understanding Paper Mode

**Paper mode simulates trading without real orders:**

✅ **What it does**:
- Generates real signals from live market data
- Simulates order placement and fills
- Tracks P&L and positions
- Applies risk limits
- Logs all decisions

❌ **What it doesn't do**:
- Place actual orders with broker
- Use real capital
- Cause financial loss

**Use paper mode to**:
- Learn the system
- Test strategies
- Verify risk controls
- Build confidence

**Minimum paper trading**: 2 weeks before considering live mode.

---

## Going Live (⚠️ CAUTION)

**Only after**:
- ✅ 2+ weeks paper trading
- ✅ Risk limits tested and verified
- ✅ Kill switch tested multiple times
- ✅ Strategies performing as expected
- ✅ Full understanding of system behavior

**To switch to LIVE mode**:

```bash
# This will prompt for confirmation
make live

# You MUST type exactly:
CONFIRM LIVE TRADING
```

**Remember**: 
- Start with small capital (max 20% of total)
- Monitor constantly during first week
- Keep kill switch accessible
- When in doubt, PAUSE

---

## Key Commands Reference

```bash
# Start/Stop
make paper          # Start in paper mode
make live           # Start in live mode (requires confirmation)
make stop           # Stop all services
make clean          # Clean up completely

# Monitoring
curl http://localhost:8000/health      # Health check
curl http://localhost:8000/state       # System state
curl http://localhost:8000/positions   # Positions
curl http://localhost:8000/orders      # Orders

# Control
curl -X POST http://localhost:8000/pause    # Pause trading
curl -X POST http://localhost:8000/resume   # Resume trading
curl -X POST http://localhost:8000/flatten  # KILL SWITCH

# Maintenance
make backup-db      # Backup database
make test           # Run tests
```

---

## Getting Help

1. **Documentation**: 
   - `README.md` - Overview
   - `docs/RUNBOOK.md` - Operations guide
   - `docs/SECURITY.md` - Safety and compliance
   - `PROJECT_SUMMARY.md` - Complete feature list

2. **Logs**: Always check logs first
   ```bash
   tail -100 logs/aitrapp.log | jq
   ```

3. **Health Check**: Verify services
   ```bash
   curl http://localhost:8000/health | jq
   ```

---

## Next: Deep Dive

After AITRAPP is running, read:

1. **`docs/RUNBOOK.md`** - Daily operations
2. **`docs/SECURITY.md`** - Safety best practices
3. **`docs/COMPLIANCE.md`** - SEBI regulations
4. **`PROJECT_SUMMARY.md`** - Full system overview

---

## Emergency Contacts

- **Zerodha Support**: 080-40402020
- **Kite Status**: https://status.kite.trade
- **NSE**: https://www.nseindia.com

---

**🎉 Congratulations! You're ready to paper trade with AITRAPP.**

**Remember**: Paper trade for at least 2 weeks. Safety first. 🛡️

