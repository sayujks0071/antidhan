# Day-2 Last-Mile Card (Tape Next to GO Block)

**10-second reference, roll without thinking**

---

## 10-Sec Green-Room Snap

```bash
make verify && bash scripts/check_ntp_drift.sh && bash scripts/read_day2_pass.sh && make prelive-gate
```

---

## Roll

Use `DAY2_GO_BLOCK.md` exactly as written. Keep the gauges pane open the whole session.

---

## Tripwires (Flatten Immediately If…)

* Leader flips to 0 or `/ready` returns 503 during market hours
* Any heartbeat ≥ 5s for > 1m
* OCO child fails to appear within expected ack window
* Rate-limit queue continues rising > 30s
* Spreads blow out beyond your freeze-band threshold

---

## One-Liners (Muscle Memory)

```bash
# Leader 0
docker compose restart redis && sleep 10 && curl -s :8000/ready | jq

# Scan stalled
curl -s :8000/debug/supervisor/status | jq && curl -s -X POST :8000/debug/supervisor/start | jq

# Schema gripe
alembic upgrade head && make reconcile-db

# Emergency
make abort   # pause + flatten + PAPER
```

---

## Post-Close (60s)

```bash
make burnin-report && make reconcile-db && make post-close
make score-day2
git tag burnin-day2-$(date +%F) && git push --tags
```

---

## Success Signature (Mental Checklist)

* ✅ Leader == 1 all session
* ✅ All three heartbeats < 5s
* ✅ ≥1 clean OCO lifecycle; `/flatten` ≤ 2s → positions=0
* ✅ Reconcile: duplicates=0, orphans=0
* ✅ No alerts (PreLiveDay2Fail/PreLiveDay2Stale)
* ✅ `trader_prelive_day2_pass 1` and age small

---

**You're green-lit. Run the GO block, keep the five gauges green, log one clean OCO, score Day-2, tag.**


