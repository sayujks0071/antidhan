# Day-2 Final Runbook (Operator-Friendly)

**Target:** Boring (in the best way) ✅  
**Time:** Copy-paste ready, no thinking required

---

## Green-Room Micro-Check (≤15s)

```bash
make verify
bash scripts/check_ntp_drift.sh
bash scripts/read_day2_pass.sh        # prints DAY2 PASS… or exits non-zero
make prelive-gate                     # fail-closed gate
curl -s :8000/metrics | grep -E '^trader_prelive_day2_(pass|age_seconds)'
```

**Expected:**
- ✅ Clock drift check passed
- ✅ `DAY2 PASS …` line
- ✅ `trader_prelive_day2_pass 1`
- ✅ `trader_prelive_day2_age_seconds` small (today)

---

## Day-2 Run (Copy-Paste)

### Pre-Open (08:55–09:10 IST)

```bash
docker compose up -d postgres redis
export APP_MODE=PAPER APP_TIMEZONE=Asia/Kolkata PYTHONPATH=.
make burnin-check && make paper-e2e && make prelive-gate
```

### Keep Gauges Open (Separate Terminal)

```bash
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds|orders_placed_total|orders_filled_total|oco_children_created_total|kill_switch_total|prelive_day2_pass|prelive_day2_age_seconds)" | sort'
```

### Prove One OCO (09:20–09:25)

```bash
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB
curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_day2"}' | jq
sleep 2 && curl -s :8000/positions | jq 'length'   # expect 0
```

### Cutoffs

* **15:20** → No new entries
* **15:25** → Exits allowed; be flat by ≤ 15:25

### Post-Close (≈60s)

```bash
make burnin-report && make reconcile-db && make post-close
make score-day2     # atomic JSON; gauges update
git tag burnin-day2-$(date +%F) && git push --tags
```

---

## What "Green" Looks Like

* ✅ `trader_is_leader == 1` all session
* ✅ Heartbeats `< 5s` (marketdata/order/scan)
* ✅ OCO children created ≥ 1; positions flat on demand (`/flatten` ≤ 2s)
* ✅ Reconcile: duplicates=0, orphans=0
* ✅ `trader_prelive_day2_pass 1`
* ✅ Alerts: none (PreLiveDay2Fail/PreLiveDay2Stale quiet)

---

## One-Liners if Something Blips

### Leader 0 / Readiness 503
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

## Nice-to-Have (Low Effort, High Safety)

### Tmux Pane with Compact Probe

```bash
( QUIET=1 bash scripts/read_day2_pass.sh 2>/dev/null || echo FAIL ) | sed 's/^/DAY2:/'
```

**Output:** `DAY2:PASS` or `DAY2:FAIL`

### Grafana Singlestat Panels

Pin these metrics for at-a-glance monitoring:

1. **`trader_prelive_day2_pass`** (0/1 gauge)
2. **`trader_prelive_day2_age_seconds`** (age in seconds)
3. **`trader_leader_changes_total`** (last 15m delta)

---

## Quick Reference

| Command | Purpose | Exit Code |
|---------|---------|-----------|
| `make verify` | System readiness check | 0=OK |
| `make read-day2` | Read Day-2 status | 0=PASS, 1=FAIL, 2=missing |
| `make prelive-gate` | Full gate check | 0=PASS, 1=FAIL |
| `make score-day2` | Generate Day-2 JSON | 0=PASS, 1=FAIL |

---

**Next:** Day-3 PAPER (if Day-2 PASS) → Canary LIVE (if 3/3 days PASS)


