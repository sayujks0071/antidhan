# Operator Micro-Check (15s)

Quick verification that Day-2 gate is green before trading.

## Pre-Day-2 Check (15s)

```bash
# 1) Verify latest Day-2 JSON is fresh & PASS (jq-less)
bash scripts/read_day2_pass.sh || exit 1

# 2) Gate self-test (synthetic cases), optional after hours
bash scripts/test_prelive_gate_cases.sh

# 3) Metrics reflect the gate
curl -s :8000/metrics | grep -E '^trader_prelive_day2_(pass|age_seconds)'
```

**Expected:**
- `DAY2 PASS …` line from the reader
- `trader_prelive_day2_pass 1`
- `trader_prelive_day2_age_seconds` small (today)

---

## One-Liner Probe for tmux / Status Bar

```bash
( QUIET=1 bash scripts/read_day2_pass.sh 2>/dev/null || echo FAIL ) | sed 's/^/DAY2:/'
```

**Output:** `DAY2:PASS` or `DAY2:FAIL`

---

## Day-2 Morning (PAPER)

```bash
docker compose up -d postgres redis
export APP_MODE=PAPER APP_TIMEZONE=Asia/Kolkata PYTHONPATH=.
make burnin-check && make paper-e2e && make prelive-gate
```

---

## Post-Close

```bash
make burnin-report && make reconcile-db && make post-close
make score-day2  # updates metrics + JSON atomically
git tag burnin-day2-$(date +%F) && git push --tags
```

---

## Quick Reference

| Command | Purpose | Exit Code |
|---------|---------|-----------|
| `make read-day2` | Read Day-2 JSON (compact) | 0=PASS, 1=FAIL, 2=missing |
| `make prelive-gate` | Full pre-live gate check | 0=PASS, 1=FAIL |
| `make score-day2` | Generate Day-2 scorer JSON | 0=PASS, 1=FAIL |
| `QUIET=1 bash scripts/read_day2_pass.sh` | Dashboard probe | 0=PASS, 1=FAIL |

---

**Next:** Day-3 PAPER (if Day-2 PASS) → Canary LIVE (if 3/3 days PASS)


