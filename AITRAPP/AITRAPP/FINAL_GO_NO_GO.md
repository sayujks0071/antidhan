# Final Go/No-Go Gates

## 🎯 Pre-Burn-In Checklist

### Time Synchronization
- [ ] Container clocks synced to IST (`TZ=Asia/Kolkata` on all services)
- [ ] Host NTP healthy
- [ ] Time-stops use IST from config

### Single Runner
- [ ] Only one orchestrator active
- [ ] Leader lock implemented and working
- [ ] Redis leader-lock prevents dual runners

### Secrets
- [ ] `KITE_*` valid, no expiry during session
- [ ] `.env` not mounted read-only by mistake
- [ ] Access token rotated if required

### Database
- [ ] `alembic upgrade head` ran successfully
- [ ] `orders.client_order_id` is **unique** (check constraint)
- [ ] WAL (Write-Ahead Logging) enabled on Postgres

### Metrics
- [ ] `/metrics` exposes `trader_*` metrics
- [ ] Counters increment in smoke test
- [ ] All expected metrics present

### Kill Path
- [ ] `/flatten` closes all positions ≤ 2s in PAPER
- [ ] Tested under load
- [ ] Blocks new entries until unpause

### EOD Behavior
- [ ] Auto-tighten at 15:20 IST
- [ ] Hard flat at 15:25 IST
- [ ] Verified in paper replay
- [ ] Zero open orders after 15:25

---

## Red-Team Drills (10 min, before Day-1 paper)

### 1. WebSocket Drop
**Test:** Kill broker WS for 30s
**Pass:** Reconnects; no duplicate children placed
**Command:**
```bash
# Simulate network drop
# Verify reconnection in logs
# Check for duplicate orders
```

### 2. LIMIT Rejection
**Test:** Force stale price LIMIT order
**Pass:** Dedupe holds; retry bounded
**Command:**
```bash
# Place LIMIT with stale price
# Verify single order entry
# Check retry logic
```

### 3. Partial Fill
**Test:** Tiny qty partial fill
**Pass:** Reprice within freeze/tick; OCO attaches for remainder
**Command:**
```bash
# Simulate partial fill
# Verify reprice logic
# Check OCO for remainder
```

### 4. Illiquidity
**Test:** Widen spread beyond threshold
**Pass:** Risk block fires; no new entries
**Command:**
```bash
# Simulate wide spreads
# Verify risk block
# Check no orders placed
```

### 5. Redis Down
**Test:** Stop Redis
**Pass:** Trading continues; dashboard loses events; resumes when back
**Command:**
```bash
docker compose stop redis
# Verify API continues
docker compose start redis
# Verify events resume
```

### 6. DB Restart
**Test:** Bounce Postgres
**Pass:** App recovers; no lost idempotency
**Command:**
```bash
docker compose restart postgres
# Verify app recovers
# Check idempotency still works
```

### 7. Clock Skew
**Test:** Set container TZ wrong
**Pass:** Time-stops use IST from config
**Command:**
```bash
# Set wrong TZ
# Verify time-stops use config TZ
```

### 8. Network Flap
**Test:** Drop outbound for 10s
**Pass:** No duplicate orders after recover
**Command:**
```bash
# Simulate network flap
# Verify no duplicates
```

### 9. EOD Race
**Test:** Keep position at 15:19
**Pass:** Tighten then flat by 15:25
**Command:**
```bash
# Open position at 15:19
# Verify tighten at 15:20
# Verify flat at 15:25
```

### 10. Kill Switch Under Load
**Test:** Kill switch during active fill churn
**Pass:** Flat ≤ 2s; block new entries until unpause
**Command:**
```bash
# Generate active fills
# Press kill switch
# Verify ≤ 2s flat
# Verify new entries blocked
```

---

## Final Go/No-Go Gates

### Gate 1: Pre-Burn-In
**Go if:**
- ✅ All pre-burn-in checklist items pass
- ✅ Leader lock working
- ✅ Kill switch ≤ 2s
- ✅ EOD behavior verified

**No-Go if:**
- ❌ Any checklist item fails
- ❌ Leader lock not working
- ❌ Kill switch > 2s
- ❌ EOD behavior incorrect

### Gate 2: Red-Team Drills
**Go if:**
- ✅ All 10 drills pass
- ✅ No critical issues discovered

**No-Go if:**
- ❌ Any drill fails
- ❌ Critical issues found

### Gate 3: 3-Day Burn-In
**Go if:**
- ✅ All 3 days pass criteria
- ✅ No duplicate `client_order_id` ever
- ✅ Zero orphan OCO siblings after exits
- ✅ Reports + reconciliation clean

**No-Go if:**
- ❌ Any day fails
- ❌ Duplicates found
- ❌ Orphans found
- ❌ Reconciliation issues

### Gate 4: Final Validation
**Go if:**
- ✅ `/flatten` ≤ 2s under load
- ✅ Leader lock prevents dual runners
- ✅ EOD tight/flat at 15:20/15:25 IST
- ✅ All reports clean

**No-Go if:**
- ❌ Any validation fails
- ❌ Issues discovered

---

## If Any Gate Fails

1. **Pause** trading
2. **Flatten** all positions
3. **Revert** to PAPER mode
4. **Fix** the issue
5. **Re-run** Day-0 half-session
6. **Re-test** failed gate

---

## Success Path

1. ✅ Pre-burn-in checklist passes
2. ✅ Red-team drills pass
3. ✅ 3-day burn-in passes
4. ✅ Final validation passes
5. ✅ **READY FOR LIVE**

---

## First Hour LIVE

See `FIRST_HOUR_LIVE_PLAYBOOK.md` for detailed procedure.

**Key Points:**
- Start in PAPER at 09:05
- Switch to LIVE at 09:10
- Conservative caps (0.25%, 1.0%, 1.0%)
- Monitor dashboard continuously
- Keep kill switch ready

---

## Post-Close Ritual

See `POST_CLOSE_RITUAL.md` for daily procedure.

**Key Steps:**
1. Verify zero open orders/positions
2. Generate report: `make burnin-report`
3. Run reconciliation: `psql -f scripts/reconcile_db.sql`
4. Snapshot config SHA + tag git
5. Rotate token if required

---

## Final Checklist

Before enabling LIVE:
- [ ] All gates passed
- [ ] Red-team drills complete
- [ ] 3-day burn-in successful
- [ ] Leader lock working
- [ ] Kill switch tested
- [ ] EOD behavior verified
- [ ] Reports clean
- [ ] Dashboard ready
- [ ] First hour playbook reviewed
- [ ] Post-close ritual understood

**You're ready. Flip to PAPER, run burn-in, then go LIVE.**

