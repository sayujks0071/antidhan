# Day-2 GO Block (Ultra-Tight Ops Wrap)

**Copy-paste ready, execute without thinking**

---

## GO Block (T-5, Copy-Paste)

```bash
make verify && bash scripts/check_ntp_drift.sh && bash scripts/read_day2_pass.sh && make prelive-gate

docker compose up -d postgres redis

export APP_MODE=PAPER APP_TIMEZONE=Asia/Kolkata PYTHONPATH=.

make burnin-check && make paper-e2e && make prelive-gate
```

---

## Keep This Pane Open (Gauges)

```bash
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds|orders_placed_total|orders_filled_total|oco_children_created_total|kill_switch_total|prelive_day2_pass|prelive_day2_age_seconds)" | sort'
```

---

## OCO Prove-Out (09:20–09:25)

```bash
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB

curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_day2"}' | jq

sleep 2 && curl -s :8000/positions | jq 'length'   # expect 0
```

---

## Cutoffs

* **15:20** → No new entries
* **≤15:25** → Be flat

---

## Post-Close (≈60s)

```bash
make burnin-report && make reconcile-db && make post-close

make score-day2

git tag burnin-day2-$(date +%F) && git push --tags
```

---

## Green Criteria (Quick Mental Checklist)

* ✅ Leader `== 1` all session
* ✅ Heartbeats `< 5s` (marketdata / order / scan)
* ✅ OCO children ≥ 1; `/flatten` ≤ 2s → positions=0
* ✅ Reconcile: duplicates=0, orphans=0
* ✅ `trader_prelive_day2_pass 1`, `trader_prelive_day2_age_seconds` small
* ✅ No alerts (PreLiveDay2Fail / PreLiveDay2Stale)

---

## If-Then One-Liners

| Issue | Command |
|-------|---------|
| **Leader 0 / readiness 503** | `docker compose restart redis && sleep 10 && curl -s :8000/ready \| jq` |
| **Scan stalled** | `curl -s :8000/debug/supervisor/status \| jq && curl -s -X POST :8000/debug/supervisor/start \| jq` |
| **Schema gripe** | `alembic upgrade head && make reconcile-db` |
| **Emergency** | `make abort` (pause + flatten + PAPER) |

---

**You're green-lit. Run the GO block, keep the gauges green, log one clean OCO, score Day-2, tag.**


