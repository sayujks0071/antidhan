# 🔥 Burn-In Protocol

3-day burn-in before canary LIVE flip. Each day must be "PASS" to proceed.

## Daily Session (5-7 min)

### 1. Kick the loop + watch gauges

```bash
make live-dashboard && tmux attach -t live
# Or use watch commands
```

**Targets to hold:**
- `trader_is_leader == 1`
- `*_heartbeat_seconds < 5` (marketdata, order, scan)
- `trader_scan_ticks_total` steadily increments
- After one synthetic plan: `orders_placed_total` and `oco_children_created_total` > 0
- `/flatten` ≤ 2s → positions = 0

### 2. One end-to-end OCO

```bash
# Inject synthetic plan
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB

# Verify OCO children created
curl -s :8000/metrics | grep -E '^trader_(orders_placed_total|oco_children_created_total)'

# Test flatten
curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_burnin"}' | jq

# Verify positions flattened
curl -s :8000/positions | jq '.count // length'
```

### 3. End of day (60s)

```bash
# Generate daily report
make burnin-report

# Reconcile database (check for duplicates/orphans)
psql "${DATABASE_URL#postgresql+psycopg2://}" -f scripts/reconcile_db.sql

# Post-close hygiene
make post-close
```

## Green Criteria

Count a day as **"PASS"** if **ALL** are true:

- ✅ Leader lock remains `1` for the entire session
- ✅ All three heartbeats < 5s during trading
- ✅ No duplicate `client_order_id`; no orphan OCO children (reconcile script clean)
- ✅ `/flatten` ≤ 2s on demand
- ✅ No `retries_total{type="token_refresh"}` spikes; no `rate_limit` throttle buildup
- ✅ No alerts firing from `ops/alerts.yml`

**Do this for 3/3 days → cleared for canary LIVE.**

## Quick Check Script

```bash
# Quick burn-in check
curl -s :8000/metrics | grep -E '^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds|scan_ticks_total|orders_placed_total|oco_children_created_total)' | sort

# Check readiness
curl -s :8000/ready | jq

# Check supervisor
curl -s :8000/debug/supervisor/status | jq
```

