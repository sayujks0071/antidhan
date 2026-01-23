# 🚀 LIVE Switch Quick Reference Card

**Print this and keep it handy during the LIVE switch.**

---

## ⏰ Timeline

- **09:00** - Pre-flight checks
- **09:05** - Start in PAPER, verify stability
- **09:10** - Switch to LIVE
- **09:10-10:10** - Monitor first hour
- **15:30** - Post-close ritual

---

## ✅ Pre-Flight (5 min)

```bash
# 1. Freeze config
git commit -am "canary-live $(date +%Y-%m-%d)"
cp configs/canary_live.yaml configs/app.yaml

# 2. Verify & start
make verify
docker compose up -d postgres redis
alembic upgrade head
make paper

# 3. Canary pre-check (30 sec)
./ops/canary_precheck.sh

# 4. Create tmux dashboard (optional)
./ops/live.sh dashboard
tmux attach -t live
```

---

## 🔄 Switch to LIVE (09:10 IST)

### Option 1: Using ops script
```bash
./ops/live.sh switch
```

### Option 2: Using alias (if loaded)
```bash
live
```

### Option 3: Manual
```bash
curl -X POST localhost:8000/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"LIVE","confirm":"CONFIRM LIVE TRADING"}' | jq
```

**Verify:**
- Response: `{"status": "LIVE"}`
- Metric: `trader_is_leader{instance_id="..."} 1`

---

## 👀 Monitor First Hour

### Option 1: Tmux Dashboard (Recommended)
```bash
./ops/live.sh dashboard
tmux attach -t live
```

**5 Panes:**
1. Key metrics (top-left)
2. Positions/Heat/P&L (top-right)
3. Redis event feed (bottom-right)
4. Audit log tail (bottom-left)
5. Risk caps (bottom-center)

### Option 2: Manual Watch
```bash
watch -n 5 'curl -s localhost:8000/metrics | grep -E "trader_(order_latency_ms|portfolio_heat_rupees|retries_total|marketdata_heartbeat_seconds|kill_switch_total)"'
```

**Watch These 5:**
1. `trader_order_latency_ms` p95 < 500ms ✅
2. `trader_portfolio_heat_rupees` << cap ✅
3. `trader_retries_total` flat ✅
4. `trader_marketdata_heartbeat_seconds` < 5 ✅
5. `trader_kill_switch_total` flat ✅

---

## 🚨 Emergency Commands

### Quick Aliases (source `ops/aliases.sh`)
```bash
killnow    # Flatten all positions
pause      # Pause trading
resume     # Resume trading
live       # Switch to LIVE
paper      # Switch to PAPER
abort      # Pause + Flatten + PAPER (immediate abort)
```

### Manual Commands
```bash
# Pause
curl -X POST localhost:8000/pause

# Flatten (Kill Switch)
curl -X POST localhost:8000/flatten -d '{"reason":"latency"}'  # or "market_quality", "risk_cap"

# Rollback to PAPER
./ops/abort.sh  # Or use: abort (if aliases loaded)
```

---

## 🚨 Immediate Flatten Triggers

| Condition | Action |
|-----------|--------|
| Order acks p95 > 800ms for 2m | **PAUSE → FLATTEN(reason="latency")** |
| Leader lock drops to 0 for >10s | **AUTO-PAUSE & EXIT** |
| Rate-limit queue depth rising for 60s | **PAUSE ENTRIES** |
| Spread blowouts > 3 in 1m | **PAUSE → FLATTEN(reason="market_quality")** |
| Daily loss hits cap or heat > cap | **AUTO FLATTEN(reason="risk_cap")** |

---

## 📊 Quick Diagnostics

### Risk Gate Blocked?
```bash
curl localhost:8000/risk | jq
curl -s localhost:8000/metrics | grep trader_risk_blocks_total
```

### Spread/Band Fail?
```bash
grep -i "FREEZE_BAND\|SPREAD_BLOWOUT" logs/aitrapp.log | tail -20
```

### Leader Not 1?
```bash
curl -s localhost:8000/metrics | grep trader_is_leader
ps aux | grep uvicorn  # Check for other instances
```

### No Signals?
```bash
curl -s localhost:8000/metrics | grep trader_signals_total
curl localhost:8000/universe | jq '.count'
```

---

## 📋 Post-Close (15:30 IST)

```bash
make post-close
psql $DATABASE_URL -f scripts/reconcile_db.sql
git push --tags
```

---

## 📚 Full Documentation

- **`LIVE_SWITCH_RUNBOOK.md`** - Complete 15-min procedure
- **`FAST_FAQ.md`** - Troubleshooting guide
- **`FIRST_HOUR_MONITORING.md`** - First hour details
- **`FINAL_LIVE_READY.md`** - Complete system overview

---

## ✅ Success Criteria

**First Hour Passes If:**
- ✅ No kill switch triggered
- ✅ Heat stays within limits
- ✅ Orders execute successfully
- ✅ OCO children place correctly
- ✅ No duplicate orders
- ✅ Latency < 500ms p95

**Then:** Continue monitoring, gradually increase caps if stable.

---

**Keep this card visible during the LIVE switch! 🚀**

---

## 📄 See Also

- **`LAUNCH_CARD.md`** - Print-friendly launch card (keep by keyboard)
- **`WEEK1_BACKLOG.md`** - Post-LIVE improvements

