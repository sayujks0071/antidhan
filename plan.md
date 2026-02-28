# Analysis & Plan

## 1. Ranking
- Analyzed backtest output from `scripts/rank_strategies_v2.py`.
- **Alpha:** `nse_rsi_macd_strategy_v2` (PF: 6.23)
- **Laggard:** `mcx_naturalgas_momentum_strategy` (PF: 0.00)

## 2. Deprecation
- Archive the laggard strategy. `mcx_naturalgas_momentum_strategy.py` should be moved to `strategies/retired/`. Note: Need to update `strategy_configs.json` or ensure `strategies/retired/` handles it properly.
- Update `.gitignore` as well.

## 3. Innovation
- Create `nse_rsi_macd_strategy_v3.py`.
- Incorporate Multi-Timeframe Confirmation or Volume Profile/VWAP Filter to mitigate drawdowns. We will add a Volatility Filter (checking `INDIA VIX` to adjust sizing/stops dynamically) or a VWAP confirmation check since it's an equity strategy. Let's add an explicit VWAP confirmation filter (Buy only if Close > VWAP) or an ADX trend strength filter to avoid choppy markets. Based on previous leaderboard notes, adding an ADX filter (ADX > 25) was suggested for MACD strategies. Let's add ADX filter to V3.

## 4. Infrastructure
- In `trading_utils.py`, `calculate_macd` is duplicated (lines 985 and 1206). Let's remove the duplicate on line 1206.
- Check other utilities for duplicates.

## 5. Summary
- Write `DAILY_STATUS.md`.

## 6. Pre-Commit
- Run pre-commit checks using `pre_commit_instructions`.

## 7. Submit
- Submit changes.
