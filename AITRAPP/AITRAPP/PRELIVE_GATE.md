# Pre-LIVE Gate

Automated gate that blocks LIVE switch if any tripwires are triggered.

**Outputs JSON summary** for easy integration with runbooks and CI/CD.

## Usage

```bash
# Run pre-LIVE gate checks
make prelive-gate

# Or directly
bash scripts/prelive_gate.sh
```

## Checks

1. **Leader Lock**: `trader_is_leader == 1`
2. **Heartbeats**: Both marketdata and order_stream < 5s
3. **Order Latency**: p95 < 500ms (optional, may not be populated yet)
4. **Flatten Speed**: ≤ 2s
5. **Zero Positions**: All positions flattened
6. **Zero Open Orders**: No pending orders

## Exit Codes

- `0`: All checks passed - ready for LIVE switch
- `1`: One or more checks failed - do not switch to LIVE

## Integration

Add to your pre-LIVE workflow:

```bash
# Pre-open (PAPER)
make verify && docker compose up -d postgres redis
alembic upgrade head && make paper
make live-dashboard

# Run gate before switching
make prelive-gate   # blocks if anything is off

# Switch at 09:10 IST if PASS:
make live-switch
```

## Environment Variables

- `API`: API base URL (default: `http://localhost:8000`)
- `ACK_P95_MS_MAX`: Max order ack p95 in ms (default: `500`)
- `HEARTBEAT_MAX`: Max heartbeat in seconds (default: `5`)
- `LEADER_REQUIRED`: Required leader lock value (default: `1`)

## Example Output

**JSON Summary:**
```json
{
  "status": "PASS",
  "leader": 1,
  "heartbeats": {
    "market": 2.3,
    "orders": 1.8
  },
  "flatten_ms": 1200,
  "positions_open": 0,
  "orders_open": 0
}
```

**Human-readable:**
```
✅ PRELIVE GATE PASS - System ready for LIVE switch
```

## GitHub Actions Integration

The gate can be run in CI and will output JSON to the step summary:

```yaml
- name: Prelive gate (summary)
  if: always()
  run: |
    echo "### Prelive Gate Result" >> $GITHUB_STEP_SUMMARY
    echo "\`\`\`json" >> $GITHUB_STEP_SUMMARY
    bash scripts/prelive_gate.sh 2>&1 | tee -a $GITHUB_STEP_SUMMARY || true
    echo "\`\`\`" >> $GITHUB_STEP_SUMMARY
```

