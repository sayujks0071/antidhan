# Final Burn-In Setup - One Command Away

## 🚀 Do This Now (Finalize Today's PAPER Run)

### 1. Restart API to Pick Up Flatten Fix

```bash
# Stop any running uvicorn bound to 8000
lsof -nP -iTCP:8000 | awk '/LISTEN/ {print $2}' | xargs -r kill -TERM

# Start API
PORT=8000 make paper
```

### 2. Confirm Orchestrator is Live

```bash
curl -s :8000/state | jq '{running, paused, last_scan:.last_scan_at, open_positions:(.positions|length)}'
```

**Target**: `running:true`, `paused:false`, `last_scan_at` updating every few seconds

### 3. Watch Heartbeats + Leader Lock

```bash
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds)"'
```

**Target**: Both heartbeats < 5s, `trader_is_leader == 1`

### 4. Seed Activity (PAPER)

```bash
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB

# Optional: repeat once more to confirm idempotency skip
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB
```

### 5. Flatten Smoke Test (≤2s, positions → 0)

```bash
time curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_smoke"}' | jq

sleep 2 && curl -s :8000/positions | jq 'length'
```

**Target**: Flatten completes in ≤ 2s, positions = 0

## 🐛 If Metrics Look "Quiet"

### Off-Hours
- Signals/decisions may stay at 0 — that's fine
- Heartbeats + injector prove the loop

### During Market Hours (Still Quiet)
Check:
1. `/state` shows strategies loaded
2. Risk not blocking (`/risk`)
3. Market-hours/holiday guards aren't preventing entries

```bash
# Check state
curl -s :8000/state | jq

# Check risk
curl -s :8000/risk | jq

# Check logs
tail -f logs/*.log | grep -i "risk_block\|market.*hours\|holiday"
```

## 🔍 DB Integrity (Run Once Today)

```bash
# Set if not set already
export DATABASE_URL='postgresql+psycopg2://trader:trader@localhost:5432/aitrapp'

psql "${DATABASE_URL#postgresql+psycopg2://}" -f scripts/reconcile_db.sql
```

**Target**: Should report 0 duplicates, 0 orphans

## 🌅 End-of-Day (60 seconds)

```bash
make burnin-report

psql "${DATABASE_URL#postgresql+psycopg2://}" -f scripts/reconcile_db.sql

make post-close
```

## 🌄 Tomorrow Pre-Open

```bash
make paper-e2e

make prelive-gate   # must PASS before any LIVE flip
```

## 💻 Dashboard (Optional)

### Install tmux (macOS)
```bash
brew install tmux
```

### Start Dashboard
```bash
make live-dashboard && tmux attach -t live
```

## 📊 Continuous Monitoring

### Watch Metrics
```bash
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds)"'
```

### Watch State
```bash
watch -n 5 'curl -s :8000/state | jq "{running, paused:.is_paused, last_scan:.last_scan_at, positions:.positions_count}"'
```

### Watch Logs
```bash
tail -F logs/aitrapp.log | jq -r '.["ts","level","message"]|@tsv'
```

## ✅ Success Indicators

### Orchestrator Live
- ✅ `running: true`
- ✅ `paused: false`
- ✅ `last_scan_at` updating every few seconds

### Heartbeats
- ✅ `trader_marketdata_heartbeat_seconds < 5`
- ✅ `trader_order_stream_heartbeat_seconds < 5`
- ✅ `trader_is_leader == 1`

### Trade Injection
- ✅ First injection: Creates plan
- ✅ Second injection: Idempotency skip (decision already exists)

### Flatten
- ✅ Completes in ≤ 2s
- ✅ Positions → 0 after flatten

### DB Integrity
- ✅ 0 duplicate client order IDs
- ✅ 0 orphan OCO groups
- ✅ 0 positions without filled orders
- ✅ 0 orders without positions

## 🎯 You're Set!

After completing these checks:
1. ✅ API restarted with fixes
2. ✅ Orchestrator confirmed live
3. ✅ Heartbeats + leader lock verified
4. ✅ Trade injection tested
5. ✅ Flatten smoke test passed
6. ✅ DB integrity confirmed

**You're officially in burn-in!** 🚀

Keep monitoring with the watch commands above, and run end-of-day checks before closing.

