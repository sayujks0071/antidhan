# 🚀 AITRAPP - Final Checklist & Playbooks

## ✅ System Status: READY FOR BURN-IN

All integration complete. All hardening patches applied. Ready for validation.

---

## 📋 Quick Reference

### Pre-Flight
```bash
alembic upgrade head
make verify
docker compose up -d postgres redis
make paper
```

### Smoke Test
```bash
make smoke-test
python scripts/test_idempotency.py
```

### Red-Team Drills
```bash
make red-team-drills
```

### Burn-In
- Follow `BURN_IN_PLAN.md`
- 3-day protocol
- Daily reports: `make burnin-report`

### LIVE Gate
After 3/3 days pass:
```bash
curl -X POST localhost:8000/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"LIVE","confirm":"CONFIRM LIVE TRADING"}'
```

### First Hour LIVE
Follow `FIRST_HOUR_LIVE_PLAYBOOK.md`

### Post-Close
Follow `POST_CLOSE_RITUAL.md`

---

## 🔒 Hardening Features

1. **Leader Lock** - Prevents dual orchestrator instances
2. **Crash-Safe OCO** - Recovers open positions on restart
3. **Price Clamping** - Validates prices before order placement
4. **Universe Hygiene** - Blocks F&O ban symbols

---

## 📊 Key Scripts

- `make verify` - Environment check
- `make smoke-test` - Smoke tests
- `make red-team-drills` - Resilience tests
- `make burnin-report` - Daily report
- `make rollback` - Emergency rollback
- `python scripts/test_idempotency.py` - Idempotency test
- `python scripts/synthetic_plan_injector.py` - OCO test

---

## 🎯 Final Go/No-Go

See `FINAL_GO_NO_GO.md` for complete checklist.

**Must Pass:**
- ✅ Pre-burn-in checklist
- ✅ Red-team drills (10 tests)
- ✅ 3-day burn-in
- ✅ Final validation

---

## 📚 Documentation

- `BURN_IN_PLAN.md` - Complete burn-in protocol
- `FIRST_HOUR_LIVE_PLAYBOOK.md` - First hour LIVE procedure
- `POST_CLOSE_RITUAL.md` - Daily post-close steps
- `FINAL_GO_NO_GO.md` - Final gates checklist
- `README_BURN_IN.md` - Quick burn-in reference

---

## 🆘 Emergency

**Rollback:**
```bash
make rollback
```

**Kill Switch:**
```bash
curl -X POST localhost:8000/flatten
```

---

## 🎉 You're Ready

1. Run pre-flight checklist
2. Execute smoke test
3. Run red-team drills
4. Complete 3-day burn-in
5. Enable LIVE mode
6. Monitor first hour closely

**Good luck! 🚀**

