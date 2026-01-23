# Burn-In Ready - Final Checklist

## ✅ Do Now (PAPER, 5-8 min)

### 1. Prove One Full OCO Lifecycle

```bash
# Inject trade
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB

# Watch ENTRY → SL/TP attach → /flatten ≤2s → positions=0
curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_oco_drill"}' | jq

# Verify positions = 0
sleep 2 && curl -s :8000/positions | jq 'length'
```

### 2. Watch the 5 Gauges

```bash
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|orders_placed_total|oco_children_created_total|kill_switch_total)"'
```

**Targets:**
- `trader_is_leader == 1`
- Both heartbeats < 5s
- Orders/OCO counters increment after injector
- `/flatten` ≤ 2s → positions = 0

## 🔍 One-Time Sanity (DB + Schema)

```sql
-- 0 dups / 0 orphans target
\i scripts/reconcile_db.sql;

-- audit_logs aligned (enum + details)
SELECT typname FROM pg_type WHERE typname='auditactionenum';

SELECT column_name, udt_name FROM information_schema.columns
WHERE table_name='audit_logs' AND column_name IN ('action','details');
```

Or via command line:

```bash
psql "${DATABASE_URL#postgresql+psycopg2://}" -f scripts/reconcile_db.sql

psql "${DATABASE_URL#postgresql+psycopg2://}" -c "SELECT typname FROM pg_type WHERE typname='auditactionenum';"

psql "${DATABASE_URL#postgresql+psycopg2://}" -c "SELECT column_name, udt_name FROM information_schema.columns WHERE table_name='audit_logs' AND column_name IN ('action','details');"
```

## 🌅 Pre-Open Routine (Every Day)

```bash
make paper-e2e

make prelive-gate   # schema gate included → blocks LIVE if misaligned
```

## 🌄 EOD Ritual (60s)

```bash
make burnin-report

psql "${DATABASE_URL#postgresql+psycopg2://}" -f scripts/reconcile_db.sql

make post-close
```

## 🔒 Two Tiny Hardeners

### 1. Lock Exact Working Runtime

**Production boxes should install from locked requirements:**

```bash
# Use requirements.lock for exact versions
pip install -r requirements.lock

# Verify versions match
python -c "import fastapi; print(f'fastapi: {fastapi.__version__}')"
```

**Why:** Your current runtime shows newer libs than earlier ranges. Freeze what's working now to avoid drift before LIVE.

### 2. Alert on `/flatten` Use

**Telegram/Slack alert on kill switch:**

The system now sends alerts when `/flatten` is triggered. Configure:

```bash
# Set environment variables
export TG_BOT_TOKEN="your_telegram_bot_token"
export TG_CHAT_ID="your_telegram_chat_id"

# Or Slack
export SLACK_WEBHOOK_URL="your_slack_webhook_url"
```

**What triggers:**
- `trader_kill_switch_total{reason=...}` increments
- Alert sent via Telegram/Slack (if configured)
- Includes reason and position details

## 📊 Day-1 Success Criteria

If today's burn-in shows:
- ✅ `trader_is_leader == 1`
- ✅ Both heartbeats < 5s
- ✅ One clean OCO lifecycle
- ✅ `/flatten` ≤ 2s
- ✅ Reconcile script is clean (0 dups, 0 orphans)

**Count that as Day-1.**

## 🎯 3-Day Burn-In Plan

1. **Day 1**: Today - Prove OCO lifecycle, verify all gauges
2. **Day 2**: Tomorrow - Run pre-open routine, monitor all day
3. **Day 3**: Day after - Final verification, run gate

After 3 clean days:
- Run `make prelive-gate` (must PASS)
- Flip canary LIVE

## 📋 Quick Reference

### Monitor Metrics
```bash
watch -n 5 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|orders_placed_total|oco_children_created_total|kill_switch_total)"'
```

### Test OCO Lifecycle
```bash
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB
curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_oco_drill"}' | jq
```

### Daily Checks
```bash
# Morning
make paper-e2e
make prelive-gate

# Evening
make burnin-report
psql "${DATABASE_URL#postgresql+psycopg2://}" -f scripts/reconcile_db.sql
make post-close
```

## 🚀 You're Ready!

System is burn-in ready. Monitor the gauges, prove the OCO lifecycle, and after 3 clean days, you're ready for canary LIVE.

