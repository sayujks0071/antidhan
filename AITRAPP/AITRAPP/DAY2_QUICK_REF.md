# Day-2 Quick Reference Card

**Copy-paste ready, no thinking required**

---

## T-5 Micro-GO (≤15s)

```bash
make verify
bash scripts/check_ntp_drift.sh
bash scripts/read_day2_pass.sh
make prelive-gate
```

---

## Morning Run (Copy-Paste)

```bash
docker compose up -d postgres redis
export APP_MODE=PAPER APP_TIMEZONE=Asia/Kolkata PYTHONPATH=.
make burnin-check && make paper-e2e && make prelive-gate
```

---

## Watch Gauges (Keep Open)

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
* **≤15:25** → Be flat (exits allowed to 15:25)

---

## Post-Close (≈60s)

```bash
make burnin-report && make reconcile-db && make post-close
make score-day2
git tag burnin-day2-$(date +%F) && git push --tags
```

---

## Quick "Green" Scoreboard

* ✅ `trader_is_leader == 1` all session
* ✅ Heartbeats `< 5s` (marketdata/order/scan)
* ✅ OCO children created ≥ 1; `/flatten` ≤ 2s → positions=0
* ✅ Reconcile: duplicates=0, orphans=0
* ✅ `trader_prelive_day2_pass 1` and `trader_prelive_day2_age_seconds` small
* ✅ Alerts: none (PreLiveDay2Fail/PreLiveDay2Stale quiet)

---

## One-Liner Triage

| Issue | Command |
|-------|---------|
| **Leader 0 / readiness 503** | `docker compose restart redis && sleep 10 && curl -s :8000/ready \| jq` |
| **Scan stalled** | `curl -s :8000/debug/supervisor/status \| jq && curl -s -X POST :8000/debug/supervisor/start \| jq` |
| **Schema gripe** | `alembic upgrade head && make reconcile-db` |
| **Emergency** | `make abort` (pause + flatten + PAPER) |

---

## Optional Nice-to-Have

### Tmux Probe Badge
```bash
( QUIET=1 bash scripts/read_day2_pass.sh 2>/dev/null || echo FAIL ) | sed 's/^/DAY2:/'
```

### Grafana Singlestat Panels (PromQL)
* `trader_prelive_day2_pass`
* `trader_prelive_day2_age_seconds`
* `rate(trader_leader_changes_total[15m])`

---

**You're ready. Flip the sequence, keep the five gauges green, log one clean OCO, score Day-2, tag, done.**


