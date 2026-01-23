# First Hour LIVE Monitoring Guide

## 🎯 What to Watch

### Key Metrics (Tail Continuously)

```bash
watch -n 5 'curl -s localhost:8000/metrics | grep -E "trader_(orders_placed_total|retries_total|portfolio_heat_rupees|order_latency_ms)"'
```

### Expected Behavior

1. **`trader_orders_placed_total`**
   - ✅ Rises slowly (no bursts)
   - ❌ Burst of orders = problem

2. **`trader_retries_total`**
   - ✅ ~0 (or very low)
   - ❌ High retries = API issues

3. **`trader_portfolio_heat_rupees`**
   - ✅ Well below cap (1.0% = ₹X for your capital)
   - ❌ Approaching cap = risk issue

4. **`trader_order_latency_ms`**
   - ✅ P95 < 500ms
   - ❌ P95 > 500ms = broker latency

### Event Feed (Dashboard)

Watch for:
- ❌ `FREEZE_BAND` events
- ❌ `SPREAD_BLOWOUT` spam
- ✅ Normal signal/decision flow

---

## 🚨 If Something Smells Off

### Immediate Actions

1. **Pause:**
   ```bash
   curl -X POST localhost:8000/pause
   ```

2. **Flatten:**
   ```bash
   curl -X POST localhost:8000/flatten
   ```

3. **Switch to PAPER:**
   ```bash
   curl -X POST localhost:8000/mode \
     -H "Content-Type: application/json" \
     -d '{"mode":"PAPER"}'
   ```

### Investigation

1. **Reconcile DB:**
   ```bash
   psql $DATABASE_URL -f scripts/reconcile_db.sql
   ```

2. **Check Audit Logs:**
   ```sql
   SELECT * FROM audit_logs 
   ORDER BY ts DESC 
   LIMIT 100;
   ```

3. **Prometheus Time-Series:**
   ```bash
   # Check metrics around incident time
   curl -s localhost:8000/metrics | grep trader_
   ```

---

## 📊 Dashboard Tiles

### Must-Have Views

1. **Top Ranks** - Verify attribution makes sense
2. **Positions** - SL/TP, U/R P&L
3. **Portfolio Heat** - Must stay ≤ 1.0%
4. **Daily P&L** - Monitor continuously
5. **Event Feed** - Risk blocks, rejects, OCO closes
6. **Kill Switch** - Big red button

---

## ✅ Success Criteria

**First Hour Passes If:**
- ✅ No kill switch triggered
- ✅ Heat stays within limits
- ✅ Orders execute successfully
- ✅ OCO children place correctly
- ✅ No duplicate orders
- ✅ No orphan siblings
- ✅ Metrics tracking correctly
- ✅ No `FREEZE_BAND` or `SPREAD_BLOWOUT` spam

**Then:** Continue monitoring, gradually increase caps if stable.

