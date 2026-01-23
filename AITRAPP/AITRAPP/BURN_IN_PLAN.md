# Paper Burn-in Plan & Go/No-Go Gates

## 🎯 Objective

Validate system integrity, idempotency, OCO invariants, and risk guardrails over 3 full trading sessions before enabling LIVE mode.

---

## Pre-Flight Checklist (One-Time)

### 1. Database Setup
```bash
alembic upgrade head
```

### 2. Environment Verification
```bash
make verify
```

**Required `.env` variables:**
- `KITE_API_KEY`
- `KITE_API_SECRET`
- `KITE_ACCESS_TOKEN`
- `DATABASE_URL`
- `REDIS_URL`
- `APP_TIMEZONE=Asia/Kolkata`

### 3. Infrastructure
```bash
docker compose up -d postgres redis
```

### 4. Start API
```bash
make paper
```

---

## 60-Minute Smoke Test

**Run immediately after startup:**

```bash
./scripts/smoke_test.sh
python scripts/test_idempotency.py
```

**Pass Criteria:**
- ✅ All endpoints respond
- ✅ Metrics present and incrementing
- ✅ Kill switch completes ≤ 2s
- ✅ Same plan generates same IDs
- ✅ No duplicate `client_order_id` in DB

---

## Day-0 Half-Session (Paper)

**Objective:** Prove kill-path, OCO invariants, and idempotency under real ticks.

**Duration:** 2-3 hours during market hours

**Pass Criteria:**
- ✅ `/flatten` closes all positions in ≤ 2s
- ✅ For each filled OCO child, sibling is cancelled (no orphans)
- ✅ No duplicate `client_order_id` rows in DB
- ✅ Complete DB chain: `signal → decision → orders → trades` with `config_sha`

**Validation:**
```bash
# Check for orphans
psql $DATABASE_URL -f scripts/reconcile_db.sql

# Check for duplicates
psql $DATABASE_URL -c "SELECT client_order_id, COUNT(*) FROM orders GROUP BY client_order_id HAVING COUNT(*) > 1;"

# Generate report
make burnin-report
```

---

## 3-Day Burn-In (Paper)

Each day must satisfy all criteria:

### Daily Requirements

1. **Signal Generation**
   - ≥ 50 signals generated
   - ≥ 3 decisions planned
   - ≥ 1 complete OCO lifecycle observed

2. **Risk Management**
   - `trader_portfolio_heat_rupees` never exceeds configured cap
   - Daily loss stop respected
   - Per-trade risk limits enforced

3. **EOD Behavior**
   - Tightened at 15:20 IST
   - Hard flat at 15:25 IST
   - Zero open orders after 15:25 IST

4. **Data Integrity**
   - Complete audit trail: `signal → decision → orders → trades`
   - All orders have `config_sha`
   - No orphan OCO siblings
   - No duplicate `client_order_id`

5. **Report Generation**
   ```bash
   make burnin-report
   ```
   Report must include:
   - MAE/MFE distribution
   - P&L breakdown
   - Heat timeline
   - Risk events

### Daily Checklist

**Pre-Open (08:30 IST):**
- [ ] `make verify`
- [ ] `make migrate` (if needed)
- [ ] `make paper`
- [ ] Set mode: `curl -X POST localhost:8000/mode -d '{"mode":"PAPER"}'`

**During Session:**
- [ ] Monitor logs: `tail -f logs/aitrapp.log | jq`
- [ ] Check metrics: `curl localhost:8000/metrics | grep trader_`
- [ ] Monitor risk: `curl localhost:8000/risk | jq`
- [ ] Test kill switch once: `curl -X POST localhost:8000/flatten`

**Post-Close (15:30 IST):**
- [ ] Verify EOD flat: `curl localhost:8000/positions | jq`
- [ ] Run reconciliation: `psql $DATABASE_URL -f scripts/reconcile_db.sql`
- [ ] Generate report: `make burnin-report`
- [ ] Archive report: `cp burnin-report-$(date +%Y%m%d).txt reports/`

---

## Go/No-Go Gates

### Gate 1: Day-0 Half-Session
**Go if:**
- ✅ All pass criteria met
- ✅ No critical errors in logs
- ✅ Kill switch works

**No-Go if:**
- ❌ Orphan OCO siblings found
- ❌ Duplicate orders detected
- ❌ Kill switch fails
- ❌ Data integrity issues

### Gate 2: Day-1 Full Session
**Go if:**
- ✅ All daily requirements met
- ✅ No risk limit breaches
- ✅ EOD flat successful

**No-Go if:**
- ❌ Risk limits breached
- ❌ EOD flat incomplete
- ❌ Critical errors

### Gate 3: Day-2 Full Session
**Go if:**
- ✅ All daily requirements met
- ✅ Consistent performance
- ✅ No new issues discovered

**No-Go if:**
- ❌ New issues discovered
- ❌ Performance degradation
- ❌ Data integrity issues

### Gate 4: Day-3 Full Session
**Go if:**
- ✅ All daily requirements met
- ✅ 3/3 days passed
- ✅ All failure drills completed

**No-Go if:**
- ❌ Any day failed
- ❌ Failure drills incomplete

---

## Failure Drills (Before LIVE)

**Run once before enabling LIVE mode:**

### 1. Redis Failure
```bash
# Kill Redis
docker compose stop redis

# Verify: API continues, events queue resumes
curl localhost:8000/health

# Restart Redis
docker compose start redis
```

### 2. WebSocket Drop
```bash
# Simulate: Disable network for 30s
# Verify: Reconnect + resubscribe, no duplicate children
# Check logs for reconnection messages
```

### 3. Order Rejection
```bash
# Force LIMIT rejection (stale price)
# Verify: Retry bounded, idempotency holds
# Check DB for single order entry
```

### 4. Wide Spreads
```bash
# Simulate: Wide spreads > threshold
# Verify: Risk block triggers, no new entries
# Check risk events in DB
```

---

## LIVE Gate

**When 3/3 paper days pass:**

```bash
curl -X POST localhost:8000/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"LIVE","confirm":"CONFIRM LIVE TRADING"}' | jq
```

### Day-1 LIVE Configuration

**Conservative Caps:**
- Per-trade risk: 0.25%
- Portfolio heat: 1.0%
- Daily loss stop: 1.0%

**Monitoring:**
- Keep dashboard visible
- Monitor `/risk` endpoint
- Be ready to press kill switch

---

## Rollback Procedure

**If issues occur in LIVE mode:**

```bash
# 1. Pause trading
curl -X POST localhost:8000/pause

# 2. Flatten all positions
curl -X POST localhost:8000/flatten

# 3. Switch to PAPER
curl -X POST localhost:8000/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"PAPER"}'

# 4. Restart API
# (Kill process and restart)
```

**Script:** `scripts/rollback.sh`

---

## Dashboard MVP Requirements

**Priority 1 (Must Have):**
- Top Ranks with score attribution (momentum, trend, liquidity, regime, RR)
- Positions (qty, avg, SL/TP, U/R P&L)
- Portfolio Heat gauge
- Daily P&L
- Kill Switch button (calls `/flatten`)

**Priority 2 (Should Have):**
- Events feed (risk blocks, rejects, OCO closes)
- Real-time metrics
- Risk status

**Socket Channels:**
- `signals` - New signals
- `decisions` - Risk-checked decisions
- `orders` - Order updates
- `risk` - Risk state changes
- `events` - General events

---

## Post-Trade Reconciliation

**Run after each session:**

```bash
psql $DATABASE_URL -f scripts/reconcile_db.sql
```

**Key Checks:**
1. No orphan OCO siblings
2. No duplicate `client_order_id`
3. Complete audit trail
4. All positions have OCO groups
5. Risk events logged

---

## Success Criteria Summary

**3-Day Burn-In Passes If:**
- ✅ All 3 days meet daily requirements
- ✅ No critical errors
- ✅ All failure drills pass
- ✅ Data integrity maintained
- ✅ Risk limits respected
- ✅ EOD flat successful

**Then:** Enable LIVE mode with conservative caps.

---

## Next Steps After LIVE

1. Monitor closely for first week
2. Gradually increase caps if performance stable
3. Review daily reports
4. Adjust strategy parameters based on results
5. Scale up position sizes cautiously

