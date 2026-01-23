# 🚀 Day-1 GO Sequence (T-5 mins)

**Copy-paste ready. Keep it boring.**

## T-5 mins GO

```bash
# Infra
docker compose up -d postgres redis

# API (single worker) + health
make start-paper
curl -s :8000/ready | jq   # expect 200 once heartbeats <5s

# Burn-in quick checks
make burnin-check
make paper-e2e

# Open dashboard
make live-dashboard && tmux attach -t live
```

## First 10 mins

```bash
# Watch the five gauges (refresh 5s)
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds|orders_placed_total|oco_children_created_total|kill_switch_total)" | sort'
```

**Green all session:**
- `trader_is_leader == 1`
- Three heartbeats `< 5s`
- `trader_scan_ticks_total` rising
- After injector: `orders_placed_total > 0`, `oco_children_created_total > 0`

## One Clean OCO Drill (PAPER)

```bash
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB
curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_day1"}' | jq
sleep 2 && curl -s :8000/positions | jq 'length'    # expect 0
```

## Tripwires → Immediate Action

**If any fire:**
- Any heartbeat > 5s for >1 min
- Ack p95 > 500ms sustained
- Throttle queue depth rising
- Reconcile shows dups/orphans

**Triage / Self-Heal:**
```bash
curl -s :8000/debug/supervisor/status | jq
curl -s -X POST :8000/debug/supervisor/start | jq
```

**Abort Macro (pause + flatten + PAPER):**
```bash
make abort
```

## End-of-Day (60s)

```bash
make burnin-report
make reconcile-db
make post-close
git tag burnin-day1-$(date +%F) && git push --tags
```

## Log Day-1 PASS

```bash
printf "Date: %s\nLeader:1\nHBs:<5s\nOCO:PASS\nFlatten<=2s:PASS\nReconcile:0/0\nAlerts:none\n\n" "$(date +%F)" >> DAY1_BURNIN_LOG.md
```

## Optional After Hours

```bash
make chaos-suite
```

Proves leader-loss, rate-limit, and DB blip resilience.

---

**You're set. Keep the five gauges green, do one clean OCO, reconcile clean—then stamp Day-1 PASS.**

