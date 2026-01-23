# Burn-In Checklist

## 🚀 Do Now (5-7 min)

```bash
# 1) Open the dashboard
make live-dashboard && tmux attach -t live

# 2) Force one end-to-end trade (PAPER)
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB

# 3) Quick prove-out (latency, OCO, flatten)
make quick-proveout
```

## 📊 What to Watch (During Session)

### Key Metrics Command
```bash
curl -s :8000/metrics | grep -E '^trader_(is_leader|orders_placed_total|orders_filled_total|oco_children_created_total|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|kill_switch_total)' | sort
```

### Critical Checks
- ✅ `trader_is_leader == 1` - Leader lock acquired
- ✅ Heartbeats < 5s:
  - `trader_marketdata_heartbeat_seconds < 5`
  - `trader_order_stream_heartbeat_seconds < 5`
- ✅ Orders increment after injector:
  - `trader_orders_placed_total` increments
  - `trader_oco_children_created_total` increments
- ✅ `/flatten` closes all ≤ 2s (positions → 0)

### Continuous Monitoring
```bash
# Watch metrics in real-time
watch -n 2 'curl -s :8000/metrics | grep -E "trader_(is_leader|orders_placed_total|oco_children_created_total|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds)" | sort'

# Or in tmux dashboard
make live-dashboard
tmux attach -t live
```

## 🌅 End-of-Day (60 seconds)

```bash
# 1. Generate burn-in report
make burnin-report

# 2. Reconcile database
psql "$DATABASE_URL" -f scripts/reconcile_db.sql

# 3. Post-close hygiene
make post-close
```

### What These Do
- **burnin-report**: Generates daily trading report (P&L, heat, MAE/MFE)
- **reconcile_db.sql**: Checks for:
  - Duplicate client order IDs
  - Orphan OCO groups
  - Positions without filled orders
  - Orders without positions
  - Summary counts
- **post-close**: DB snapshot, logs archive, git tagging

## 🌄 Tomorrow Morning Flow (Pre-Open)

```bash
# 1. Quick full loop check
make paper-e2e

# 2. Pre-LIVE gate (must PASS before any LIVE consideration)
make prelive-gate
```

### Pre-LIVE Gate Checks
- Leader lock acquired
- Heartbeats fresh (< 5s)
- Order latency p95 < 500ms
- Flatten speed ≤ 2s
- Zero positions
- Zero open orders

## 💾 Optional: Lock Environment Versions

Capture your *known-good* env so it's reproducible:

```bash
# Freeze current versions
pip freeze > requirements.lock

# Commit to git
git add requirements.lock
git commit -m "lock working runtime versions"
```

### Restore from Lock
```bash
pip install -r requirements.lock
```

## 🛑 Emergency Commands

If anything feels off mid-session:

```bash
# Immediate abort macro
make abort

# Or manually:
curl -X POST http://localhost:8000/pause
curl -X POST http://localhost:8000/flatten -H 'Content-Type: application/json' -d '{"reason":"emergency"}'
```

## 📋 Daily Routine

### Morning (Pre-Open)
1. `make verify` - Environment check
2. `docker compose up -d postgres redis` - Start services
3. `alembic upgrade head && make paper` - Start PAPER
4. `make live-dashboard` - Open dashboard
5. `make paper-e2e` - E2E test
6. `make prelive-gate` - Gate check (must PASS)

### During Session
- Monitor dashboard: `tmux attach -t live`
- Watch key metrics (see above)
- Test flatten periodically
- Check logs: `tail -f logs/*.log`

### End of Day
1. `make burnin-report` - Daily report
2. `psql "$DATABASE_URL" -f scripts/reconcile_db.sql` - DB reconciliation
3. `make post-close` - Post-close hygiene

## ✅ Success Indicators

### During Burn-In
- ✅ Leader lock stable
- ✅ Heartbeats consistent < 5s
- ✅ Orders execute correctly
- ✅ OCO children created
- ✅ Flatten works in < 2s
- ✅ No errors in logs

### After Burn-In (1-3 days)
- ✅ All metrics stable
- ✅ No data integrity issues
- ✅ Pre-live gate PASSES
- ✅ Ready for canary LIVE

## 🎯 Next Steps After Burn-In

1. **Review burn-in reports**: Check P&L, heat, MAE/MFE
2. **Verify data integrity**: Run `reconcile_db.sql`
3. **Run pre-live gate**: `make prelive-gate` (must PASS)
4. **Switch to LIVE**: When ready, use canary profile
5. **Monitor closely**: First hour is critical

## 💡 Pro Tips

- **Keep dashboard open**: `tmux attach -t live` in separate terminal
- **Watch logs**: `tail -f logs/*.log` in another terminal
- **Test flatten regularly**: Ensures kill-switch works
- **Check gate daily**: `make prelive-gate` before any LIVE operations
- **Lock versions**: `pip freeze > requirements.lock` after stable run

