# 🔥 Day-1 PAPER Burn-In Checklist

## T-15 min (Pre-Open) ✅

- [x] Fast green check: `make burnin-check`
- [x] Full loop pre-open test: `make paper-e2e`
- [x] Start PAPER session: `make start-paper` (or manual start)
- [x] Dashboard ready: `make live-dashboard && tmux attach -t live`

## At/After Open (First 5-10 min)

### Watch the Five Gauges
```bash
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds|orders_placed_total|oco_children_created_total|kill_switch_total)" | sort'
```

### Optional: Force One Clean OCO Lifecycle
```bash
# Inject synthetic plan
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB

# Safety drill - should close in ≤2s and leave zero positions
curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_day1"}' | jq

sleep 2 && curl -s :8000/positions | jq 'length'
```

## What "Green" Looks Like (Hold These All Session)

- [ ] `trader_is_leader == 1`
- [ ] `trader_marketdata_heartbeat_seconds < 5`
- [ ] `trader_order_stream_heartbeat_seconds < 5`
- [ ] `trader_scan_heartbeat_seconds < 5` and `trader_scan_ticks_total` rising
- [ ] After injector: `trader_orders_placed_total > 0` and `trader_oco_children_created_total > 0`
- [ ] `/flatten` completes ≤ 2s and positions → 0 on demand
- [ ] No Prometheus alerts (MD/Orders/Scan stale rules)

## Quick Tripwires (Flatten Immediately If Any Fire)

- [ ] Any heartbeat > 5s for >1 minute during market hours
- [ ] Order-ack p95 > 500 ms for >1 minute
- [ ] Throttle queue depth rising and not recovering
- [ ] Duplicate client IDs or orphan OCO children in reconcile

## Fast Triage Commands

```bash
# Supervisor not ticking
curl -s :8000/debug/supervisor/status | jq
curl -s -X POST :8000/debug/supervisor/start | jq

# Readiness (should be 200 once all heartbeats fresh)
curl -s :8000/ready | jq

# Abort macro (pause + flatten + PAPER) if any tripwire persists
make abort
```

## Pre-Close (Last 5-10 min)

- [ ] Confirm **positions = 0**, heat ≈ 0
- [ ] Heartbeats still < 5s
- [ ] No pending OCO children

## End-of-Day (60 seconds)

```bash
make burnin-report
make reconcile-db
make post-close
```

## Day-1 PASS Criteria (Log It)

- [ ] All five gauges green all session
- [ ] One clean OCO lifecycle proven
- [ ] `/flatten` ≤ 2s on demand
- [ ] Reconcile shows **0** duplicates and **0** orphans
- [ ] No alerts fired

---

**Status:** In Progress  
**Started:** $(date)  
**Session:** PAPER Day-1

