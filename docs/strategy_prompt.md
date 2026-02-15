# OpenAlgo Strategy Development Prompt for Google Jules

Use this prompt when asking Jules to create new trading strategies for the OpenAlgo platform.

---

## Prompt

```
You are building a production-grade trading strategy for the OpenAlgo platform. Follow these specifications exactly.

## Platform Architecture

- **Framework**: Strategies run as standalone Python scripts inside a Docker container at `/app/strategies/scripts/`
- **Base Class**: `BaseStrategy` in `strategies/utils/base_strategy.py` — provides `fetch_history()`, `execute_trade()`, `calculate_rsi()`, `calculate_ema()`, `calculate_atr()`, `calculate_adx()`, `calculate_supertrend()`, `calculate_intraday_vwap()`, `analyze_volume_profile()`, `check_sector_correlation()`, `get_vix()`, `get_adaptive_quantity()`
- **Trading Utils**: `strategies/utils/trading_utils.py` — provides `APIClient`, `PositionManager`, `SmartOrder`, `normalize_symbol()`, `is_market_open()`, `calculate_atr()`, `calculate_adx()`, `calculate_rsi()`, `calculate_sma()`, `calculate_ema()`, `calculate_bollinger_bands()`, `calculate_supertrend()`, `calculate_intraday_vwap()`, `analyze_volume_profile()`, `calculate_relative_strength()`
- **Options Utils**: `strategies/utils/optionchain_utils.py` — for option chain strategies
- **MCX Utils**: `strategies/utils/mcx_utils.py` — for commodity strategies
- **Backtesting**: `strategies/utils/simple_backtest_engine.py` — calls `generate_signal(df, client, symbol)` on each strategy
- **Scheduler**: Each strategy has schedule_start, schedule_stop, schedule_days managed by the platform. Strategies run in a `while True` loop with `time.sleep(60)`.

## File Structure Template

```python
#!/usr/bin/env python3
"""
[Strategy Name] - [Brief Description]
[Exchange]: NSE / MCX / NSE_INDEX
[Type]: EQUITY / FUT / OPT

CHANGELOG:
- YYYY-MM-DD: Initial version with enterprise risk management
"""
import os
import sys
import time
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Path setup
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, 'utils')
sys.path.insert(0, utils_dir)

from base_strategy import BaseStrategy
from trading_utils import (
    normalize_symbol, calculate_atr, calculate_adx,
    calculate_rsi, calculate_sma, calculate_ema,
    is_market_open, APIClient, PositionManager
)

# ═══════════════════════════════════════════
# ENTERPRISE RISK PARAMETERS (MANDATORY)
# ═══════════════════════════════════════════
ATR_SL_MULTIPLIER = 2.0       # Stop loss = ATR × this (use 1.5 for options, 2.0 for equity, 2.0 for MCX)
ATR_TP_MULTIPLIER = 4.0       # Take profit = ATR × this (minimum 2:1 R:R ratio)
BREAKEVEN_TRIGGER_R = 1.0     # Move SL to entry after this R multiple (0.8 for options)
TIME_STOP_BARS = 20           # Force exit after N bars with no SL/TP hit (15 for options, 25 for MCX)
MAX_RISK_PCT = 2.0            # Max % of capital risked per trade (1.5% for MCX, 5% for options)
MAX_DAILY_LOSS_PCT = 3.0      # Stop trading after this % daily drawdown
CAPITAL = 500000              # Reference capital for position sizing

# Strategy-specific parameters here...


class YourStrategy(BaseStrategy):
    def __init__(self, symbol, quantity=10, api_key=None, host=None, **kwargs):
        super().__init__(
            name=f"StrategyName_{symbol}",
            symbol=symbol, quantity=quantity,
            api_key=api_key, host=host, **kwargs
        )
        # State tracking
        self.trailing_stop = 0.0
        self.entry_price_local = 0.0
        self.bars_in_trade = 0
        self.partial_exit_done = False
        self.daily_pnl = 0.0

    def cycle(self):
        """Main strategy logic — called every 60 seconds."""

        # 1. FETCH DATA
        exchange = "NSE"  # or "MCX", "NSE_INDEX"
        df = self.fetch_history(days=30, exchange=exchange)
        if df.empty or len(df) < 50:
            return

        # 2. CALCULATE INDICATORS
        atr_series = calculate_atr(df)
        atr_val = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0
        adx_series = calculate_adx(df)
        adx_val = float(adx_series.iloc[-1]) if not adx_series.empty else 0.0

        last = df.iloc[-1]
        price = float(last['close'])

        # Volume confirmation
        vol_mean = df['volume'].rolling(20).mean().iloc[-1]
        vol_confirmed = last['volume'] > vol_mean * 1.5

        # ATR-based position sizing
        sl_dist = ATR_SL_MULTIPLIER * atr_val
        risk_amount = CAPITAL * (MAX_RISK_PCT / 100)
        qty = max(1, int(risk_amount / sl_dist)) if sl_dist > 0 else self.quantity

        # 3. MANAGE EXISTING POSITION
        if self.pm and self.pm.has_position():
            self.bars_in_trade += 1

            # Time stop
            if self.bars_in_trade >= TIME_STOP_BARS:
                self.execute_trade('SELL', abs(self.pm.position), price)
                self._reset_state()
                return

            # Breakeven trigger
            if self.entry_price_local > 0 and atr_val > 0:
                r_mult = (price - self.entry_price_local) / (ATR_SL_MULTIPLIER * atr_val)
                if r_mult >= BREAKEVEN_TRIGGER_R and self.trailing_stop < self.entry_price_local:
                    self.trailing_stop = self.entry_price_local

                # Partial exit at 1.5R
                if r_mult >= 1.5 and not self.partial_exit_done:
                    partial = max(1, abs(self.pm.position) // 2)
                    self.execute_trade('SELL', partial, price)
                    self.partial_exit_done = True
                    return

            # ATR trailing stop (ratchet only upward)
            new_stop = price - (ATR_SL_MULTIPLIER * atr_val)
            if new_stop > self.trailing_stop:
                self.trailing_stop = new_stop

            if price < self.trailing_stop:
                self.execute_trade('SELL', abs(self.pm.position), price)
                self._reset_state()
                return

            # Strategy-specific exit conditions here...
            return

        # 4. DAILY LOSS CHECK
        if self.daily_pnl < -(CAPITAL * MAX_DAILY_LOSS_PCT / 100):
            return

        # 5. ENTRY LOGIC (multi-confirmation required)
        # RULE: Require at least 2-3 confirming signals before entry
        signals = []

        # Signal 1: Your primary signal
        # signals.append(your_condition)

        # Signal 2: ADX regime filter
        # - Trend strategies: ADX > 25
        # - Mean reversion: ADX < 20
        # signals.append(adx_val > 25)

        # Signal 3: Volume confirmation
        # signals.append(vol_confirmed)

        # Signal 4: RSI filter (avoid overbought/oversold)
        # signals.append(30 < rsi < 70)

        if sum(signals) >= 2:  # Require minimum 2 confirmations
            self.execute_trade('BUY', qty, price)
            self.entry_price_local = price
            self.trailing_stop = price - sl_dist
            self.bars_in_trade = 0
            self.partial_exit_done = False

    def _reset_state(self):
        self.trailing_stop = 0.0
        self.entry_price_local = 0.0
        self.bars_in_trade = 0
        self.partial_exit_done = False


# ═══════════════════════════════════════════
# BACKTEST INTERFACE (MANDATORY)
# ═══════════════════════════════════════════
def generate_signal(df, client=None, symbol=None, params=None):
    """
    Module-level function for backtesting.
    Called by SimpleBacktestEngine on each bar.

    Args:
        df: DataFrame with OHLCV data up to current bar
        client: APIClient instance (optional, for live data)
        symbol: Trading symbol
        params: Dict of strategy parameters

    Returns:
        (action, score, details) where:
        - action: 'BUY', 'SELL', or 'HOLD'
        - score: 0.0-1.0 confidence score
        - details: dict with at minimum: atr, quantity, sl, tp
    """
    if df is None or df.empty or len(df) < 50:
        return 'HOLD', 0.0, {}

    df = df.copy()

    # Calculate indicators
    atr_series = calculate_atr(df)
    atr_val = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0
    adx_series = calculate_adx(df)
    adx_val = float(adx_series.iloc[-1]) if not adx_series.empty else 0.0

    last = df.iloc[-1]
    price = float(last['close'])

    # Position sizing
    sl_dist = ATR_SL_MULTIPLIER * atr_val if atr_val > 0 else price * 0.02
    qty = max(1, int((CAPITAL * MAX_RISK_PCT / 100) / sl_dist))

    details = {
        'close': price,
        'atr': atr_val,
        'adx': adx_val,
        'quantity': qty,
        'sl': price - sl_dist,
        'tp': price + ATR_TP_MULTIPLIER * atr_val,
        'breakeven_trigger_r': BREAKEVEN_TRIGGER_R,
        'time_stop_bars': TIME_STOP_BARS,
    }

    # Entry logic (same as cycle() but stateless)
    # ... your signal logic here ...

    # if buy_signal:
    #     return 'BUY', confidence_score, details
    # if sell_signal:
    #     return 'SELL', confidence_score, details

    return 'HOLD', 0.0, details


if __name__ == "__main__":
    YourStrategy.cli()
```

## MANDATORY RULES

### Risk Management (Non-Negotiable)
1. **Every strategy MUST have** ATR_SL_MULTIPLIER, ATR_TP_MULTIPLIER, BREAKEVEN_TRIGGER_R, TIME_STOP_BARS, MAX_RISK_PCT, MAX_DAILY_LOSS_PCT as module-level constants
2. **R:R ratio must be >= 2:1** (ATR_TP_MULTIPLIER >= 2 × ATR_SL_MULTIPLIER)
3. **Position sizing via ATR**: `qty = risk_amount / (ATR × SL_MULTIPLIER)`, never fixed lots
4. **Daily loss circuit breaker**: Stop all trading after MAX_DAILY_LOSS_PCT hit
5. **Trailing stop**: Must ratchet only in favorable direction, never widen
6. **Partial exit**: Close 50% at 1.5R, trail the rest
7. **Time stop**: Force exit after TIME_STOP_BARS if price is stagnant

### Entry Logic (Multi-Confirmation)
1. **Never enter on a single signal** — require minimum 2 independent confirmations
2. **Always include**:
   - ADX regime filter (>25 for trend, <20 for mean reversion)
   - Volume confirmation (>1.5x 20-period average)
3. **Trend strategies**: Price above key MA + momentum indicator + volume
4. **Mean reversion**: RSI extreme + Bollinger Band touch + ranging ADX + volume spike
5. **Breakout strategies**: Close-based (not wick), volume >2x average, ADX rising

### Exit Logic (Layered)
1. **Hard stop**: ATR-based, set on entry, never moved against position
2. **Breakeven**: Move SL to entry after BREAKEVEN_TRIGGER_R profit
3. **Partial exit**: 50% at 1.5R
4. **Trailing stop**: ATR-based, ratchets in favorable direction
5. **Time stop**: Exit after TIME_STOP_BARS
6. **Signal-based**: Exit on signal reversal (RSI neutral, VWAP cross, etc.)

### Exchange-Specific Rules

**NSE Equity/Index:**
- Exchange: "NSE" or "NSE_INDEX" for indices
- Market hours: 9:15-15:30 IST
- Skip first 15 min for intraday (opening volatility)
- Use `is_market_open()` check

**MCX Commodity:**
- Exchange: "MCX"
- Sessions: Morning (9:00-17:00), Evening (17:00-23:30)
- Use `is_market_open("MCX")`
- Session-end exit: Close before 23:25 (evening) or 16:55 (day)
- No new entries in last 30 min of session
- ATR_SL_MULTIPLIER = 2.0, ATR_TP_MULTIPLIER = 3.5
- MAX_RISK_PCT = 1.5% (commodities are leveraged)

**Options (NSE):**
- Use optionchain_utils for chain data
- ATR_SL_MULTIPLIER = 1.5, TIME_STOP_BARS = 15
- IV rank filter: only sell when IV > 50th percentile
- VIX-based sizing: reduce at VIX > 20, halt at VIX > 30
- Close 2 days before expiry (gamma risk)
- 50% profit target on premium sold
- Max loss: 50% of premium/credit
- No naked selling — always hedge with wings
- Lot sizes: NIFTY=50, BANKNIFTY=30, SENSEX=10

### Code Quality
1. **No hardcoded paths** — use `os.path` relative to script location
2. **No debug logging** to local filesystem paths
3. **Graceful imports** — try/except with fallbacks for all utility imports
4. **generate_signal()** MUST be a module-level function (not a method) for backtesting
5. **generate_signal()** MUST return `(action, score, details)` where details has `atr`, `quantity`, `sl`, `tp`
6. **Use `normalize_symbol()`** for all symbol references
7. **CHANGELOG** at top of every file with dated entries
8. **All numeric values from pandas** must be cast to `float()` before comparison to avoid numpy type issues

### What NOT to Do
- No `requests` library — use `APIClient` from trading_utils
- No hardcoded API keys or hosts
- No `print()` in production — use `self.logger` or the logging module
- No fixed position sizes — always ATR-based
- No single-indicator entries
- No strategies without stop losses
- No strategies without generate_signal() backtest function
- No imports from external ML libraries unless absolutely necessary (keep dependencies minimal)
```

---

## Usage

Copy the prompt above into Jules when requesting a new strategy. Specify:
1. **Strategy type**: trend following, mean reversion, breakout, options selling, etc.
2. **Instrument**: NIFTY, BANKNIFTY, RELIANCE, SILVER, CRUDEOIL, etc.
3. **Exchange**: NSE, MCX, NSE_INDEX
4. **Timeframe**: 1m, 5m, 15m, 1h, D
5. **Any specific indicators or logic** you want incorporated
