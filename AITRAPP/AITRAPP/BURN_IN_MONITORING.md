# Burn-In Monitoring Guide

## 🔍 5 Quick Checks (Do Now)

```bash
# Run all 5 checks at once
make quick-health

# Or individually:

# 1) Orchestrator heartbeat
watch -n 5 'curl -s :8000/state | jq "{running:.running, paused:.is_paused, last_scan:.last_scan_at, open_positions:(.positions_count // 0)}"'

# 2) Live metrics moving
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(signals_total|decisions_total|orders_placed_total|oco_children_created_total|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds)"'

# 3) Force a single end-to-end plan (PAPER)
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB

# 4) Flatten path (≤2s, ends at zero positions)
time curl -s -X POST :8000/flatten -H "Content-Type: application/json" -d '{"reason":"paper_smoke"}' | jq
sleep 2 && curl -s :8000/positions | jq 'length'

# 5) DB integrity (dups/orphans = 0)
psql "$DATABASE_URL" -f scripts/reconcile_db.sql
```

## 📊 Quick Sanity Targets

### Critical Metrics
- ✅ `trader_is_leader == 1` - Leader lock acquired
- ✅ Both heartbeats < 5s:
  - `trader_marketdata_heartbeat_seconds < 5`
  - `trader_order_stream_heartbeat_seconds < 5`
- ✅ One full OCO lifecycle (ENTRY → SL/TP) in PAPER
- ✅ `/flatten` ≤ 2s → positions = 0
- ✅ `reconcile_db.sql` shows 0 duplicates & 0 orphans

## 🐛 If Metrics Look "Quiet"

### Heartbeats > 5s
**Problem**: Streams not connected
**Fix**:
```bash
# Restart API
pkill -f uvicorn
make start-paper

# Or restart broker WS connection
# Check logs: tail -f logs/*.log
```

### `signals_total` Stays 0
**Problem**: Strategies not generating signals
**Fix**:
```bash
# Check if strategies are loaded
curl -s :8000/state | jq '.strategies'

# Check if paused
curl -s :8000/state | jq '.is_paused'

# Unpause if needed
curl -X POST :8000/resume
```

### Decisions/Entries Not Rising After Injector
**Problem**: Risk blocks or price-band guards
**Fix**:
```bash
# Check logs for RISK_BLOCK
tail -f logs/*.log | grep -i "risk_block\|price.*band\|freeze"

# Check risk state
curl -s :8000/risk | jq
```

## 💻 No tmux? No Problem

### Install tmux (macOS)
```bash
brew install tmux
```

### Or Use watch Commands
```bash
# Monitor metrics
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|orders_placed_total|oco_children_created_total|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|kill_switch_total)"'

# Monitor logs
tail -F logs/aitrapp.log | jq -r '.["ts","level","message"]|@tsv'
```

## 📊 Continuous Monitoring

### Watch Metrics
```bash
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|orders_placed_total|oco_children_created_total|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|kill_switch_total)" | sort'
```

### Watch State
```bash
watch -n 5 'curl -s :8000/state | jq "{mode:.mode, paused:.is_paused, positions:.positions_count, trades_today:.trades_today, daily_pnl:.daily_pnl}"'
```

### Watch Logs
```bash
# All logs
tail -f logs/*.log

# Filtered for errors
tail -f logs/*.log | grep -i error

# Filtered for signals
tail -f logs/*.log | grep -i signal

# JSON formatted
tail -F logs/aitrapp.log | jq -r '.["ts","level","message"]|@tsv'
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

## 🌄 Tomorrow Morning (Pre-Open)

```bash
# 1. Quick full loop check
make paper-e2e

# 2. Pre-LIVE gate (must PASS)
make prelive-gate
```

## 🎯 Success Indicators

### During Burn-In
- ✅ Leader lock stable (`trader_is_leader == 1`)
- ✅ Heartbeats consistent (< 5s)
- ✅ Signals generating (`trader_signals_total` increasing)
- ✅ Orders executing (`trader_orders_placed_total` increasing)
- ✅ OCO children created (`trader_oco_children_created_total` increasing)
- ✅ Flatten works in < 2s
- ✅ No errors in logs
- ✅ DB integrity clean (0 duplicates, 0 orphans)

### After Burn-In (1-3 days)
- ✅ All metrics stable
- ✅ No data integrity issues
- ✅ Pre-live gate PASSES
- ✅ Ready for canary LIVE

## 💡 Pro Tips

1. **Keep monitoring simple**: Use `watch` commands in separate terminals
2. **Check logs regularly**: `tail -f logs/*.log` for any issues
3. **Test flatten daily**: Ensures kill-switch works
4. **Run health check**: `make quick-health` before end of day
5. **Review reports**: Check `burnin-report` output daily

## 🛑 Emergency Commands

```bash
# Immediate abort
make abort

# Or manually
curl -X POST :8000/pause
curl -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"emergency"}'
```

## 📋 Daily Routine

### Morning
1. `make verify` - Environment check
2. `docker compose up -d postgres redis` - Start services
3. `alembic upgrade head && make paper` - Start PAPER
4. `make quick-health` - Health check
5. `make paper-e2e` - E2E test
6. `make prelive-gate` - Gate check

### During Session
- Monitor metrics: `watch -n 5 'curl -s :8000/metrics | grep trader_'`
- Watch logs: `tail -f logs/*.log`
- Test flatten periodically

### End of Day
1. `make quick-health` - Final health check
2. `make burnin-report` - Daily report
3. `psql "$DATABASE_URL" -f scripts/reconcile_db.sql` - DB reconciliation
4. `make post-close` - Post-close hygiene

