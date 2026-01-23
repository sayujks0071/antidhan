# Day-1 Retest Plan (After Leader Lock Fix)

## ✅ Fixes Applied

1. **Leader Lock Redis Compatibility** (`packages/core/leader_lock.py`)
   - Fixed `acquire()`, `refresh()`, and `release()` to handle both bytes and strings
   - Prevents `'str' object has no attribute 'decode'` errors

2. **Pre-Live Gate Regression Guard** (`scripts/prelive_gate.sh`)
   - Added explicit assertion: `test "${leader:-0}" = "1" || exit 1`
   - Prevents Redis compatibility regression from slipping through

3. **Unit Test** (`tests/test_leader_lock_redis_compat.py`)
   - Standalone test (no pytest required)
   - Tests acquire/refresh/release with Redis

4. **Dashboard Chip** (`scripts/quick_leader_check.sh`)
   - Quick status check for leader lock + supervisor + heartbeats
   - Use in tmux pane or Next.js dashboard

---

## 🧪 Quick Retest (Copy-Paste)

```bash
# 1. Restart API
lsof -nP -iTCP:8000 | awk '/LISTEN/ {print $2}' | xargs kill -TERM 2>/dev/null || true
make start-paper

# 2. Wait for API to start (10 seconds)
sleep 10

# 3. Verify leadership + readiness
curl -s :8000/metrics | grep '^trader_is_leader'     # should be 1
curl -s :8000/ready | jq                              # should be 200

# 4. Prove one OCO lifecycle (PAPER)
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB
curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_day1_fix"}' | jq
sleep 2 && curl -s :8000/positions | jq 'length'      # expect 0

# 5. Score Day-1
make score-day1
```

---

## 🔍 Sanity Checks

### DATABASE_URL (if using Postgres)

```bash
export DATABASE_URL="postgresql+psycopg2://trader:trader@localhost:5432/aitrapp"
alembic upgrade head
make reconcile-db
```

### Redis Compatibility Unit Test

```bash
# Run standalone test
python tests/test_leader_lock_redis_compat.py
```

Expected output:
```
Testing acquire...
✅ acquire passed
Testing refresh...
refresh_ok: True
✅ refresh passed
Testing release...
✅ release passed

✅ All leader lock compatibility tests passed!
```

---

## 📊 Dashboard Chip

```bash
# Quick status check
bash scripts/quick_leader_check.sh
```

Output:
```
=== Leadership & Supervisor Status ===
✅ Leader: ACQUIRED (1)
✅ Supervisor: running (1)
📊 Scan Ticks: 1088

=== Heartbeats ===
Market Data:   0.38s ✅
Order Stream:  1.00s ✅
Scan Loop:     0.56s ✅
```

---

## ✅ Success Criteria

**Day-1 PASS if:**
- ✅ `trader_is_leader == 1` (leader lock acquired)
- ✅ `/ready` returns 200 (all heartbeats < 5s)
- ✅ OCO lifecycle proven (injector + flatten works)
- ✅ `make score-day1` returns PASS
- ✅ No duplicate `client_order_id` (if DB available)
- ✅ No orphan OCO children (if DB available)

---

## 🎯 Expected Outcome

After applying the leader lock fix:
1. Leader lock acquires successfully → `trader_is_leader = 1`
2. Orchestrator unpauses → signals/orders can be generated
3. `/ready` returns 200 → system ready for trading
4. OCO lifecycle works → `trader_oco_children_created_total > 0`
5. Day-1 scorer passes → **Day-1 PASS** ✅

---

**Next:** Run the retest plan above and verify Day-1 PASS.

