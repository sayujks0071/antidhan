# 30-Minute PAPER End-to-End Test

Comprehensive test suite to verify the complete trading loop:
- Signals → Rank → Idempotent Entry → OCO Attach → Exits → Logs/Metrics/DB

## Quick Start

```bash
# Run the full test suite
make paper-e2e

# Or directly
python scripts/paper_e2e.py
```

## Test Steps

### 0) Kick off & Sanity (2 min)
- ✅ Leader lock acquired (`trader_is_leader == 1`)
- ✅ Heartbeats < 5s (marketdata & order stream)
- ✅ Mode is PAPER
- ✅ Can take new positions

### 1) Force one end-to-end trade (5 min)
- ✅ Inject synthetic plan via `synthetic_plan_injector.py`
- ✅ Verify ENTRY order created
- ✅ Verify OCO children (STOP + TP) attached
- ✅ Check no duplicate `client_order_id`s

### 2) Exit paths (8 min)
- ✅ Test kill-switch flatten
- ✅ Verify positions cleared
- ✅ Check no orphaned OCO groups
- ✅ Verify signal→decision→order chains intact

### 3) Metrics & logs sanity (5 min)
- ✅ Core counters incremented
- ✅ Order latency histogram present
- ✅ No retry spikes (token_refresh, rate_limit)

### 4) Chaos quickies (5-10 min)
- ✅ Idempotency: second injection skipped
- ✅ No duplicate orders after idempotency test

## Manual Testing

### Inject a synthetic plan:
```bash
python scripts/synthetic_plan_injector.py --symbol NIFTY --side LONG --qty 50 --strategy ORB
```

### Monitor metrics:
```bash
watch -n 5 'curl -s localhost:8000/metrics | grep -E "^trader_(orders_placed_total|orders_filled_total|oco_children_created_total|portfolio_heat_rupees|kill_switch_total|retries_total)"'
```

### Check database:
```sql
-- Order groups
SELECT tag, parent_group, COUNT(*) c 
FROM orders 
GROUP BY tag, parent_group 
ORDER BY parent_group;

-- Duplicate check
SELECT client_order_id, COUNT(*) c 
FROM orders 
GROUP BY client_order_id 
HAVING COUNT(*) > 1;

-- Orphaned OCO groups
SELECT parent_group, COUNT(*) c
FROM orders
WHERE tag IN ('STOP','TP') AND status='PLACED'
GROUP BY parent_group
HAVING COUNT(*) <> 2;
```

## Troubleshooting

### Risk blocks entries
- Check events feed for `FREEZE_BAND`/spread or heat cap
- Try injector with safer symbol/qty

### Children not attaching
- Confirm `on_entry_filled()` fired in logs
- Check `OCOManager.attach_children` single-flight guard
- Verify DB for `parent_group`

### Duplicate children
- Single-flight check should prevent
- Verify OrderWatcher isn't double-emitting on reconnect

## Expected Output

```
============================================================
30-Minute PAPER E2E Test
============================================================

=== 0) Kick off & sanity ===
✅ Leader lock acquired
✅ marketdata_heartbeat_seconds = 2.3s
✅ order_stream_heartbeat_seconds = 1.8s
✅ Mode: PAPER
✅ Can take new positions

=== 1) Force one end-to-end trade ===
📥 Injecting plan: NIFTY @ 25000.0
✅ Found 1 ENTRY order(s)
✅ Found 2 child orders (STOP+TP)
✅ No duplicate client_order_ids

=== 2) Exit paths ===
✅ Flatten command accepted
✅ All positions flattened
✅ No orphaned OCO groups
✅ All signal→decision→order chains intact

=== 3) Metrics & logs sanity ===
✅ trader_signals_total = 1
✅ trader_orders_placed_total = 3
✅ Order latency histogram present
✅ Retry count for token_refresh: 0

=== 4) Chaos quickies ===
✅ Second injection correctly skipped (idempotency working)
✅ No duplicate orders after idempotency test

============================================================
Test Summary
============================================================

✅ All tests PASSED! ✅
```

## Integration

Add to CI/CD:
```yaml
- name: Run PAPER E2E test
  run: make paper-e2e
```

Add to morning pre-open checklist:
- Run `make paper-e2e` before market open
- Verify all tests pass
- Check metrics dashboard

## Exit Codes

- `0`: All tests passed
- `1`: One or more tests failed

Failures are logged with details for debugging.

