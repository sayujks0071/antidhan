# Quick Prove-Out Guide

## 🚀 Quick Start (Copy/Paste)

```bash
# 1) Start PAPER with full preflight
make start-paper

# 2) Open the tmux dashboard
make live-dashboard
tmux attach -t live

# 3) Force one end-to-end trade (optional, speeds validation)
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB

# 4) Sanity metrics & state
curl -s localhost:8000/metrics | grep -E '^trader_(is_leader|orders_placed_total|oco_children_created_total|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds)' | sort
curl -s localhost:8000/positions | jq

# 5) Kill-switch test (should close in ≤2s)
curl -s -X POST localhost:8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_smoke"}' | jq
sleep 2 && curl -s localhost:8000/positions | jq
```

## ✅ What to See

### Critical Checks
- `trader_is_leader == 1` - Leader lock acquired
- Both heartbeats `< 5` during market hours
  - `trader_marketdata_heartbeat_seconds < 5`
  - `trader_order_stream_heartbeat_seconds < 5`
- After injector: `orders_placed_total` and `oco_children_created_total` increment
- `/flatten` leaves **zero** positions in ≤2s

### Automated Prove-Out
```bash
make quick-proveout
```

This runs all checks automatically:
- API health
- Critical metrics
- Positions check
- Kill-switch test

## 🐛 Fast Triage

### Port Busy
```bash
# Use different port
PORT=8010 make paper

# Or find and kill blocking process
lsof -nP -iTCP:8000 | grep LISTEN
kill -TERM <PID>
```

### DB/Enum Issues
```bash
# Re-run migration
alembic upgrade head

# Then smoke check
make smoke-check
```

### WS Teardown Logs
- `SafeKiteTicker` will swallow benign teardown errors
- Reconnect once if needed
- Check logs: `tail -f logs/*.log`

### Idempotency Test
```bash
# Run injector twice with same params
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB

# Second should be skipped (idempotency check)
```

### API Not Responding
```bash
# Check if process is running
ps aux | grep uvicorn

# Check logs
tail -f logs/api_8000.log

# Check for errors
tail -f logs/*.log | grep -i error

# Restart if needed
pkill -f uvicorn
make start-paper
```

## 🌅 Daily Flow (PAPER Pre-Open)

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

## 📊 Monitoring Commands

### Check Metrics
```bash
# All critical metrics
curl -s localhost:8000/metrics | grep -E '^trader_(is_leader|orders_placed_total|oco_children_created_total|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds)' | sort

# Specific metric
curl -s localhost:8000/metrics | grep trader_is_leader

# All trader metrics
curl -s localhost:8000/metrics | grep trader_
```

### Check State
```bash
# Health
curl -s localhost:8000/health | jq

# System state
curl -s localhost:8000/state | jq

# Risk state
curl -s localhost:8000/risk | jq

# Positions
curl -s localhost:8000/positions | jq
```

### Test Kill-Switch
```bash
# Flatten all positions
curl -s -X POST localhost:8000/flatten \
  -H 'Content-Type: application/json' \
  -d '{"reason":"paper_smoke"}' | jq

# Wait and verify
sleep 2
curl -s localhost:8000/positions | jq
```

## ✅ Success Indicators

After running prove-out, you should see:

- ✅ API responding on `/health`
- ✅ `trader_is_leader == 1`
- ✅ Heartbeats < 5 seconds
- ✅ Orders placed/executed after injector
- ✅ `/flatten` completes in ≤ 2s
- ✅ Zero positions after flatten
- ✅ No errors in logs

## 🎯 Next Steps

1. **Monitor dashboard**: `tmux attach -t live`
2. **Watch logs**: `tail -f logs/*.log`
3. **Run daily E2E**: `make paper-e2e` (pre-open)
4. **When ready for LIVE**: `make prelive-gate` (must PASS)

## 💡 Pro Tips

- **Keep dashboard open**: `tmux attach -t live` in separate terminal
- **Watch logs**: `tail -f logs/*.log` in another terminal
- **Test flatten regularly**: Ensures kill-switch works
- **Check gate before LIVE**: `make prelive-gate` must PASS
- **Port override**: Always use `PORT=8010` if 8000 is busy

