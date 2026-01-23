# First Hour LIVE Playbook

## 🎯 Objective

Safely transition from PAPER to LIVE mode and monitor the first hour of live trading.

---

## Pre-Flight (09:00 IST)

### Checklist
- [ ] All 3 burn-in days passed
- [ ] All failure drills completed
- [ ] Leader lock working
- [ ] Kill switch tested
- [ ] Dashboard visible
- [ ] Metrics endpoint accessible
- [ ] `.env` has valid `KITE_*` tokens (no expiry during session)

### Start in PAPER
```bash
make paper
```

### Monitor Stability (09:00 - 09:05)
- Watch logs: `tail -f logs/aitrapp.log | jq`
- Check metrics: `curl localhost:8000/metrics | grep trader_`
- Verify no errors
- Confirm leader lock acquired

---

## Transition to LIVE (09:10 IST)

### Switch Mode
```bash
curl -X POST localhost:8000/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"LIVE","confirm":"CONFIRM LIVE TRADING"}' | jq
```

### Conservative Caps (Day-1 LIVE)
- **Per-trade risk:** 0.25%
- **Portfolio heat:** 1.0%
- **Daily loss stop:** 1.0%

**Update config:**
```yaml
risk:
  per_trade_risk_pct: 0.25
  max_portfolio_heat_pct: 1.0
  daily_loss_stop_pct: 1.0
```

---

## First Hour Monitoring (09:10 - 10:10 IST)

### Dashboard Tiles to Watch

1. **Portfolio Heat**
   - Must stay ≤ 1.0%
   - Alert if > 0.8%

2. **Daily P&L**
   - Monitor continuously
   - Alert if approaching -1.0%

3. **Top Ranks**
   - Verify attribution makes sense
   - Check feature scores

4. **Positions**
   - Monitor SL/TP levels
   - Watch U/R P&L

5. **Event Feed**
   - Watch for risk blocks
   - Monitor order rejects
   - Check OCO closes

### Metrics to Tail
```bash
watch -n 5 'curl -s localhost:8000/metrics | grep -E "trader_(portfolio_heat|daily_pnl|orders_placed|orders_filled|retries)"'
```

### Kill Switch Triggers

**Press Kill if:**
- ❌ Portfolio heat > cap (1.0%)
- ❌ Spreads blow out (> threshold)
- ❌ Retries spike (> 50 in 10 min)
- ❌ Order acks lag (> 500ms P95)
- ❌ Any unexpected behavior

**Kill Procedure:**
```bash
curl -X POST localhost:8000/flatten
```

---

## Hour-by-Hour Checklist

### 09:10 - 09:20 (First 10 minutes)
- [ ] Mode switched to LIVE
- [ ] First signal generated
- [ ] First decision made
- [ ] First order placed (if approved)
- [ ] No errors in logs
- [ ] Metrics incrementing

### 09:20 - 09:40 (Next 20 minutes)
- [ ] Multiple signals generated
- [ ] Risk checks working
- [ ] Orders executing
- [ ] OCO children placed
- [ ] Portfolio heat stable
- [ ] No retries spike

### 09:40 - 10:10 (Final 30 minutes)
- [ ] System stable
- [ ] No anomalies
- [ ] Heat within limits
- [ ] P&L tracking correctly
- [ ] All positions have SL/TP

---

## Post-First-Hour

### Review
- [ ] Check all positions
- [ ] Verify OCO groups
- [ ] Review risk events
- [ ] Check order latency
- [ ] Validate P&L

### Adjustments
- If stable: consider gradual cap increases
- If issues: revert to PAPER, investigate

---

## Emergency Procedures

### If Kill Switch Pressed
1. System flattens all positions
2. Trading paused
3. Review logs
4. Investigate root cause
5. Fix issue
6. Re-run Day-0 before re-enabling LIVE

### If Heat Limit Breached
1. System auto-pauses
2. Review positions
3. Check risk calculations
4. Manually flatten if needed
5. Adjust caps if necessary

### If Daily Loss Stop Hit
1. System auto-pauses
2. Review trades
3. Analyze losses
4. Adjust strategy if needed
5. Re-run burn-in if major issues

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

**Then:** Continue monitoring, gradually increase caps if stable.

---

## Notes

- Keep dashboard visible at all times
- Have kill switch ready
- Monitor metrics continuously
- Review logs periodically
- Be ready to rollback if needed

**Remember:** First hour is critical. Stay vigilant.

