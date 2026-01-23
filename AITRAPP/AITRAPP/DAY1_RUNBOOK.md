# 🔥 Day-1 PAPER Burn-In Runbook

**Date:** $(date +%Y-%m-%d)  
**Goal:** Boring, green session → Day-1 PASS

## Pre-Open (T-15 min)

### 0) Infrastructure

```bash
docker compose up -d postgres redis
```

### 1) Start API + Quick Health

```bash
make start-paper

# Wait for readiness
curl -s :8000/ready | jq   # expect 200 once heartbeats <5s
```

### 2) Burn-In Checklist (Fast)

```bash
make burnin-check
make paper-e2e
```

## During Session

### 3) Prove One OCO Lifecycle

```bash
# Inject synthetic plan
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB

# Test flatten
curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_day1"}' | jq

# Verify positions flattened
sleep 2 && curl -s :8000/positions | jq 'length'  # expect 0
```

### 4) Watch the Five Gauges (All Session)

```bash
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds|orders_placed_total|oco_children_created_total|kill_switch_total)" | sort'
```

**Targets to hold:**
- `trader_is_leader == 1`
- `trader_marketdata_heartbeat_seconds < 5`
- `trader_order_stream_heartbeat_seconds < 5`
- `trader_scan_heartbeat_seconds < 5` and `trader_scan_ticks_total` rising
- After injector: `trader_orders_placed_total > 0`, `trader_oco_children_created_total > 0`
- `/flatten` ≤ 2s → positions = 0

## Chaos Drills (Optional Today, or After Close)

```bash
# Full chaos suite (non-interactive, auto-abort on failure)
make chaos-suite

# Or run individually:
NONINTERACTIVE=1 PAUSE_ON_FAIL=1 bash scripts/chaos_test_leader_lock.sh
bash scripts/chaos_test_rate_limit.sh  # default PLAN_COUNT=15
bash scripts/chaos_test_postgres.sh
```

## End-of-Day (60s)

```bash
make burnin-report
make reconcile-db
make post-close

# Tag the session
git tag burnin-day1-$(date +%F) && git push --tags
```

## Day-1 PASS Criteria

✅ All five gauges green all session  
✅ One clean OCO lifecycle proven  
✅ `/flatten` ≤ 2s on demand  
✅ Reconcile shows **0 duplicates, 0 orphans**  
✅ No alerts fired  

**If all pass → Day-1 PASS ✅**

## Quick Reference

- **Watch gauges:** `watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds|orders_placed_total|oco_children_created_total|kill_switch_total)" | sort'`
- **Emergency abort:** `make abort`
- **Check readiness:** `curl -s :8000/ready | jq`
- **Check supervisor:** `curl -s :8000/debug/supervisor/status | jq`

