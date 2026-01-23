```markdown
# AITRAPP Operational Runbook

## Purpose

This runbook provides step-by-step procedures for operating, monitoring, and troubleshooting the AITRAPP autonomous trading system.

---

## Table of Contents

1. [Pre-Flight Checklist](#pre-flight-checklist)
2. [Starting the System](#starting-the-system)
3. [Monitoring](#monitoring)
4. [Emergency Procedures](#emergency-procedures)
5. [Daily Operations](#daily-operations)
6. [Troubleshooting](#troubleshooting)
7. [Maintenance](#maintenance)
8. [Incident Response](#incident-response)

---

## Pre-Flight Checklist

**Run this checklist BEFORE starting the system each day.**

### Environment

- [ ] `.env` file exists with valid credentials
- [ ] `KITE_ACCESS_TOKEN` is current (not expired)
- [ ] Database is running and accessible
- [ ] Redis is running
- [ ] Docker services are healthy
- [ ] Sufficient disk space (>10 GB free)
- [ ] System time synchronized (NTP)

### Configuration

- [ ] `configs/app.yaml` reviewed
- [ ] Risk limits appropriate for account size
- [ ] Strategies enabled/disabled as intended
- [ ] Universe configuration updated (if changed)
- [ ] Mode set to `PAPER` (for initial testing)

### Market Conditions

- [ ] Market open time confirmed (9:15 IST on trading day)
- [ ] No major news events unless strategy accounts for them
- [ ] F&O ban list reviewed (if trading F&O)
- [ ] Circuit breakers status checked

### System Health

```bash
# Check Docker services
docker-compose ps

# Check logs for errors
tail -100 logs/aitrapp.log

# Check database connection
make shell-postgres
\dt  # List tables
\q

# Verify API health
curl http://localhost:8000/health | jq
```

---

## Starting the System

### Option 1: Paper Mode (Recommended)

```bash
# Terminal 1: Start infrastructure
make dev

# Wait for services to start (30 seconds)

# Terminal 2: Start API in PAPER mode
make paper
```

Expected output:
```
Starting AITRAPP
Mode: PAPER
Loading strategies...
Syncing instruments...
Building universe...
WebSocket connected
AITRAPP started successfully
```

### Option 2: Live Mode (⚠️ USE WITH EXTREME CAUTION)

**Only after thorough testing in paper mode for at least 2 weeks.**

```bash
# Start infrastructure
make dev

# Start in LIVE mode (requires confirmation)
make live

# You will be prompted to type: CONFIRM LIVE TRADING
```

### Verification

After startup, verify:

```bash
# Check system state
curl http://localhost:8000/state | jq

# Check positions (should be empty on fresh start)
curl http://localhost:8000/positions | jq

# Open dashboard
open http://localhost:3000  # macOS
# or
xdg-open http://localhost:3000  # Linux
```

---

## Monitoring

### Real-Time Dashboard

**URL**: http://localhost:3000

**Key Metrics to Watch**:

1. **System Status**
   - Mode (PAPER/LIVE)
   - Paused status
   - Market open/closed

2. **Positions**
   - Open positions count
   - Unrealized P&L
   - Position heat %

3. **Daily Performance**
   - Trades today
   - Win rate
   - Daily P&L
   - Daily P&L %

4. **Risk Metrics**
   - Portfolio heat (must stay < 2.0%)
   - Distance to daily loss limit

### Command-Line Monitoring

```bash
# Tail logs in real-time
tail -f logs/aitrapp.log | jq

# Watch system state (updates every 2s)
watch -n 2 'curl -s http://localhost:8000/state | jq'

# Monitor positions
watch -n 5 'curl -s http://localhost:8000/positions | jq'

# View Prometheus metrics
curl http://localhost:8000/metrics
```

### Alerts (If Configured)

- **Telegram**: Check bot messages
- **Slack**: Check webhook channel
- **Email**: Check configured email

### Log Files

```bash
# Main application log
tail -f logs/aitrapp.log

# Error-only filter
tail -f logs/aitrapp.log | jq 'select(.level=="error")'

# Warning and above
tail -f logs/aitrapp.log | jq 'select(.level=="warning" or .level=="error")'
```

---

## Emergency Procedures

### 🚨 KILL SWITCH (Flatten All Positions)

**When to Use**:
- System behaving unexpectedly
- Approaching daily loss limit
- Market conditions deteriorating rapidly
- Any situation requiring immediate exit

**How to Activate**:

**Option 1: Dashboard**
1. Open http://localhost:3000
2. Click **BIG RED BUTTON** labeled "KILL SWITCH"
3. Confirm action

**Option 2: API**
```bash
curl -X POST http://localhost:8000/flatten
```

**Option 3: Manual (Broker)**
1. Log into Zerodha Kite web
2. Navigate to Positions
3. Click "Exit All"

**After Kill Switch**:
1. System automatically pauses (no new positions)
2. All positions closed with market orders
3. Review logs to understand what happened
4. Do NOT resume until root cause identified

### ⏸️ PAUSE Trading

**Use when you want to stop new signals but keep existing positions open.**

```bash
# Pause
curl -X POST http://localhost:8000/pause

# Resume (after review)
curl -X POST http://localhost:8000/resume
```

### 🔄 Emergency Stop & Restart

```bash
# Stop all services
docker-compose down

# Check for orphaned processes
ps aux | grep -E 'uvicorn|python.*main.py'

# Kill if necessary
kill <PID>

# Restart
make paper
```

### 📞 Emergency Contacts

- **Zerodha Support**: 080-40402020
- **Exchange Support**: [NSE/BSE support numbers]
- **System Administrator**: [Your contact]
- **Broker RMS**: [If applicable]

---

## Daily Operations

### Pre-Market (Before 9:15 AM IST)

**8:00 AM - 8:30 AM**:

```bash
# 1. Start infrastructure
make dev

# 2. Sync instruments and F&O ban list
curl -X POST http://localhost:8000/universe/reload

# 3. Review strategy configs
cat configs/app.yaml

# 4. Check risk limits
grep -A 5 "^risk:" configs/app.yaml

# 5. Start application
make paper  # or make live if approved

# 6. Verify system state
curl http://localhost:8000/state | jq
```

**8:30 AM - 9:10 AM**:

- Monitor pre-market indicators (if available)
- Review overnight news
- Check for corporate actions on traded stocks
- Ensure F&O ban list is current
- Test kill switch

### Market Hours (9:15 AM - 3:30 PM IST)

**Every 15 Minutes**:
- Glance at dashboard
- Check position P&L
- Verify portfolio heat < 2%

**Hourly**:
- Review trades executed
- Check for any errors in logs
- Verify strategies are generating signals appropriately

**Key Times**:

- **9:15 AM**: Market opens, monitor for opening range strategies
- **12:00 PM**: Mid-day review, assess morning performance
- **3:15 PM**: Pre-close checks, verify EOD square-off enabled
- **3:25 PM**: All positions should be squared off
- **3:30 PM**: Market closes

### Post-Market (After 3:30 PM IST)

```bash
# 1. Verify all positions closed
curl http://localhost:8000/positions | jq

# 2. Review daily performance
curl http://localhost:8000/state | jq

# 3. Export trades for analysis
# (Implement as needed via API or DB query)

# 4. Stop application
docker-compose down

# 5. Backup database
make backup-db

# 6. Review logs for issues
grep -i error logs/aitrapp.log
```

### End-of-Day Checklist

- [ ] All positions closed
- [ ] Daily P&L recorded
- [ ] Trades exported for tax records
- [ ] Logs reviewed for errors
- [ ] Database backed up
- [ ] System stopped cleanly
- [ ] Tomorrow's strategy adjustments planned (if any)

---

## Troubleshooting

### Issue: System Won't Start

**Symptoms**: Application exits immediately or hangs

**Diagnosis**:
```bash
# Check Docker services
docker-compose ps

# Check logs
docker-compose logs api

# Check database
docker-compose logs postgres

# Check environment
cat .env | grep -E 'KITE_|DATABASE_|REDIS_'
```

**Solutions**:
1. Verify `.env` file exists and has valid values
2. Ensure database and redis are running: `make dev`
3. Check access token hasn't expired
4. Review error logs for specific issues

### Issue: WebSocket Not Connecting

**Symptoms**: "WebSocket connection failed" in logs

**Diagnosis**:
```bash
# Check network connectivity
ping kite.zerodha.com

# Verify access token
curl https://api.kite.trade/ -H "Authorization: token api_key:access_token"
```

**Solutions**:
1. Regenerate access token if expired
2. Check firewall/proxy settings
3. Verify Kite API status: https://status.kite.trade
4. Check rate limits (wait if exceeded)

### Issue: Orders Not Executing

**Symptoms**: Signals generated but no orders placed

**Diagnosis**:
```bash
# Check if paused
curl http://localhost:8000/state | jq .is_paused

# Check order logs
tail -100 logs/aitrapp.log | jq 'select(.message | contains("order"))'

# Check risk limits
curl http://localhost:8000/state | jq
```

**Solutions**:
1. Resume if paused: `curl -X POST http://localhost:8000/resume`
2. Check if daily loss limit hit
3. Verify portfolio heat < 2%
4. Check margin availability with broker
5. Review risk check logs for rejection reasons

### Issue: High Slippage

**Symptoms**: Fill price significantly different from signal price

**Diagnosis**:
- Review order type (MARKET vs LIMIT)
- Check instrument liquidity
- Examine market conditions during execution

**Solutions**:
1. Use LIMIT orders for illiquid instruments
2. Reduce position size
3. Exclude low-liquidity instruments from universe
4. Adjust `limit_chase_ticks` in config

### Issue: Positions Not Closing at EOD

**Symptoms**: Open positions after 3:25 PM

**Diagnosis**:
```bash
# Check EOD config
grep -A 3 "^market:" configs/app.yaml

# Check current time
date

# Check positions
curl http://localhost:8000/positions | jq
```

**Solutions**:
1. Ensure `eod_squareoff_enabled: true` in config
2. Manually close: `curl -X POST http://localhost:8000/flatten`
3. Check system clock synchronization
4. Review exit manager logs

### Issue: Database Full

**Symptoms**: "Disk full" or "Out of space" errors

**Solutions**:
```bash
# Check disk usage
df -h

# Clean old logs
find logs/ -name "*.log" -mtime +30 -delete

# Archive old trades (implement as needed)
# Or increase disk space
```

### Issue: Memory Leak

**Symptoms**: System becoming slow over time

**Diagnosis**:
```bash
# Check memory usage
docker stats

# Check processes
ps aux --sort=-%mem | head
```

**Solutions**:
1. Restart application daily (schedule in cron)
2. Review code for memory leaks (indicators, dataframes)
3. Reduce bar history window size
4. Limit subscribed instruments

---

## Maintenance

### Daily Maintenance

```bash
# Backup database
make backup-db

# Rotate logs (automatic with logrotate or manual)
mv logs/aitrapp.log logs/aitrapp.$(date +%Y%m%d).log

# Check disk space
df -h
```

### Weekly Maintenance

```bash
# Review strategy performance
# (Implement analysis scripts)

# Update F&O ban list (automatic daily, but verify weekly)
curl -X POST http://localhost:8000/universe/reload

# Review and tune risk parameters (if needed)
vim configs/app.yaml

# Check for software updates
git pull
pip list --outdated
```

### Monthly Maintenance

```bash
# Dependency updates
pip list --outdated
# Review and update as needed

# Security audit
pip-audit
# or
safety check

# Database optimization
docker-compose exec postgres vacuumdb -U aitrapp -d aitrapp -z

# Archive old data (>3 months)
# Implement as needed
```

### Quarterly Maintenance

- Review and update strategies
- Backtest on recent data
- Compare paper vs live performance (if running live)
- Review compliance documentation
- Update dependencies (major versions)

---

## Incident Response

### Severity Levels

**P0 - Critical**: System down, large losses, security breach
**P1 - High**: Significant impact, partial outage
**P2 - Medium**: Limited impact, workaround available
**P3 - Low**: Cosmetic issues, no immediate impact

### P0 Response Procedure

1. **Immediate Actions** (within 2 minutes):
   - Activate kill switch
   - Pause trading
   - Alert team

2. **Containment** (within 10 minutes):
   - Stop system
   - Isolate affected components
   - Preserve logs

3. **Investigation** (within 1 hour):
   - Review logs
   - Identify root cause
   - Document timeline

4. **Resolution** (ASAP):
   - Implement fix
   - Test in paper mode
   - Deploy to live (if applicable)

5. **Post-Mortem** (within 24 hours):
   - Write incident report
   - Document lessons learned
   - Update runbook

### Incident Documentation Template

```markdown
## Incident Report: [Title]

**Date**: YYYY-MM-DD
**Time**: HH:MM IST
**Severity**: P0/P1/P2/P3
**Status**: Open/Resolved

### Summary
Brief description of what happened.

### Impact
- Financial impact: INR
- Positions affected: N
- Duration: X minutes

### Timeline
- HH:MM: Event detected
- HH:MM: Kill switch activated
- HH:MM: Root cause identified
- HH:MM: Resolution implemented

### Root Cause
Technical explanation.

### Resolution
Steps taken to fix.

### Prevention
How to prevent recurrence.

### Action Items
- [ ] Task 1 (Owner, Due date)
- [ ] Task 2 (Owner, Due date)
```

---

## Appendix

### Useful Commands

```bash
# Health check
curl http://localhost:8000/health | jq

# System state
curl http://localhost:8000/state | jq

# Positions
curl http://localhost:8000/positions | jq

# Orders
curl http://localhost:8000/orders | jq

# Pause
curl -X POST http://localhost:8000/pause

# Resume
curl -X POST http://localhost:8000/resume

# Flatten
curl -X POST http://localhost:8000/flatten

# Reload strategies
curl -X POST http://localhost:8000/strategies/reload

# Database shell
make shell-postgres

# API logs
docker-compose logs -f api

# Backup database
make backup-db
```

### Configuration Reference

See `configs/app.yaml` for full config options.

**Key Settings**:
- `mode`: PAPER or LIVE
- `risk.per_trade_risk_pct`: Per-trade risk (default: 0.5%)
- `risk.max_portfolio_heat_pct`: Portfolio heat cap (default: 2.0%)
- `risk.daily_loss_stop_pct`: Daily loss limit (default: -2.5%)

### Log Levels

- `DEBUG`: Verbose, all details
- `INFO`: Normal operations
- `WARNING`: Potential issues
- `ERROR`: Failures requiring attention
- `CRITICAL`: Severe issues, immediate action

Set via `LOG_LEVEL` environment variable.

---

## Contact Information

**System Owner**: [Your name]
**Email**: [Your email]
**Phone**: [Your phone]

**Broker Support**: Zerodha 080-40402020
**Emergency Escalation**: [If applicable]

---

**Last Updated**: 2025-11-12
**Version**: 1.0
**Next Review**: 2025-12-12

---

**Remember**: When in doubt, PAUSE and review manually. Capital preservation is paramount.
```

