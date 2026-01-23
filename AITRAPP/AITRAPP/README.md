# 🚀 AITRAPP - Autonomous Trading App

**Exchange-grade, auditable trading bot for India's NSE using Zerodha Kite Connect.**

---

## 🎯 Quick Start

### Pre-Flight
```bash
make verify
docker compose up -d postgres redis
alembic upgrade head
make paper
make live-dashboard
make prelive-gate   # blocks if anything is off
```

### Switch to LIVE
See `LIVE_SWITCH_QUICK_REF.md` for the quick reference card.

---

## 📚 Documentation

### Getting Started
- **`LAUNCH_CARD.md`** - Print-friendly launch card (keep by keyboard!)
- **`LIVE_SWITCH_QUICK_REF.md`** - Quick reference card
- **`LIVE_SWITCH_RUNBOOK.md`** - Complete 15-minute LIVE switch procedure
- **`FAST_FAQ.md`** - Quick diagnostics for common issues

### Operational
- **`FIRST_HOUR_MONITORING.md`** - First hour LIVE monitoring guide
- **`FIRST_HOUR_LIVE_PLAYBOOK.md`** - Detailed first hour playbook
- **`POST_CLOSE_RITUAL.md`** - Daily post-close procedure
- **`BURN_IN_PLAN.md`** - 3-day burn-in protocol
- **`PAPER_E2E_TEST.md`** - 30-minute PAPER end-to-end test guide
- **`PRELIVE_GATE.md`** - Pre-LIVE gate checks documentation
- **`SECRETS_HYGIENE.md`** - Secrets management guide

### Reference
- **`FINAL_LIVE_READY.md`** - Complete system overview
- **`FINAL_GO_NO_GO.md`** - Final gates checklist
- **`FINAL_HARDENING_COMPLETE.md`** - Hardening summary
- **`WEEK1_BACKLOG.md`** - Post-LIVE improvements (non-blocking)

---

## 🛠️ Key Commands

```bash
# Pre-flight
make verify              # Environment check
make smoke-test          # Smoke tests
make red-team-drills     # Resilience tests
make paper-e2e          # 30-min PAPER end-to-end test
make prelive-gate       # Pre-LIVE gate checks
make failure-drills      # Failure scenarios

# Trading
make paper               # Start in PAPER mode
make live                # Start in LIVE mode (after burn-in)

# Operations
make post-close          # Daily post-close ritual
make rollback            # Emergency rollback to PAPER
make burnin-report       # Generate daily report

# Infrastructure
docker compose up -d     # Start services
alembic upgrade head     # Run migrations
```

---

## 🎯 System Status

**✅ Production-Ready**

All components complete:
- ✅ Database models & migrations
- ✅ Persistence layer
- ✅ OCO manager with sibling cancellation
- ✅ OrderWatcher with orchestrator callbacks
- ✅ Hardened risk gates
- ✅ Redis pub/sub bus
- ✅ Prometheus metrics
- ✅ Deterministic IDs & idempotency
- ✅ Leader lock (single runner)
- ✅ Crash-safe OCO recovery
- ✅ Price validation utilities
- ✅ Market hours gate
- ✅ Config immutability
- ✅ Incident snapshot

---

## 🚀 Next Steps

1. **Run 3-day burn-in** (PAPER mode)
   - Follow `BURN_IN_PLAN.md`
   - Complete burn-in checklist
   - Daily reports: `make burnin-report`

2. **Switch to LIVE**
   - Follow `LIVE_SWITCH_RUNBOOK.md`
   - Use `LIVE_SWITCH_QUICK_REF.md` as reference
   - Monitor first hour closely

3. **Daily Operations**
   - Monitor dashboard
   - Run post-close ritual: `make post-close`
   - Review reports and reconcile DB

---

## 🆘 Emergency

**Kill Switch:**
```bash
curl -X POST localhost:8000/flatten -d '{"reason":"emergency"}'
```

**Rollback:**
```bash
make rollback
```

**Quick Diagnostics:**
See `FAST_FAQ.md`

---

## 📊 Key Metrics

All metrics use `trader_*` prefix:
- `trader_signals_total`
- `trader_decisions_total`
- `trader_orders_placed_total`
- `trader_orders_filled_total`
- `trader_portfolio_heat_rupees`
- `trader_daily_pnl_rupees`
- `trader_order_latency_ms`
- `trader_is_leader`

Access: `curl localhost:8000/metrics`

---

## 🔒 Safety Features

- **PAPER mode default** - Safe testing
- **LIVE mode gated** - Requires explicit confirmation
- **Kill switch** - Instant flatten ≤ 2s
- **Risk guardrails** - Per-trade, portfolio heat, daily loss limits
- **Leader lock** - Prevents dual instances
- **Idempotency** - No duplicate orders
- **Crash-safe recovery** - Re-arms OCO on restart
- **Config immutability** - No runtime changes in LIVE

---

## 📁 Project Structure

```
AITRAPP/
├── apps/
│   ├── api/          # FastAPI control plane
│   └── web/          # Next.js dashboard (future)
├── packages/
│   ├── core/         # Trading logic (signals, execution, risk)
│   ├── storage/      # Database models & persistence
│   └── infra/        # Docker, deployment
├── configs/
│   ├── app.yaml      # Main config
│   ├── canary_live.yaml  # Day-1 LIVE config
│   └── strategies/   # Strategy configs
├── scripts/          # Operational scripts
├── ops/              # Prometheus alerts, SLOs
└── reports/          # Daily reports, incident snapshots
```

---

## 🎉 You're Ready!

**System is production-ready. Follow the runbooks and go LIVE!**

**Key Documents:**
- **`LAUNCH_CARD.md`** - Print this and keep by keyboard!
- **`LIVE_SWITCH_QUICK_REF.md`** - Quick reference
- **`LIVE_SWITCH_RUNBOOK.md`** - Complete procedure
- **`FAST_FAQ.md`** - Troubleshooting
- **`WEEK1_BACKLOG.md`** - Post-LIVE improvements

**Good luck! 🚀**
