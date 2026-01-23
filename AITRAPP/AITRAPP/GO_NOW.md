# 🚀 GO NOW - Day-1 Execution

**Copy-paste ready. Execute immediately.**

## GO NOW (Copy-Paste)

```bash
# Infra
docker compose up -d postgres redis

# API + readiness (single worker)
make start-paper
curl -s :8000/ready | jq   # should go 200 once heartbeats <5s

# Unpause if needed
curl -s :8000/state | jq '{running,paused}'
# if paused:true → toggle until false
curl -s -X POST :8000/pause | jq
```

## 15:00-15:07 — Prove One OCO (PAPER)

```bash
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB

# Counters should bump
curl -s :8000/metrics | grep -E '^trader_(orders_placed_total|oco_children_created_total)'

# Safety: flatten ≤2s and flat = 0
curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_day1"}' | jq
sleep 2 && curl -s :8000/positions | jq 'length'
```

## Keep This Running (Watch Gauges)

```bash
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds|orders_placed_total|oco_children_created_total|kill_switch_total)" | sort'
```

**✅ Green all session:**
- `trader_is_leader == 1`
- Three heartbeats `< 5s`
- `trader_scan_ticks_total` rising

## Cutoffs (Important)

- **15:20** → **No new entries** (market-hours gate enforces this)
- **15:25** → Exits allowed until then; make sure you're **flat** before/at 15:25

## Post-Close (60s Total)

```bash
make burnin-report
make reconcile-db
make post-close
git tag burnin-day1-$(date +%F) && git push --tags
make score-day1   # prints PASS/FAIL
```

## If Scorer Says FAIL (Fast Triage)

### Heartbeats ≥5s
```bash
# Check supervisor
curl -s :8000/debug/supervisor/status | jq

# Kick it
curl -s -X POST :8000/debug/supervisor/start | jq
```

### Not Ready (503)
```bash
# Verify Redis/Postgres + leader
curl -s :8000/metrics | grep '^trader_is_leader'

# If 0, leader lock reacquire loop will try; watch it recover
# If stuck: docker compose restart redis
```

### Duplicates/Orphans
```bash
# Re-run reconcile
make reconcile-db

# Skim logs for repeated client_order_id
# If found, keep today as FAIL, fix, and rerun tomorrow
```

## Sanity Before Start

- ✅ Ensure envs: `APP_MODE=PAPER`, `TZ/APP_TIMEZONE=Asia/Kolkata`
- ✅ One uvicorn worker (no multiprocess Prometheus confusion)

---

**You're good. Run the GO block now, do the OCO drill before 15:10, keep the five gauges green, and close with `make score-day1`.**
