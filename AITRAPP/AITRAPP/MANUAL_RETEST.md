# Manual Retest Guide (Day-1 → PASS)

## Quick Retest Sequence

```bash
# 1) Start API (in foreground to see errors)
make start-paper

# Wait 15-20 seconds for full startup, then in another terminal:

# 2) Readiness + Leadership
curl -s :8000/metrics | grep '^trader_is_leader'    # expect 1
curl -s :8000/ready | jq                             # expect 200

# 3) Heartbeats < 5s (numeric)
curl -s :8000/metrics | awk '/^trader_(marketdata|order_stream|scan)_heartbeat_seconds/{if($2>=5)bad=1}END{exit bad}' && echo ok

# 4) Scorer
make score-day1
```

---

## If PASS → Commit & Tag

```bash
git add -A
git commit -m "fix(leader-lock): bytes/str compat + prelive guard + tests + leader-change tracking"
git tag burnin-day1-$(date +%F)
git push && git push --tags
```

---

## Quick Sanity (Optional, 20s)

```bash
# Flaps should be tiny or zero after the fix
curl -s :8000/metrics | grep '^trader_leader_changes_total'

# Fast leader chip
bash scripts/quick_leader_check.sh
```

---

## If FAIL - Fast Triage

### Leader == 0
```bash
# Restart Redis
docker compose restart redis
# OR if local Redis:
# brew services restart redis
# OR
# sudo systemctl restart redis

sleep 10
curl -s :8000/ready | jq
```

### Scan Stalled
```bash
curl -s :8000/debug/supervisor/status | jq
curl -s -X POST :8000/debug/supervisor/start | jq
```

### DB Checks Blocked
```bash
export DATABASE_URL="postgresql+psycopg2://trader:trader@localhost:5432/aitrapp"
alembic upgrade head
make reconcile-db
make score-day1
```

---

## Day-2 Morning (PAPER, Pre-Open)

```bash
make burnin-check
make paper-e2e
make prelive-gate
```

---

## Expected Results

**After fix:**
- ✅ `trader_is_leader = 1` (leader lock acquired)
- ✅ `/ready` returns 200 (all heartbeats < 5s)
- ✅ All heartbeats < 5s
- ✅ `make score-day1` returns PASS
- ✅ `trader_leader_changes_total` stays low/zero

**If all green → Day-1 PASS → Commit & Tag**

