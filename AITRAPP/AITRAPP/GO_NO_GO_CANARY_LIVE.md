# Go/No-Go for Canary LIVE (After Day-3)

**Decision Date:** $(date +%Y-%m-%d)  
**Status:** [ ] GO / [ ] NO-GO

---

## Prerequisites (All Must Pass)

### 1. Burn-In History
- [ ] **3/3 days: PASS**
  - Day-1: PASS ✅
  - Day-2: PASS ✅
  - Day-3: PASS ✅

### 2. Leader Lock Stability
- [ ] **No leader flaps during market hours** (or minimal, with fast auto-heal)
  - `trader_leader_changes_total` < 3 per day
  - No LeaderFlaps alerts fired
  - Auto-reacquire works (verified in chaos tests)

### 3. Database Integrity
- [ ] **Reconcile: 0 duplicates / 0 orphans**
  - Run: `make reconcile-db`
  - Verify: No duplicate `client_order_id`
  - Verify: No orphan OCO children

### 4. Flatten Performance
- [ ] **`/flatten` ≤ 2s consistently**
  - Verified in all 3 days
  - No timeouts or errors

### 5. Alert Status
- [ ] **Alerts: none (or only test alerts)**
  - Check Prometheus alerts
  - No critical alerts during market hours
  - No LeaderFlaps alerts
  - No heartbeat stale alerts

---

## Additional Checks

### 6. Latency Metrics
- [ ] **Order latency p95 < 500ms**
  - Run: `make print-latency`
  - Verify: P95 order latency acceptable

### 7. OCO Lifecycle
- [ ] **At least one clean OCO lifecycle per day**
  - Entry → SL/TP created → Fill → Cancel
  - Verified in all 3 days

### 8. Pre-Live Gate
- [ ] **Pre-live gate PASS**
  - Run: `make prelive-gate`
  - All checks green

---

## Decision Matrix

| Criteria | Day-1 | Day-2 | Day-3 | Status |
|----------|-------|-------|-------|--------|
| Burn-In PASS | [ ] | [ ] | [ ] | [ ] |
| Leader Flaps < 3 | [ ] | [ ] | [ ] | [ ] |
| Reconcile: 0/0 | [ ] | [ ] | [ ] | [ ] |
| Flatten ≤ 2s | [ ] | [ ] | [ ] | [ ] |
| No Alerts | [ ] | [ ] | [ ] | [ ] |

**Decision:** [ ] GO / [ ] NO-GO

---

## If GO

1. **Load canary LIVE profile:**
   ```bash
   cp configs/canary_live.yaml configs/app.yaml
   ```

2. **Run pre-live gate:**
   ```bash
   make prelive-gate
   ```

3. **Switch to LIVE:**
   ```bash
   # Follow LIVE_SWITCH_RUNBOOK.md
   ```

---

## If NO-GO

**Blockers:**
- [ ] List specific failures
- [ ] Assign fixes
- [ ] Re-test after fixes
- [ ] Re-evaluate after Day-4

---

**Reviewed By:** _________________  
**Date:** _________________


