# Day-1 PAPER Burn-In Log

**Date:** $(date +%Y-%m-%d)  
**Session:** PAPER Day-1  
**Mode:** Simulation Only

## Pre-Open Checks

- [x] Infrastructure up (Postgres, Redis)
- [x] API started and healthy
- [x] Leader lock acquired
- [x] All heartbeats < 5s
- [x] Supervisor running

## Session Monitoring

### Five Gauges (Target: Green All Session)

- [ ] `trader_is_leader == 1` (all session)
- [ ] `trader_marketdata_heartbeat_seconds < 5` (all session)
- [ ] `trader_order_stream_heartbeat_seconds < 5` (all session)
- [ ] `trader_scan_heartbeat_seconds < 5` (all session)
- [ ] `trader_scan_ticks_total` rising (all session)

### OCO Lifecycle Test

- [ ] Synthetic plan injected
- [ ] Orders placed (`trader_orders_placed_total > 0`)
- [ ] OCO children created (`trader_oco_children_created_total > 0`)
- [ ] `/flatten` completed ≤ 2s
- [ ] Positions → 0 after flatten

### Tripwires (None Fired)

- [ ] No heartbeat > 5s for >1 min
- [ ] No order-ack p95 > 500 ms for >1 min
- [ ] No throttle queue depth issues
- [ ] No duplicate client_order_id
- [ ] No orphan OCO children

## End-of-Day

- [ ] Burn-in report generated
- [ ] Database reconciliation: **0 duplicates, 0 orphans**
- [ ] Post-close hygiene completed
- [ ] No alerts fired

## Verdict

**Status:** [ ] PASS / [ ] FAIL

**Notes:**
- Leader lock: [ ] 1 all session
- Heartbeats: [ ] <5s all session
- OCO lifecycle: [ ] PASS
- `/flatten` ≤2s: [ ] PASS
- Reconcile (dups/orphans): [ ] 0 / 0
- Alerts: [ ] none

---

**Completed:** $(date)  
**Next:** Day-2 burn-in (if PASS)

