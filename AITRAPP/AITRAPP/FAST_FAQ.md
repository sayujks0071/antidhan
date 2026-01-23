# 🚨 Fast FAQ - When Something "Doesn't Trade"

## Quick Diagnostics

### Risk Gate Blocked?

**Check:**
```bash
curl localhost:8000/risk | jq
curl -s localhost:8000/metrics | grep trader_risk_blocks_total
```

**Common Reasons:**
- Per-trade risk cap exceeded
- Portfolio heat at limit
- Daily loss stop hit
- Freeze quantity exceeded

**Fix:**
- Review risk config: `configs/app.yaml` → `risk:`
- Check current positions: `curl localhost:8000/positions | jq`
- Reset daily loss if needed (requires restart)

---

### Spread/Band Fail?

**Check:**
```bash
# Check events for FREEZE_BAND
grep -i "FREEZE_BAND\|SPREAD_BLOWOUT" logs/aitrapp.log | tail -20

# Check metrics
curl -s localhost:8000/metrics | grep trader_risk_blocks_total
```

**Common Reasons:**
- Spread > `max_spread_mid_pct` threshold
- Price outside freeze bands
- Circuit limit hit

**Fix:**
- Widen `max_spread_mid_pct` in config (if market conditions justify)
- Check instrument freeze bands: `curl localhost:8000/instruments | jq`
- Wait for better liquidity

---

### Duplicate Dedupe?

**Check:**
```sql
-- Check for duplicate client_order_ids
SELECT client_order_id, COUNT(*) 
FROM orders 
GROUP BY client_order_id 
HAVING COUNT(*) > 1;
```

**Common Reasons:**
- Same `plan_client_id` seen recently
- Idempotency check failed
- OrderWatcher replay

**Fix:**
- Check idempotency logic: `packages/core/execution.py` → `plan_client_id()`
- Review OrderWatcher logs: `grep -i "replay\|duplicate" logs/aitrapp.log`
- Verify single-flight guard in OCO: `packages/core/oco.py` → `on_entry_fill()`

---

### Leader Not 1?

**Check:**
```bash
curl -s localhost:8000/metrics | grep trader_is_leader
```

**Expected:** `trader_is_leader{instance_id="..."} 1`

**Common Reasons:**
- Another instance running
- Leader lock expired
- Redis connection lost

**Fix:**
- Check for other processes: `ps aux | grep uvicorn`
- Check Redis: `docker compose ps redis`
- Review leader lock logs: `grep -i "leader" logs/aitrapp.log`

---

### No Signals Generated?

**Check:**
```bash
curl -s localhost:8000/metrics | grep trader_signals_total
```

**Common Reasons:**
- Strategies disabled in config
- Universe empty (no instruments)
- Market data not streaming
- All signals filtered by ranker

**Fix:**
- Check strategies: `configs/app.yaml` → `strategies:`
- Check universe: `curl localhost:8000/universe | jq`
- Check market data: `curl -s localhost:8000/metrics | grep trader_marketdata_heartbeat_seconds`
- Review ranker thresholds: `configs/app.yaml` → `ranking:`

---

### Orders Not Placing?

**Check:**
```bash
# Check order metrics
curl -s localhost:8000/metrics | grep trader_orders_placed_total

# Check recent orders
curl localhost:8000/orders | jq '.orders[:10]'

# Check for errors
grep -i "error\|failed\|reject" logs/aitrapp.log | tail -20
```

**Common Reasons:**
- Token expired (401/403)
- Rate limit hit
- Insufficient margin
- Market closed
- Invalid price/quantity

**Fix:**
- Check token: `curl localhost:8000/health | jq`
- Check rate limits: `curl -s localhost:8000/metrics | grep trader_throttle_queue_depth`
- Check margin: Broker dashboard
- Verify market hours: `packages/core/market_hours.py`
- Review price validation: `packages/core/price_utils.py`

---

### OCO Children Not Placing?

**Check:**
```bash
# Check OCO metrics
curl -s localhost:8000/metrics | grep trader_oco_children_created_total

# Check positions
curl localhost:8000/positions | jq '.positions[] | {position_id, oco_group, status}'

# Check logs
grep -i "oco\|stop\|tp" logs/aitrapp.log | tail -20
```

**Common Reasons:**
- Entry not filled yet
- Single-flight guard preventing duplicate
- OrderWatcher not running
- OCO manager error

**Fix:**
- Check entry order status: `curl localhost:8000/orders | jq '.orders[] | select(.tag=="ENTRY")'`
- Review OCO logs: `grep -i "on_entry_fill\|single-flight" logs/aitrapp.log`
- Check OrderWatcher: `curl localhost:8000/health | jq`
- Review OCO manager: `packages/core/oco.py`

---

### High Latency?

**Check:**
```bash
# Order latency
curl -s localhost:8000/metrics | grep trader_order_latency_ms

# Tick to decision latency
curl -s localhost:8000/metrics | grep trader_tick_to_decision_ms
```

**Common Reasons:**
- Broker API slow
- Network issues
- High load
- WebSocket lag

**Fix:**
- Check broker status: Broker dashboard
- Check network: `ping broker-api-url`
- Reduce scan frequency: `configs/app.yaml` → `scan_interval_seconds`
- Check WebSocket: `curl -s localhost:8000/metrics | grep trader_marketdata_heartbeat_seconds`

---

### Kill Switch Triggered?

**Check:**
```bash
curl -s localhost:8000/metrics | grep trader_kill_switch_total

# Check audit logs
psql $DATABASE_URL -c "SELECT * FROM audit_logs WHERE action = 'KILL_SWITCH' ORDER BY ts DESC LIMIT 5;"
```

**Common Reasons:**
- Manual activation
- Risk cap breach
- EOD auto-flatten
- System error

**Fix:**
- Review reason in audit log
- Check risk state: `curl localhost:8000/risk | jq`
- Resume if needed: `curl -X POST localhost:8000/resume`
- Switch to PAPER if issues: `curl -X POST localhost:8000/mode -d '{"mode":"PAPER"}'`

---

## Emergency Commands

```bash
# Pause trading
curl -X POST localhost:8000/pause

# Flatten all positions
curl -X POST localhost:8000/flatten -d '{"reason":"emergency"}'

# Switch to PAPER
curl -X POST localhost:8000/mode -d '{"mode":"PAPER"}'

# Check health
curl localhost:8000/health | jq

# View recent logs
tail -50 logs/aitrapp.log | jq
```

---

## Still Stuck?

1. **Check incident snapshot:**
   ```bash
   ls -lt reports/incident-* | head -1
   ```

2. **Review audit logs:**
   ```sql
   SELECT * FROM audit_logs ORDER BY ts DESC LIMIT 100;
   ```

3. **Check Prometheus:**
   ```bash
   curl -s localhost:8000/metrics | grep trader_ | head -50
   ```

4. **Review runbook:** `LIVE_SWITCH_RUNBOOK.md`

