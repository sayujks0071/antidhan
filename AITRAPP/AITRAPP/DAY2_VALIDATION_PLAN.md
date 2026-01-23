# Day-2 Validation & Run Plan

## 1) Validate the New Gate End-to-End (2–3 min)

```bash
# Fresh scorer JSON present + PASS (jq-less)
bash scripts/read_day2_pass.sh

# Shell gate (fails closed)
make prelive-gate

# API gate mirrors shell logic
curl -s :8000/ready | jq       # should be 200 during active session
curl -s :8000/metrics | grep -E '^trader_prelive_day2_(pass|age_seconds)'
```

**Expected:**
- `DAY2 PASS …` line from reader
- `trader_prelive_day2_pass 1`
- `trader_prelive_day2_age_seconds` small (today)
- `/ready` returns 200

---

## 2) Day-2 Run (Copy-Paste)

### Pre-Open (08:55–09:10 IST)

```bash
docker compose up -d postgres redis
export APP_MODE=PAPER APP_TIMEZONE=Asia/Kolkata PYTHONPATH=.
make burnin-check && make paper-e2e && make prelive-gate
```

### Watch Gauges (Separate Terminal)

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

- **15:20** → No new entries
- **15:25** → Exits allowed; be flat by ≤ 15:25

### Post-Close (60s)

```bash
make burnin-report && make reconcile-db && make post-close
make score-day2     # writes atomic JSON + updates prelive gauges
git tag burnin-day2-$(date +%F) && git push --tags
```

---

## 3) Quick Alert Sanity (Optional, After Hours)

Use chaos scripts to trigger alert paths safely:

```bash
# Leader loss → PreLiveDay2Fail should fire if JSON becomes FAIL/missing
make chaos-suite   # includes leader lock + Postgres + rate-limit drills
```

---

## 4) Guardrails

- ✅ Clock skew check (NTP drift > 2s fails startup)
- ✅ Mode safety (assert APP_MODE != LIVE, log config_sha + git_head to AuditLog)

---

**Next:** Day-3 PAPER (if Day-2 PASS) → Canary LIVE (if 3/3 days PASS)


