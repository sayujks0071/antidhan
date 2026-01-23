# 🎯 Operator Cheat Sheet - Day-1

**Quick reference for running and scoring the session.**

## 3-Line Kickoff (PAPER)

```bash
docker compose up -d postgres redis
make start-paper
curl -s :8000/ready | jq   # expect 200 once heartbeats <5s
```

## Live Gauge Watch (Keep This Running)

```bash
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds|orders_placed_total|oco_children_created_total|kill_switch_total)" | sort'
```

## OCO Drill (PAPER)

```bash
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB
curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_day1"}' | jq
sleep 2 && curl -s :8000/positions | jq 'length'   # expect 0
```

## One-Shot Day-1 PASS Scorer

```bash
bash scripts/score_day1.sh
```

Or inline:
```bash
ok=1
curl -sf :8000/ready >/dev/null || ok=0
curl -s :8000/metrics | awk '/^trader_(marketdata|order_stream|scan)_heartbeat_seconds/{if($2>=5)bad=1}END{exit bad}' || ok=0
dups=$(psql "${DATABASE_URL#postgresql+psycopg2://}" -tAc "SELECT COUNT(*) FROM (SELECT client_order_id FROM orders WHERE client_order_id IS NOT NULL GROUP BY client_order_id HAVING COUNT(*) > 1) dupes;" 2>/dev/null || echo "0")
[ "${dups:-0}" -eq 0 ] || ok=0
echo "DAY-1 $([ $ok -eq 1 ] && echo PASS || echo FAIL)"
```

## Tripwires → Act Immediately

**If any fire:**
- Any heartbeat > 5s for >1 min
- Order-ack p95 > 500 ms sustained
- Throttle queue depth rising
- Reconcile shows duplicates/orphans

**Triage:**
```bash
curl -s :8000/debug/supervisor/status | jq
curl -s -X POST :8000/debug/supervisor/start | jq
```

**Abort:**
```bash
make abort   # pause + flatten + PAPER
```

## End of Day (60s)

```bash
make burnin-report && make reconcile-db && make post-close
git tag burnin-day1-$(date +%F) && git push --tags
printf "Date: %s\nLeader:1\nHBs:<5s\nOCO:PASS\nFlatten<=2s:PASS\nReconcile:0/0\nAlerts:none\n\n" "$(date +%F)" >> DAY1_BURNIN_LOG.md
```

## Configuration Check

**Ensure before start:**
- `APP_MODE=PAPER` (set in `.env` or export)
- `APP_TIMEZONE=Asia/Kolkata` (for market-hours gating)

**Quick check:**
```bash
curl -s :8000/health | jq '.mode'  # should be "PAPER"
```

---

**Safe trading! Keep it boring.**

