# 🚀 LIVE Switch Runbook (15 minutes)

## Pre-Switch (Before 09:10 IST)

### 1. Freeze Config (1 min)

```bash
# Commit current state
git add -A
git commit -am "canary-live $(date +%Y-%m-%d)"

# Note config SHA
CONFIG_SHA=$(python -c 'from packages.core.config import app_config; print(getattr(app_config, "config_sha", "unknown"))')
echo "Config SHA: $CONFIG_SHA" > runbook_$(date +%Y-%m-%d).txt

# Load canary config
cp configs/canary_live.yaml configs/app.yaml
```

**Record in runbook:**
- Config SHA: `$CONFIG_SHA`
- Git SHA: `$(git rev-parse HEAD)`
- Timestamp: `$(date -u +%Y-%m-%dT%H:%M:%SZ)`

---

### 2. Pre-Flight (2 min)

```bash
# Verify environment
make verify

# Start infrastructure
docker compose up -d postgres redis
sleep 5

# Migrate DB
alembic upgrade head

# Start in PAPER mode
make paper
sleep 10
```

**Check Gauges:**
```bash
curl -s localhost:8000/metrics | grep -E '^trader_(is_leader|marketdata_heartbeat|order_stream_heartbeat|positions_open|portfolio_heat_rupees)'
```

**Expected:**
- `trader_is_leader{instance_id="..."} 1`
- `trader_marketdata_heartbeat_seconds{bucket="..."} < 5`
- `trader_order_stream_heartbeat_seconds < 5`
- `trader_positions_open{strategy="..."} 0`
- `trader_portfolio_heat_rupees 0`

---

### 3. Warm Safety & Recovery (2 min)

```bash
# Ensure PAPER mode
curl -s -X POST localhost:8000/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"PAPER"}' | jq

# Check logs for recovery
tail -20 logs/aitrapp.log | grep -i "recover\|recovering"

# Expected: "Recovering 0 open positions" or "No open positions to recover"

# Test flatten (sanity check)
START=$(date +%s)
curl -s -X POST localhost:8000/flatten \
  -H "Content-Type: application/json" \
  -d '{"reason":"prelive_sanity"}' | jq
END=$(date +%s)
DURATION=$((END - START))

echo "Flatten duration: ${DURATION}s"
# Must be ≤ 2s

# Verify zero positions
curl -s localhost:8000/positions | jq '.count'
# Must be 0
```

---

## Switch to LIVE (09:10 IST)

### 4. Flip to LIVE

```bash
curl -s -X POST localhost:8000/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"LIVE","confirm":"CONFIRM LIVE TRADING"}' | jq
```

**Verify:**
- Response: `{"status": "LIVE", ...}`
- Logs: `"Mode switched to LIVE"`
- Metric: `trader_is_leader{instance_id="..."} 1`

**Keep Open:**
- Dashboard: `http://localhost:3000` (or your dashboard URL)
- Metrics: `watch -n 5 'curl -s localhost:8000/metrics | grep trader_'`
- Logs: `tail -f logs/aitrapp.log | jq`

---

## First 60 Minutes Monitoring

### 5. Watch These 5 Signals

**Continuous Monitoring:**
```bash
watch -n 5 'curl -s localhost:8000/metrics | grep -E "trader_(order_latency_ms|portfolio_heat_rupees|retries_total|marketdata_heartbeat_seconds|kill_switch_total)"'
```

**Expected Behavior:**

1. **`trader_order_latency_ms`**
   - ✅ P95 < 500ms
   - ❌ P95 > 800ms for 2m → **PAUSE → FLATTEN(reason="latency")**

2. **`trader_portfolio_heat_rupees`**
   - ✅ Well below cap (1.0% = ₹X for your capital)
   - ❌ > cap → **AUTO FLATTEN(reason="risk_cap")**

3. **`trader_retries_total`**
   - ✅ Flat (esp. `token_refresh`, `rate_limit`)
   - ❌ Rising → Check logs for API issues

4. **`trader_marketdata_heartbeat_seconds`**
   - ✅ < 5s
   - ❌ > 5s → WebSocket issue, check reconnects

5. **`trader_kill_switch_total`**
   - ✅ Stays flat (unless you test it)
   - ❌ Increments → Review reason

---

## Immediate Flatten Triggers (Decision Table)

| Condition | Action |
|-----------|--------|
| Order acks p95 > 800ms for 2m | **PAUSE → FLATTEN(reason="latency")** |
| Leader lock drops to 0 for >10s | **AUTO-PAUSE & EXIT** (already wired) |
| Rate-limit queue depth rising for 60s | **PAUSE ENTRIES** (let exits complete) |
| Spread blowouts or band rejections > 3 in 1m | **PAUSE → FLATTEN(reason="market_quality")** |
| Daily loss hits cap or heat > cap | **AUTO FLATTEN(reason="risk_cap")** (already wired) |

**Flatten Command:**
```bash
curl -X POST localhost:8000/flatten \
  -H "Content-Type: application/json" \
  -d '{"reason":"latency"}'  # or "market_quality", "risk_cap"
```

**Pause Command:**
```bash
curl -X POST localhost:8000/pause
```

---

## Burn-In Checklist (Paper, 3 Sessions)

**Must Pass Before LIVE:**

- [ ] `/flatten` p95 ≤ 2s under live ticks
- [ ] No duplicate `client_order_id` (check DB)
- [ ] No orphan OCO siblings post-exit (run `scripts/reconcile_db.sql`)
- [ ] EOD tighten at 15:20, hard-flat at 15:25
- [ ] Daily report + DB reconcile clean

**Check Duplicates:**
```sql
SELECT client_order_id, COUNT(*) 
FROM orders 
GROUP BY client_order_id 
HAVING COUNT(*) > 1;
```

**Check Orphans:**
```sql
-- Run scripts/reconcile_db.sql
```

---

## Post-Close Ritual

```bash
# Run post-close hygiene
make post-close

# Reconcile DB
psql $DATABASE_URL -f scripts/reconcile_db.sql

# Tag release
git tag burnin-$(date +%Y-%m-%d)
git push --tags
```

---

## Fast FAQ (When Something "Doesn't Trade")

### Risk Gate Blocked?
```bash
curl localhost:8000/risk | jq
curl -s localhost:8000/metrics | grep trader_risk_blocks_total
```

### Spread/Band Fail?
```bash
# Check events for FREEZE_BAND
grep -i "FREEZE_BAND\|SPREAD_BLOWOUT" logs/aitrapp.log | tail -20
```

### Duplicate Dedupe?
- Same `plan_client_id` seen recently
- Check: `SELECT * FROM orders WHERE client_order_id = '...'`

### Leader Not 1?
- Another instance running
- Lock prevented entries
- Check: `curl -s localhost:8000/metrics | grep trader_is_leader`

---

## Success Criteria

**First Hour Passes If:**
- ✅ No kill switch triggered
- ✅ Heat stays within limits
- ✅ Orders execute successfully
- ✅ OCO children place correctly
- ✅ No duplicate orders
- ✅ No orphan siblings
- ✅ Metrics tracking correctly
- ✅ Latency < 500ms p95

**Then:** Continue monitoring, gradually increase caps if stable.

---

## Emergency Rollback

```bash
# Pause
curl -X POST localhost:8000/pause

# Flatten
curl -X POST localhost:8000/flatten -d '{"reason":"rollback"}'

# Switch to PAPER
curl -X POST localhost:8000/mode -d '{"mode":"PAPER"}'

# Review logs
tail -100 logs/aitrapp.log | jq
```

---

**You're ready. Flip the switch at 09:10 IST. 🚀**

