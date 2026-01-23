# ✅ Burn-In Plan Complete - Ready for Validation

## 📦 What Was Created

### Scripts

1. **`scripts/verify_env.py`** - Environment & connectivity checker
   - Validates required env vars
   - Checks port accessibility
   - Usage: `make verify`

2. **`scripts/smoke_test.sh`** - 60-minute smoke test
   - Health & metrics checks
   - Kill switch validation
   - Metrics incrementing test
   - Usage: `make smoke-test`

3. **`scripts/test_idempotency.py`** - Idempotency validator
   - Tests deterministic ID generation
   - Verifies same plan → same IDs
   - Tests OCO children IDs
   - Usage: `python scripts/test_idempotency.py`

4. **`scripts/synthetic_plan_injector.py`** - Synthetic plan tester
   - Injects controlled plans
   - Tests idempotency paths
   - Validates OCO children creation
   - Usage: `python scripts/synthetic_plan_injector.py`

5. **`scripts/rollback.sh`** - Rollback procedure
   - Pause → Flatten → Switch to PAPER
   - Usage: `make rollback`

6. **`scripts/reconcile_db.sql`** - Post-trade reconciliation
   - Orphan detection
   - Duplicate checks
   - Audit trail validation
   - Usage: `psql $DATABASE_URL -f scripts/reconcile_db.sql`

### Documentation

1. **`BURN_IN_PLAN.md`** - Complete burn-in protocol
   - Pre-flight checklist
   - Day-0 half-session
   - 3-day burn-in requirements
   - Go/No-Go gates
   - Failure drills
   - LIVE gate procedure
   - Rollback procedure

2. **`README_BURN_IN.md`** - Quick reference
   - Fast commands
   - Key scripts
   - Links to full docs

3. **`ops/alerts.yml`** - Prometheus alerting rules
   - No signals alert
   - High portfolio heat
   - Stuck orders
   - Daily loss approaching
   - WebSocket reconnects
   - API latency

### Makefile Targets

- `make verify` - Verify environment
- `make smoke-test` - Run smoke tests
- `make burnin-report` - Generate daily report
- `make rollback` - Rollback to PAPER

---

## 🚀 Quick Start

### Pre-Flight
```bash
alembic upgrade head
make verify
docker compose up -d postgres redis
make paper
```

### Smoke Test
```bash
make smoke-test
python scripts/test_idempotency.py
```

### Day-0 Half-Session
- Run during market hours
- Monitor logs
- Test kill switch
- Validate OCO invariants

### 3-Day Burn-In
- Follow `BURN_IN_PLAN.md`
- Each day must pass all criteria
- Generate reports: `make burnin-report`
- Run reconciliation: `psql $DATABASE_URL -f scripts/reconcile_db.sql`

### LIVE Gate
After 3/3 days pass:
```bash
curl -X POST localhost:8000/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"LIVE","confirm":"CONFIRM LIVE TRADING"}'
```

---

## 📋 Daily Checklist

**Pre-Open:**
- [ ] `make verify`
- [ ] `make paper`
- [ ] Set mode to PAPER

**During Session:**
- [ ] Monitor logs
- [ ] Check metrics
- [ ] Monitor risk
- [ ] Test kill switch once

**Post-Close:**
- [ ] Verify EOD flat
- [ ] Run reconciliation
- [ ] Generate report
- [ ] Archive report

---

## 🎯 Success Criteria

**3-Day Burn-In Passes If:**
- ✅ All 3 days meet daily requirements
- ✅ No critical errors
- ✅ All failure drills pass
- ✅ Data integrity maintained
- ✅ Risk limits respected
- ✅ EOD flat successful

**Then:** Enable LIVE mode with conservative caps.

---

## 🔧 Failure Drills

Before LIVE, test:
1. Redis failure → API continues
2. WebSocket drop → Reconnect, no duplicates
3. Order rejection → Retry bounded, idempotency holds
4. Wide spreads → Risk block, no new entries

---

## 📊 Dashboard MVP

**Priority 1:**
- Top Ranks with attribution
- Positions (qty, avg, SL/TP, P&L)
- Portfolio Heat
- Daily P&L
- Kill Switch

**Socket Channels:**
- `signals`, `decisions`, `orders`, `risk`, `events`

---

## 🆘 Rollback

If issues in LIVE:
```bash
make rollback
# Then restart API
```

---

## 📝 Next Steps

1. Run pre-flight checklist
2. Execute 60-minute smoke test
3. Run Day-0 half-session
4. Complete 3-day burn-in
5. Run failure drills
6. Enable LIVE mode

**Status: READY FOR BURN-IN** 🎉

