# Day-2 PAPER Burn-In Runbook
**Date:** $(date +%Y-%m-%d)  
**Session:** PAPER Day-2  
**Mode:** Simulation Only  
**Target:** Boring (in the best way) ✅

---

## Pre-Open (08:55–09:10 IST)

```bash
# Infra + env
docker compose up -d postgres redis
export APP_MODE=PAPER APP_TIMEZONE=Asia/Kolkata PYTHONPATH=.

# Sanity
make burnin-check
make paper-e2e
make prelive-gate   # should PASS
```

**Expected:**
- ✅ Leader lock: 1
- ✅ All heartbeats < 5s
- ✅ Supervisor: running
- ✅ Pre-live gate: PASS

---

## Market Open (09:15–09:35 IST)

### Keep Gauges Green (Separate Terminal)

```bash
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds|orders_placed_total|orders_filled_total|oco_children_created_total|kill_switch_total|leader_changes_total)" | sort'
```

**Targets All Session:**
- ✅ `trader_is_leader == 1`
- ✅ Heartbeats `< 5s`
- ✅ `trader_scan_ticks_total` rising
- ✅ `trader_leader_changes_total` stays low (0-2 max)

---

## Prove One Clean OCO (09:20–09:25)

```bash
# Inject synthetic plan
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB

# Verify OCO children created
curl -s :8000/metrics | grep trader_oco_children_created_total

# Test flatten
curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_day2"}' | jq

# Verify positions flat
sleep 2 && curl -s :8000/positions | jq 'length'   # expect 0
```

**Expected:**
- ✅ Entry order placed
- ✅ OCO children created (`trader_oco_children_created_total > 0`)
- ✅ Flatten completes ≤ 2s
- ✅ Positions = 0 after flatten

---

## Mid-Session Hygiene (Any Time)

```bash
# Readiness + leadership
curl -s :8000/ready | jq
curl -s :8000/metrics | grep '^trader_is_leader'

# Supervisor status
curl -s :8000/debug/supervisor/status | jq

# Leader changes (should be low)
curl -s :8000/metrics | grep '^trader_leader_changes_total'
```

---

## Cutoffs

* **15:20** → No **new** entries
* **15:25** → Exits allowed till then; be **flat** ≤ 15:25

---

## Post-Close (60s)

```bash
# Generate reports
make burnin-report

# Database reconciliation
make reconcile-db

# Post-close hygiene
make post-close

# Score Day-2
make score-day2   # (or use score-day1 as generic scorer)

# Tag and push
git tag burnin-day2-$(date +%F) && git push --tags
```

---

## Tripwires → One-Liners

### Heartbeat ≥ 5s for >1m
```bash
curl -s -X POST :8000/debug/supervisor/start | jq
```

### Leader Flip to 0
```bash
docker compose restart redis && sleep 10 && curl -s :8000/ready | jq
```

### DB Schema Hiccup
```bash
alembic upgrade head && make reconcile-db
```

### Panic Button
```bash
make abort  # pause + flatten + PAPER
```

---

## Success Criteria

**Day-2 PASS if:**
- ✅ Leader lock: 1 all session
- ✅ All heartbeats < 5s all session
- ✅ One clean OCO lifecycle proven
- ✅ `/flatten` ≤ 2s → positions=0
- ✅ Reconcile: 0 duplicates, 0 orphans
- ✅ Leader changes < 3 in 15m window
- ✅ No alerts fired (especially LeaderFlaps)
- ✅ `/ready` = 200 throughout session

---

**Next:** Day-3 PAPER (if Day-2 PASS) → Canary LIVE (if 3/3 days PASS)


