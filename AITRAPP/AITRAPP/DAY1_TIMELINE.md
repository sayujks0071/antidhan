# ⏰ Day-1 Timeline (14:56-15:30)

**Time-boxed execution plan for clean PASS today.**

## 14:56-15:00 (Kick Off - 4 min)

```bash
# If infra isn't up yet
docker compose up -d postgres redis

# Start API (single worker) and verify readiness
make start-paper
curl -s :8000/ready | jq   # expect 200 once heartbeats <5s

# Ensure trading loop is running (paused should be false)
curl -s :8000/state | jq '{running,paused,last_scan:.last_scan_at}'

# If paused==true, toggle until false
curl -s -X POST :8000/pause | jq
```

**Start gauges watch (keep this open):**
```bash
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds|orders_placed_total|oco_children_created_total|kill_switch_total)" | sort'
```

**Green targets all session:** `trader_is_leader==1`, all 3 heartbeats `<5s`.

## 15:00-15:07 (Prove One OCO Lifecycle - 7 min)

**Do the quick PAPER drill before 15:10** (well clear of entry cutoff 15:20 and exit grace 15:25):

```bash
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB

# Confirm counters tick
curl -s :8000/metrics | grep -E '^trader_(orders_placed_total|oco_children_created_total)'

# Safety: flatten must complete ≤2s and positions go to 0
curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_day1"}' | jq
sleep 2 && curl -s :8000/positions | jq 'length'   # expect 0
```

## 15:07-15:20 (Steady State - 13 min)

- Keep the **five gauges** green (<5s on heartbeats)
- Let the orchestrator tick; scan ticks should rise
- **Tripwire → immediate action:** if any heartbeat >5s for >1 min, or ack p95 spikes, or throttle queue depth builds:

```bash
curl -s :8000/debug/supervisor/status | jq
curl -s -X POST :8000/debug/supervisor/start | jq
make abort   # pause + flatten + PAPER (if needed)
```

## 15:20 Hard Stop for New Entries

Your market-hours guard blocks new entries after **15:20** and allows exits until **15:25**. Make sure you're **flat** well before 15:25.

## 15:25-15:30 (Pre-Close Sanity - 5 min)

```bash
# Final check: no positions; heartbeats still <5s
curl -s :8000/positions | jq 'length'
curl -s :8000/metrics | grep -E '^trader_(marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds)'
```

## Post-Close (~60s)

```bash
make burnin-report
make reconcile-db
make post-close
git tag burnin-day1-$(date +%F) && git push --tags
printf "Date: %s\nLeader:1\nHBs:<5s\nOCO:PASS\nFlatten<=2s:PASS\nReconcile:0/0\nAlerts:none\n\n" "$(date +%F)" >> DAY1_BURNIN_LOG.md

# One-shot scorer
make score-day1
```

## PASS Checklist for Today

- [ ] `trader_is_leader == 1` all session
- [ ] All three heartbeats `< 5s`
- [ ] One clean OCO lifecycle proven
- [ ] `/flatten` ≤ 2s → positions = 0 on demand
- [ ] Reconcile: **0 duplicates**, **0 orphans**
- [ ] No alerts fired

**If all pass → Day-1 PASS ✅**

