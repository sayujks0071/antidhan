# 🚀 Canary LIVE Flip Guide

Safest path to flip from PAPER to LIVE with conservative settings.

## 1. Load Conservative Profile

**Settings:**
- Per-trade risk ≤ **0.25%**
- Portfolio heat ≤ **1.0%**
- Kill-switch enabled
- Indices-only (no F&O initially)

Update `config/app_config.yaml` or environment variables before flip.

## 2. Pre-Open Routine (Gate Included)

```bash
# Run E2E test
make paper-e2e

# Run pre-LIVE gate (MUST PASS)
make prelive-gate

# Expected output:
# ✅ PRELIVE GATE PASS - System ready for LIVE switch
```

**Gate checks:**
- Leader lock = 1
- All heartbeats < 5s
- Flatten speed ≤ 2s
- Zero positions/orders
- Schema aligned (details column + enum action)

## 3. Switch at 09:10 IST

```bash
# Switch to LIVE mode
make live-switch
# Or: curl -X POST :8000/mode -H 'Content-Type: application/json' -d '{"mode":"LIVE","confirmation":"LIVE"}'

# Verify readiness
curl :8000/ready | jq
# Should return: {"status": "ready", ...}
```

## 4. First Hour Watch

**Monitor continuously:**
```bash
watch -n 3 'curl -s :8000/metrics | grep -E "^trader_(is_leader|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds|orders_placed_total|oco_children_created_total|kill_switch_total)" | sort'
```

**Targets:**
- Ack p95 < 500ms (order latency)
- Heartbeats < 5s
- Heat ≪ cap; risk blocks minimal
- No alert spikes

**If ANY tripwire:**
```bash
pause && killnow && paper
# Or: make abort
```

## 5. After First Clean Hour

- Keep indices-only or widen to top-10 F&O
- Bump per-trade to 0.30%, heat 1.2% if all green
- Run `make post-close` + `reconcile_db.sql`; tag the session

