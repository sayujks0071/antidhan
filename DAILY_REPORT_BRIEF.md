# Daily Strategy Code Improvement Brief - 2026-01-29

## 1. Top 5 Findings by Impact
1.  **Critical Reliability Risk**: `APIClient` lacked retry logic. Transient network errors would cause strategy crashes or missed orders.
2.  **Monitoring Blind Spot**: `monitor_trades.py` relied on a hardcoded list of strategies. New strategies (like the requested Gap Strategy) would go unmonitored.
3.  **Data Integrity Issue**: `ORBStrategy` fetched rigid 5-day history for previous close. Holiday weekends could result in missing data or incorrect "previous" close (fetching today's open).
4.  **Security Hygiene**: Strategy scripts contained hardcoded default API keys (`demo_key`) and host URLs in `argparse`, encouraging insecure practices.
5.  **New Opportunity**: Market analysis logs indicated potential for a "Gap" based strategy. A dedicated `GapStrategy` module was missing.

## 2. Files Changed
1.  `openalgo/strategies/utils/trading_utils.py` (Core Utility)
2.  `openalgo/strategies/scripts/orb_strategy.py` (Strategy Logic)
3.  `openalgo/scripts/monitor_trades.py` (Monitoring Tool)
4.  `openalgo/strategies/scripts/gap_strategy.py` (New Strategy)

## 3. Implemented Fixes & Enhancements

### Reliability: API Retries
Modified `APIClient` in `trading_utils.py` to include a retry loop (3 attempts, 1s backoff) for `history()` and `placesmartorder()`.
```python
for attempt in range(3):
    try:
        response = httpx.post(...)
        # success check
    except Exception:
        time.sleep(1)
```

### Monitoring: Dynamic Discovery
Updated `monitor_trades.py` to scan the `strategies/scripts/` directory for running processes instead of checking a static list.
```python
# Dynamic Fallback
if not matched and script_path:
    strategy_id = Path(script_path).stem
```

### Logic: Robust Date Handling
Updated `ORBStrategy.get_previous_close` to look back 7 days and explicitly target the *previous trading day*, avoiding "today's" data.

### Security: Hardening
Removed `default='demo_key'` from strategy scripts. Now requires explicit `--api_key` or `OPENALGO_APIKEY` env var.

### New Strategy: Gap Strategy
Created `gap_strategy.py`.
- **Logic**: Calculates pre-market gap %.
- **Trigger**: If Gap > 0.5% (configurable).
- **Execution**: Fades the move (Counter-trend) or Follows (Trend) based on mode after the first 5-min candle.

## 4. Verification
- **Gap Strategy**: Validated file creation and logic flow.
- **Retries**: Verified `trading_utils.py` imports and loop structure.
- **Monitoring**: Verified dynamic fallback logic in `monitor_trades.py`.
- **ORB**: Verified date logic update.

## 5. Risk Notes
- **Gap Strategy**: The new strategy defaults to "Fade" (counter-trend). In strong trend days, this carries risk. Ensure `stop_loss` is managed by `PositionManager` or external stops.
- **API Retries**: Retries are synchronous (`time.sleep`). In extremely high-frequency scenarios, this might add latency, but for 5m/1m timeframe strategies, reliability > microsecond latency.
