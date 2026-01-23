# 🚀 Quick Start: Burn-In & LIVE Gate

## Pre-Flight (One-Time)

```bash
# 1. Setup database
alembic upgrade head

# 2. Verify environment
make verify

# 3. Start infrastructure
docker compose up -d postgres redis

# 4. Start API
make paper
```

## 60-Minute Smoke Test

```bash
make smoke-test
python scripts/test_idempotency.py
```

## Day-0 Half-Session

Run during market hours (2-3 hours). Validate:
- Kill switch works (≤ 2s)
- OCO siblings cancel correctly
- No duplicate orders
- Complete audit trail

## 3-Day Burn-In

Each day must pass all criteria. See `BURN_IN_PLAN.md` for details.

## LIVE Gate

After 3/3 days pass:

```bash
curl -X POST localhost:8000/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"LIVE","confirm":"CONFIRM LIVE TRADING"}'
```

## Rollback

If issues occur:

```bash
make rollback
```

## Key Scripts

- `make verify` - Check environment
- `make smoke-test` - Run smoke tests
- `make burnin-report` - Generate daily report
- `make rollback` - Rollback to PAPER
- `python scripts/test_idempotency.py` - Test idempotency
- `python scripts/synthetic_plan_injector.py` - Test OCO paths

## Full Documentation

See `BURN_IN_PLAN.md` for complete burn-in protocol.

