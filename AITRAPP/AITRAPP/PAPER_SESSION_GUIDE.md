# PAPER Session Guide

## 🚀 Quick Start (5-7 min)

### Option 1: Automated (Recommended)
```bash
bash scripts/start_paper_session.sh
```

### Option 2: Manual Steps
```bash
# 1. Full post-migration checklist
make migration-checklist

# 2. Boot PAPER on port 8000 (or override if needed)
PORT=8000 make paper

# 3. Quick sanity after boot
make smoke-check
make quick-sanity

# 4. Bring up live tmux dashboard
make live-dashboard
tmux attach -t live

# 5. Optional: Force one end-to-end trade in PAPER
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB
```

## 📊 What to Watch (PAPER)

### Critical Metrics
- `trader_is_leader == 1` - Leader lock acquired
- `trader_marketdata_heartbeat_seconds < 5` - Market data fresh
- `trader_order_stream_heartbeat_seconds < 5` - Order stream fresh
- `trader_orders_placed_total` - Orders placed count
- `trader_oco_children_created_total` - OCO children created

### Health Checks
- `/flatten` completes ≤ 2s
- Positions go to 0 after flatten
- No stuck orders

### Check Metrics
```bash
curl -s http://localhost:8000/metrics | grep -E '^trader_' | head -20
```

## 🌅 Morning Routine (Pre-Open)

```bash
# 1. Verify environment
make verify

# 2. Start services
docker compose up -d postgres redis

# 3. Apply migrations and start PAPER
alembic upgrade head && make paper

# 4. Set up dashboard
make live-dashboard

# 5. Run E2E test (pre-open)
make paper-e2e

# 6. Pre-LIVE gate (must PASS before any LIVE flip)
make prelive-gate
```

## 🐛 Troubleshooting

### Port Busy
```bash
# Find process
lsof -nP -iTCP:8000 | grep LISTEN

# Kill gracefully
kill -TERM <PID>

# Or use different port
PORT=8010 make paper
```

### Enum Mismatch
```bash
# Re-run migration
alembic upgrade head

# Check with checklist
make migration-checklist
```

### Kite WS Stop Errors
- The `SafeKiteTicker` wrapper handles teardown quirks
- Reconnect once if needed
- Check logs: `tail -f logs/*.log`

### API Not Responding
```bash
# Check if running
ps aux | grep uvicorn

# Check logs
tail -f logs/api_*.log

# Restart
pkill -f uvicorn
PORT=8000 make paper
```

### Database Connection Issues
```bash
# Check DATABASE_URL
echo $DATABASE_URL

# Test connection
psql "$DATABASE_URL" -c "SELECT 1;"

# Start postgres
docker compose up -d postgres
```

### Redis Connection Issues
```bash
# Test connection
redis-cli ping

# Start redis
docker compose up -d redis
```

## 📋 Monitoring Commands

### View Metrics
```bash
# All trader metrics
curl -s http://localhost:8000/metrics | grep trader_

# Specific metric
curl -s http://localhost:8000/metrics | grep trader_is_leader

# Health check
curl -s http://localhost:8000/health | jq

# System state
curl -s http://localhost:8000/state | jq

# Risk state
curl -s http://localhost:8000/risk | jq
```

### View Logs
```bash
# All logs
tail -f logs/*.log

# API logs only
tail -f logs/api_*.log

# Filter for errors
tail -f logs/*.log | grep -i error
```

### Tmux Dashboard
```bash
# Create dashboard
make live-dashboard

# Attach to session
tmux attach -t live

# Detach (keep running)
Ctrl+B, then D

# List sessions
tmux ls

# Kill session
tmux kill-session -t live
```

## ✅ Success Indicators

After starting PAPER session, you should see:

- ✅ API responding on `/health`
- ✅ `trader_is_leader == 1` in metrics
- ✅ Heartbeats < 5 seconds
- ✅ No errors in logs
- ✅ Dashboard showing metrics
- ✅ `/flatten` works in < 2s

## 🎯 Next Steps After PAPER Burn-In

1. **Monitor for 1-3 days** in PAPER mode
2. **Run daily E2E tests** pre-open
3. **Check pre-live gate** before any LIVE switch
4. **When ready**: Run `make prelive-gate` (must PASS)
5. **Switch to LIVE**: `make live-switch` (with canary profile)

## 💡 Pro Tips

- **Keep dashboard open**: `tmux attach -t live` in a separate terminal
- **Watch logs**: `tail -f logs/*.log` in another terminal
- **Test flatten**: Regularly test `/flatten` to ensure it works
- **Check gate**: Run `make prelive-gate` before any LIVE operations
- **Port override**: Always use `PORT=8010` if 8000 is busy

## 🛑 Emergency Commands

```bash
# Immediate abort
make abort

# Pause trading
curl -X POST http://localhost:8000/pause

# Flatten all positions
curl -X POST http://localhost:8000/flatten -H "Content-Type: application/json" -d '{"reason":"emergency"}'

# Stop API
pkill -f uvicorn
```

