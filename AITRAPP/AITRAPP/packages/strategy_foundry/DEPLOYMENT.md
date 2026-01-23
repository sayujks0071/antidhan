# Deployment & Live Signals

## Live Signal Artifact
The foundry publishes a JSON artifact at `packages/strategy_foundry/results/live_signal.json`.
This file is generated ONLY during market hours (09:15 - 15:30 IST) and ONLY if a valid champion exists.

### Schema
```json
{
  "timestamp_ist": "2023-10-27T10:00:00.123456+05:30",
  "data_timestamp": "2023-10-27T09:55:00+05:30",
  "champion_id": "a1b2c3d4",
  "timeframe": "5m",
  "instrument": "NIFTY",
  "proxy_symbol_live": "NIFTY FUT",
  "signal": 1,
  "rule_summary": "Entry: 2 rules...",
  "risk": {
    "stop_loss_dist": 50.5,
    "take_profit_dist": 100.0,
    "flat_by": "15:25"
  },
  "status": "OK",
  "reason": "StrategySignal"
}
```
- `signal`: 1 (Long), 0 (Flat/Short if enabled). Currently Long-Only default.
- `status`: "OK" or "SKIPPED".

## Gating
Live execution is NOT enabled by default. To consume this signal:
1. Ensure `ENABLE_LIVE=true` in environment.
2. Ensure `approvals/ALLOW_LIVE.txt` exists.
3. Consume the JSON using a separate execution bridge (core).

## Safety
- **Stale Data**: Signal is skipped if data is > 45 mins old.
- **Market Closed**: Signal is skipped/marked SKIPPED.
- **Hard Close**: Signal becomes 0 (Flat) after 15:25 IST.
