# Day-2 PAPER Cheat Sheet (Copy-Paste Ready)

**Date:** $(date +%Y-%m-%d)  
**Target:** Boring (in the best way) ✅

---

## Pre-Open (08:55–09:10 IST)

```bash
docker compose up -d postgres redis
export APP_MODE=PAPER APP_TIMEZONE=Asia/Kolkata PYTHONPATH=.
make burnin-check
make paper-e2e
make prelive-gate    # must PASS
```

---

## Market Open Watch (Keep This Running)

```bash
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds|orders_placed_total|orders_filled_total|oco_children_created_total|kill_switch_total|leader_changes_total)" | sort'
```

**Targets:** `trader_is_leader == 1`, heartbeats < 5s, `scan_ticks_total` rising, `leader_changes_total` low

---

## Prove One OCO (09:20–09:25)

```bash
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB
curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_day2"}' | jq
sleep 2 && curl -s :8000/positions | jq 'length'   # expect 0
```

---

## Cutoffs

* **15:20** → No **new** entries
* **15:25** → Exits allowed; be **flat** ≤ 15:25

---

## Post-Close (60s)

```bash
make burnin-report
make reconcile-db
make post-close          # now prints latency p50/p95
make score-day2          # writes JSON to reports/burnin/
git tag burnin-day2-$(date +%F) && git push --tags
```

---

## Quick Sanity on Scorers

```bash
ls -1 reports/burnin/
jq . reports/burnin/day2_*.json
```

**Expected:** `leader==1`, three heartbeats < 5s, `leader_changes` ≤ 2, `status=="PASS"`

---

## If Anything Blips (One-Liners)

### Leader 0
```bash
docker compose restart redis && sleep 10 && curl -s :8000/ready | jq
```

### Scan Stalled
```bash
curl -s :8000/debug/supervisor/status | jq && curl -s -X POST :8000/debug/supervisor/start | jq
```

### Schema Gripe
```bash
alembic upgrade head && make reconcile-db
```

### Emergency
```bash
make abort  # pause + flatten + PAPER
```

---

**Next:** Day-3 PAPER (if Day-2 PASS) → Canary LIVE (if 3/3 days PASS)


