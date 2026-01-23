# Quick Start - PAPER Session

## 🚀 Do This Now

```bash
# 1. Fresh venv + deps (if not already)
make setup-venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Quick sanity
python -c "import fastapi,uvicorn,sqlalchemy,alembic,redis,pandas; print('✅ deps_ok')"

# 3. Start PAPER with preflight
make start-paper

# 4. Open dashboard
make live-dashboard
tmux attach -t live
```

## 🧪 Optional: Force One End-to-End Trade (PAPER)

```bash
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB
```

## ✅ What to See

### Critical Metrics
- `trader_is_leader == 1` - Leader lock acquired
- Heartbeats `< 5s`:
  - `trader_marketdata_heartbeat_seconds < 5`
  - `trader_order_stream_heartbeat_seconds < 5`
- After injector:
  - `trader_orders_placed_total` increments
  - `trader_oco_children_created_total` increments
- `/flatten` completes ≤ 2s and positions → 0

### Check Metrics
```bash
curl -s localhost:8000/metrics | grep -E '^trader_(is_leader|orders_placed_total|oco_children_created_total|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds)' | sort
```

### Test Kill-Switch
```bash
curl -s -X POST localhost:8000/flatten \
  -H 'Content-Type: application/json' \
  -d '{"reason":"paper_smoke"}' | jq

sleep 2
curl -s localhost:8000/positions | jq
```

## 🔍 Handy Version Check (One-Shot)

```bash
python - <<'PY'
import fastapi, uvicorn, sqlalchemy, alembic, redis, pandas, kiteconnect, pydantic

try:
    import prometheus_client
    prom_version = getattr(prometheus_client, '__version__', 'installed')
except:
    prom_version = 'not found'

print({
 "fastapi": fastapi.__version__,
 "uvicorn": uvicorn.__version__,
 "sqlalchemy": sqlalchemy.__version__,
 "alembic": alembic.__version__,
 "redis": redis.__version__,
 "pandas": pandas.__version__,
 "kiteconnect": kiteconnect.__version__,
 "prometheus_client": prom_version,
 "pydantic": pydantic.__version__,
})
PY
```

## 🐛 Fast Fixes

### uvicorn Still Missing
```bash
# Ensure you're in venv
which uvicorn  # Should show venv/bin/uvicorn

# Re-install
pip install -r requirements.txt
```

### Port Busy
```bash
PORT=8010 make paper
```

### psycopg2 Errors
```bash
# You're on psycopg2-binary already
# If still failing:
pip uninstall psycopg2
pip install psycopg2-binary
```

### Environment Variables
Confirm these are set:
- `KITE_API_KEY`
- `KITE_API_SECRET`
- `KITE_ACCESS_TOKEN`
- `DATABASE_URL` (default: `postgresql://trader:trader@localhost:5432/aitrapp`)
- `REDIS_URL` (default: `redis://localhost:6379/0`)
- `APP_TIMEZONE=Asia/Kolkata`

Check:
```bash
echo $KITE_API_KEY
echo $DATABASE_URL
echo $REDIS_URL
```

## 📊 Monitoring

### Dashboard
```bash
make live-dashboard
tmux attach -t live
```

### Logs
```bash
tail -f logs/*.log
```

### Metrics
```bash
curl -s localhost:8000/metrics | grep trader_
```

### Health
```bash
curl -s localhost:8000/health | jq
```

## 🎯 Next Steps

When PAPER run looks clean:

1. **Keep tmux up** through the session
2. **Monitor metrics** in dashboard
3. **Run daily E2E**: `make paper-e2e` (pre-open)
4. **Burn-in**: Let it run for 1-3 days
5. **Pre-live gate**: `make prelive-gate` (must PASS)
6. **Canary LIVE**: When ready, switch with canary profile

## 💡 Pro Tips

- **Keep dashboard open**: `tmux attach -t live` in separate terminal
- **Watch logs**: `tail -f logs/*.log` in another terminal
- **Test flatten regularly**: Ensures kill-switch works
- **Check gate before LIVE**: `make prelive-gate` must PASS
- **Port override**: Always use `PORT=8010` if 8000 is busy

