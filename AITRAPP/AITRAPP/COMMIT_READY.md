# Ready to Commit & Tag (After Day-1 PASS)

## ✅ All Fixes & Hardeners Applied

1. **Leader Lock Fix** (`packages/core/leader_lock.py`)
   - Bytes/string compatibility in `acquire()`, `refresh()`, `release()`

2. **Pre-Live Gate Guard** (`scripts/prelive_gate.sh`)
   - Explicit assertion to prevent Redis compatibility regression

3. **Leader Change Tracking** (`packages/core/metrics.py`, `leader_lock.py`, `orchestrator.py`)
   - Counter: `trader_leader_changes_total`
   - Tracks lock loss and re-acquisition

4. **Leader Flaps Alert** (`ops/alerts.yml`)
   - Alerts if >2 leader changes in 15m window

5. **Unit Test** (`tests/test_leader_lock_redis_compat.py`)
   - Standalone Redis compatibility test

6. **Dashboard Chip** (`scripts/quick_leader_check.sh`)
   - Quick status check script

7. **Documentation**
   - `DAY1_STATUS_REPORT.md` (full analysis)
   - `RETEST_PLAN.md` (retest instructions)
   - `DAY2_CHECKLIST.md` (Day-2 burn-in guide)

---

## 🧪 Final Retest (Manual)

```bash
# 1. Start API
make start-paper

# 2. Wait 10-15 seconds, then verify
curl -s :8000/metrics | grep '^trader_is_leader'     # expect 1
curl -s :8000/ready | jq                              # expect 200

# 3. Run scorer
make score-day1

# 4. If PASS, commit & tag
git add -A
git commit -m "fix(leader-lock): bytes/str compat + prelive gate guard + tests + leader change tracking"
git tag burnin-day1-$(date +%F)
git push && git push --tags
```

---

## 📋 Commit Message Template

```
fix(leader-lock): bytes/str compat + prelive gate guard + tests + leader change tracking

- Fix Redis client compatibility (handle both bytes and strings)
- Add pre-live gate regression guard
- Add leader change counter and tracking
- Add LeaderFlaps alert rule
- Add unit test for Redis compatibility
- Add dashboard chip script
- Add Day-1 status report and retest plan
- Add Day-2 checklist

Fixes: Leader lock never acquired due to 'str' object has no attribute 'decode'
Prevents: Redis compatibility regression via pre-live gate
Tracks: Leader lock flaps via metrics and alerts
```

---

## 🎯 After Commit

1. **Day-2 Morning (Before 09:15 IST):**
   ```bash
   make burnin-check
   make paper-e2e
   make prelive-gate
   ```

2. **Monitor During Day-2:**
   - Watch `trader_leader_changes_total` (should stay low)
   - Watch for LeaderFlaps alerts
   - Follow `DAY2_CHECKLIST.md`

---

**Status:** All code changes complete. Ready for manual retest and commit.

