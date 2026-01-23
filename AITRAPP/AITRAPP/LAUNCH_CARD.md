# 🚀 LIVE Launch Card - Keep By Keyboard

**Print this and keep it visible during the first LIVE hour.**

---

## ⚡ 10-Second Pre-Switch Sanity (Before 09:10 IST)

```bash
# Quick check
curl -s localhost:8000/metrics | grep -E 'trader_is_leader|trader_.*heartbeat' | sort
# Must show: trader_is_leader 1, both heartbeats < 5s

# Dry flatten test
time curl -s -X POST localhost:8000/flatten -d '{"reason":"prelive_sanity"}' | jq
# Must be ≤ 2s

# Zero positions
curl -s localhost:8000/positions | jq '.count'
# Must be 0

# Reconcile DB
psql $DATABASE_URL -f scripts/reconcile_db.sql
# Must show: no dup client IDs, no orphan OCOs

# Canary config check
grep -E 'per_trade_risk_pct|max_portfolio_heat_pct|fo_stocks_liquidity_rank_top_n' configs/app.yaml
# Must show: 0.25%, 1.0%, 0 (indices only)
```

**✅ All green? Proceed to LIVE switch.**

---

## 🚨 Instant Abort Macro (Paste if anything smells off)

```bash
pause && killnow && paper
```

**Or use alias:**
```bash
abort
```

---

## 🚨 Tripwires (Flatten on Sight)

| Condition | Action |
|-----------|--------|
| Order-ack p95 > 800ms for 2 minutes | **FLATTEN(reason="latency")** |
| Leader lock drops | **AUTO-EXIT** (should trigger automatically) |
| Rate-limit queue depth climbing for 60s | **PAUSE ENTRIES** (let exits complete) |
| Repeated FREEZE_BAND/SPREAD_BLOWOUT events | **FLATTEN(reason="market_quality")** |
| Daily loss/heat hits cap | **AUTO-FLATTEN(reason="risk_cap")** |

**Flatten Command:**
```bash
killnow  # or: curl -X POST localhost:8000/flatten -d '{"reason":"latency"}'
```

---

## ✅ After First Clean Hour (If All Green)

### Option 1: Keep Conservative
- Keep indices only for the day
- Monitor closely

### Option 2: Widen Scope
```bash
# Edit configs/app.yaml
vim configs/app.yaml
# Change: fo_stocks_liquidity_rank_top_n: 10  # Top 10 F&O stocks
# Restart API
```

### Option 3: Bump Caps (If Very Stable)
```bash
# Edit configs/app.yaml
vim configs/app.yaml
# Change:
#   per_trade_risk_pct: 0.30
#   max_portfolio_heat_pct: 1.2
# Restart API
```

### Post-Close
```bash
make post-close
psql $DATABASE_URL -f scripts/reconcile_db.sql
git tag burnin-$(date +%Y-%m-%d)
```

---

## 📊 Quick Commands

```bash
# Dashboard
make live-dashboard
tmux attach -t live

# Switch to LIVE
make live-switch  # or: live

# Emergency
abort  # or: pause && killnow && paper

# Quick checks
state    # System state
risk     # Risk status
positions  # Open positions
metrics  # All metrics
```

---

## 🎯 Week-1 Mini Backlog (Non-Blocking, High ROI)

### 1. Risk Banner on Dashboard
- Add visual indicator: ≥75% heat → header turns red
- Location: Dashboard header/top bar
- Update: Real-time from `trader_portfolio_heat_rupees`

### 2. Session Tagging
- Log `SESSION=YYYY-MM-DD-LIVE-CANARY` into every audit row
- Makes forensics trivial
- Update: `packages/core/persistence.py` → add session_id to all audit logs

### 3. Slippage & Latency Persistence
- Persist per-trade slippage & latency
- Auto-update slippage model daily
- Update: `packages/core/execution.py` → record slippage, `packages/storage/models.py` → add slippage field

### 4. NSE Holiday/Event Calendar
- Auto-fetch at 08:00 IST
- Wire placeholder in `packages/core/market_hours.py`
- Update: Add `fetch_nse_calendar()` function, schedule daily fetch

---

## 📋 First Hour Checklist

- [ ] Pre-switch sanity passed
- [ ] Dashboard visible (tmux)
- [ ] Switched to LIVE at 09:10 IST
- [ ] Monitoring key metrics
- [ ] No tripwires triggered
- [ ] All positions have SL/TP
- [ ] Heat stays within limits
- [ ] Latency < 500ms p95
- [ ] No duplicate orders
- [ ] No orphan OCO siblings

---

## 🆘 Emergency Contacts

**Kill Switch:** `abort` or `killnow`  
**Rollback:** `make rollback`  
**Logs:** `tail -f logs/aitrapp.log | jq`  
**Metrics:** `curl localhost:8000/metrics | grep trader_`  
**Incident Snapshots:** `ls -lt reports/incidents/`

---

**Keep this card visible. Stay vigilant. Safe trading! 🚀**

