# 🚨 Quick Triage Guide

**If anything blips during Day-1 session.**

## Supervisor Issues

```bash
# Check supervisor status
curl -s :8000/debug/supervisor/status | jq

# Restart supervisor
curl -s -X POST :8000/debug/supervisor/start | jq
```

## Leader/Redis Issues

```bash
# Restart Redis and wait for recovery
docker compose restart redis
sleep 10
curl -s :8000/ready | jq

# Check leader lock
curl -s :8000/metrics | grep '^trader_is_leader'
```

## Panic Button

```bash
# Immediate abort (pause + flatten + PAPER)
make abort
```

## Micro-Checks (Before 15:20)

```bash
# Run automated micro-checks
bash scripts/micro_checks.sh

# Or manual:
# 1) Heartbeats all < 5s
curl -s :8000/metrics | awk '/^trader_(marketdata|order_stream|scan)_heartbeat_seconds/ { if ($2>=5) bad=1 } END{ exit bad }'
echo $?   # expect 0

# 2) Flat on demand in ≤2s
time curl -s -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"paper_day1"}' >/dev/null
sleep 2 && curl -s :8000/positions | jq 'length'   # expect 0
```

