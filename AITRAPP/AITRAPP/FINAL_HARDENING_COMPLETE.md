# ✅ Final Pre-LIVE Hardening Complete

## 🛡️ All Hardening Patches Applied

### 1. Leader-Lock Watchdog ✅
- **Metric:** `trader_is_leader{instance_id=...}` (0|1)
- **Alert:** Drops to 0 for >10s
- **Integration:** Updated in `_refresh_leader_lock()`

### 2. Token Expiry Guard ✅
- **401/403 Detector:** Wraps all Kite REST calls
- **Auto-Rotate:** Token refresh callback support
- **Metric:** `trader_retries_total{type="token_refresh"}`
- **File:** `packages/core/kite_client.py`

### 3. Rate-Limit Throttle ✅
- **Leaky Bucket:** Per-second and per-minute limits
- **Metric:** `trader_throttle_queue_depth{type=...}`
- **File:** `packages/core/rate_limiter.py`

### 4. Freeze-Qty/Price-Band Check ✅
- **Pre-Broker Validation:** Fail-fast before sending
- **Price Utils:** `clamp_price()`, `within_band()`, `validate_order_price()`
- **Risk Event:** `FREEZE_BAND` on violation
- **File:** `packages/core/price_utils.py`

### 5. Heartbeat Monitors ✅
- **Market Data:** `trader_marketdata_heartbeat_seconds{bucket=...}`
- **Order Stream:** `trader_order_stream_heartbeat_seconds`
- **Alert:** >5s during market hours
- **Metrics:** Added to `packages/core/metrics.py`

### 6. Warm Restart Safety ✅
- **Boot Sequence:** Set `mode=PAPER` → recover positions → allow LIVE
- **Documentation:** Added to `lifespan()` docstring
- **File:** `apps/api/main.py`

### 7. Canary LIVE Profile ✅
- **Config:** `configs/canary_live.yaml`
- **Conservative Caps:** 0.25% per-trade, 1.0% heat, 1.0% daily loss
- **Indices Only:** No F&O stocks for day-1

### 8. Operational SLOs ✅
- **Alerts:** `ops/slo_alerts.yml`
- **SLOs:**
  - Kill-flatten p95 ≤ 2s
  - Order ack p95 ≤ 500ms
  - No duplicate client IDs
  - Zero orphan OCO siblings
  - Heat guard: ≤ 2% of NL

### 9. Failure Drills ✅
- **Script:** `scripts/failure_drills.sh`
- **Tests:**
  - Dual-runner attempt
  - WS flap during child placement
  - Exchange band jump
- **Makefile:** `make failure-drills`

### 10. Post-Close Hygiene ✅
- **Script:** `scripts/post_close_hygiene.sh`
- **Actions:**
  - DB snapshot
  - Tar logs + report
  - Record config SHA, git SHA, metrics
  - Token rotation check
- **Makefile:** `make post-close`

### 11. Single-Flight Child Placement ✅
- **Guard:** Prevents duplicate SL/TP if OrderWatcher replays
- **Check:** `order_exists()` before placing children
- **File:** `packages/core/oco.py` → `on_entry_fill()`

### 12. Kill-Switch Metric ✅
- **Metric:** `trader_kill_switch_total{reason=...}`
- **Reasons:** `manual|eod|risk`
- **Audit Log:** Records reason + open risk
- **Files:** `packages/core/orchestrator.py`, `apps/api/main.py`

---

## 📋 Quick Reference

### Pre-Flight
```bash
alembic upgrade head
make verify
make smoke-test
make red-team-drills
make failure-drills
```

### Canary LIVE Config
```bash
# Use canary config for first hour
cp configs/canary_live.yaml configs/app.yaml
# Or load via API
```

### First Hour Monitoring
- See `FIRST_HOUR_MONITORING.md`
- Watch metrics: `trader_orders_placed_total`, `trader_retries_total`, `trader_portfolio_heat_rupees`
- Alert on: `FREEZE_BAND`, `SPREAD_BLOWOUT` spam

### Post-Close
```bash
make post-close
```

---

## 🎯 Operational SLOs

| SLO | Target | Alert |
|-----|--------|-------|
| Kill-flatten time | p95 ≤ 2s | `KillFlattenSLOBreach` |
| Order ack latency | p95 ≤ 500ms | `OrderAckLatencySLOBreach` |
| Duplicate client IDs | 0 | `DuplicateClientIDs` |
| Orphan OCO siblings | 0 | `OrphanOCOSiblings` |
| Portfolio heat | ≤ 2% of NL | `HeatGuardBreach` |
| Leader lock | Always 1 | `LeaderLockLost` |
| Market data heartbeat | ≤ 5s | `MarketDataHeartbeatStale` |
| Order stream heartbeat | ≤ 5s | `OrderStreamHeartbeatStale` |

---

## 🚀 Ready for LIVE

**All hardening complete. System is production-ready.**

**Next Steps:**
1. Run pre-flight checklist
2. Execute all drills
3. Complete 3-day burn-in
4. Load canary config
5. Enable LIVE mode
6. Monitor first hour closely

**See `FIRST_HOUR_LIVE_PLAYBOOK.md` for detailed procedure.**

