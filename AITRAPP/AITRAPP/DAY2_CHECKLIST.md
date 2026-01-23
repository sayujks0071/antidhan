# Day-2 PAPER Burn-In Checklist

**Date:** $(date +%Y-%m-%d)  
**Session:** PAPER Day-2  
**Mode:** Simulation Only

---

## Pre-Open (Before 09:15 IST)

```bash
# 1. Infrastructure check
make burnin-check

# 2. End-to-end test
make paper-e2e

# 3. Pre-live gate (should PASS)
make prelive-gate
```

**Expected Results:**
- ✅ Leader lock: 1
- ✅ All heartbeats < 5s
- ✅ Supervisor: running
- ✅ Readiness: 200
- ✅ Paper E2E: PASS
- ✅ Pre-live gate: PASS

---

## During Market Hours (09:15 - 15:20 IST)

### Monitor Gauges

```bash
# Watch key metrics
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds|orders_placed_total|oco_children_created_total|kill_switch_total|leader_changes_total)" | sort'
```

**Target:** All green throughout session

### OCO Lifecycle Drill (15:00-15:07)

```bash
# Inject synthetic plan
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB

# Verify OCO children created
curl -s :8000/metrics | grep trader_oco_children_created_total

# Test flatten
curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_day2"}' | jq

# Verify positions flat
sleep 2 && curl -s :8000/positions | jq 'length'  # expect 0
```

---

## End of Day (15:25+)

```bash
# 1. Generate burn-in report
make burnin-report

# 2. Database reconciliation
make reconcile-db

# 3. Post-close hygiene
make post-close

# 4. Score Day-2
make score-day2  # (if created) or use score-day1

# 5. Tag and push
git tag burnin-day2-$(date +%F)
git push --tags
```

---

## Troubleshooting

### If Supervisor Not Running

```bash
curl -s :8000/debug/supervisor/status | jq
curl -s -X POST :8000/debug/supervisor/start | jq
```

### If Leader Lock Lost

```bash
# Check Redis
redis-cli ping

# Check leader changes (should be low)
curl -s :8000/metrics | grep trader_leader_changes_total

# Restart API if needed
make start-paper
```

### If Heartbeats Stale

```bash
# Check market data connection
curl -s :8000/metrics | grep trader_marketdata_heartbeat_seconds

# Check order watcher
curl -s :8000/metrics | grep trader_order_stream_heartbeat_seconds

# Check scan supervisor
curl -s :8000/debug/supervisor/status | jq
```

---

## Success Criteria

**Day-2 PASS if:**
- ✅ Leader lock: 1 all session
- ✅ All heartbeats < 5s all session
- ✅ One clean OCO lifecycle proven
- ✅ `/flatten` ≤ 2s → positions=0
- ✅ Reconcile: 0 duplicates, 0 orphans
- ✅ No alerts fired (especially LeaderFlaps)
- ✅ Leader changes < 3 in 15m window

---

**Next:** Day-3 PAPER (if Day-2 PASS)

