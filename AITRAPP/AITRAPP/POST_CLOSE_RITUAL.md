# Post-Close Ritual (Daily)

## 🎯 Objective

Verify system integrity, generate reports, and prepare for next session.

---

## Timing

**Run at 15:30 IST (after market close)**

---

## Checklist

### 1. Verify Zero Open Orders/Positions

```bash
# Check positions
curl localhost:8000/positions | jq '.count'
# Should be 0

# Check orders (via API or DB)
psql $DATABASE_URL -c "SELECT COUNT(*) FROM orders WHERE status IN ('PLACED', 'PARTIAL');"
# Should be 0
```

### 2. Generate Daily Report

```bash
make burnin-report
```

**Review:**
- Signals generated
- Decisions made
- Orders placed/filled
- Trades completed
- P&L summary
- Risk events

### 3. Run Reconciliation

```bash
psql $DATABASE_URL -f scripts/reconcile_db.sql
```

**Verify:**
- No orphan OCO siblings
- No duplicate `client_order_id`
- Complete audit trail
- All positions have OCO groups

### 4. Snapshot Config & Session

```bash
# Get config SHA
python -c "from packages.core.config import app_config; print(app_config.config_sha)"

# Tag git
git tag burnin-$(date +%Y-%m-%d)

# Archive report
mkdir -p reports
cp burnin-report-$(date +%Y-%m-%d).txt reports/
```

### 5. Rotate Access Token (if required)

**Check broker policy:**
- Some brokers require token rotation daily/weekly
- Update `.env` if needed
- Restart API after update

```bash
# Update .env
KITE_ACCESS_TOKEN=new_token_here

# Restart
# (Kill process and restart)
```

### 6. Review Logs

```bash
# Check for errors
grep -i error logs/aitrapp.log | tail -20

# Check for warnings
grep -i warning logs/aitrapp.log | tail -20

# Check kill switch usage
grep -i "kill\|flatten" logs/aitrapp.log
```

### 7. Database Backup (Optional but Recommended)

```bash
make backup-db
```

---

## Daily Report Template

**Save as:** `reports/burnin-YYYY-MM-DD.txt`

```
Date: YYYY-MM-DD
Mode: PAPER/LIVE
Config SHA: abc123...

Signals: X
Decisions: Y (Z approved, W rejected)
Orders: A (B filled)
Trades: C (D winners, E losers)
P&L: ₹X.XX

Risk Events:
- Event 1
- Event 2

Issues:
- Issue 1 (if any)
- Issue 2 (if any)

Next Steps:
- Action 1
- Action 2
```

---

## Post-Close SQL Queries

```sql
-- Daily summary
SELECT 
    DATE(ts) as date,
    COUNT(*) as signals,
    SUM(CASE WHEN score > 0.7 THEN 1 ELSE 0 END) as high_confidence
FROM signals
WHERE DATE(ts) = CURRENT_DATE
GROUP BY DATE(ts);

-- P&L breakdown
SELECT 
    strategy_name,
    COUNT(*) as trades,
    SUM(net_pnl) as total_pnl,
    AVG(net_pnl) as avg_pnl
FROM trades t
JOIN positions p ON t.position_id = p.id
WHERE DATE(t.ts) = CURRENT_DATE
GROUP BY strategy_name;

-- Risk events summary
SELECT 
    event_type,
    COUNT(*) as count
FROM risk_events
WHERE DATE(ts) = CURRENT_DATE
GROUP BY event_type;
```

---

## Pre-Open Next Day

**Before 09:00 IST:**
- [ ] Review previous day's report
- [ ] Check for issues
- [ ] Update config if needed
- [ ] Verify environment: `make verify`
- [ ] Start API: `make paper` or `make live`

---

## Notes

- Run ritual immediately after close
- Don't skip reconciliation
- Archive all reports
- Tag git for audit trail
- Rotate tokens if required

**Consistency is key for reliable trading.**

