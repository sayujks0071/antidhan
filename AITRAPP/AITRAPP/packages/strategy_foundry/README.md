# Strategy Foundry: Aggressive Intraday Lab

A self-generating strategy lab that runs hourly to discover, backtest, and promote intraday trading strategies for NIFTY and SENSEX.

## Architecture

- **Timeframes**: 5m (Primary), 15m (Secondary), 1D (Sanity).
- **Data**: Fetches Intraday OHLC from Yahoo Finance (cached), with fallback to Daily.
- **Factory**: Generates random strategies using a grammar of:
  - **Entry**: Breakout (Donchian/BB), Trend (EMA/Supertrend), Mean Reversion (RSI/BB).
  - **Filters**: ADX, Regime.
  - **Risk**: Dynamic ATR-based Stops, Time Stops, Intraday Session Exit (15:25).
- **Backtest**: Vectorized engine with Walk-Forward Evaluation (4 folds).
- **Selection**: Ranks by Blended Score (60% 15m + 40% 5m). Promotes champions that beat incumbents.
- **Live**: Publishes a JSON signal file (`live_signal.json`) if the market is open and a valid champion exists.

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run (Full Mode: N=80, 4 Folds)
python -m packages.strategy_foundry.run_hourly

# Run Fast Mode (N=15, 2 Folds)
FAST_MODE=1 python -m packages.strategy_foundry.run_hourly
```

## Outputs

Results are stored in `packages/strategy_foundry/results/`:
- `runs/<timestamp>/`: Artifacts of each run (candidates, rankings).
- `champions/`: JSON files of current and past champions.
- `live_signal.json`: The latest trading signal (if market open).
- `leaderboard.md`: History of top performers.

## Intraday Constraints

- **Session Exit**: All positions forced flat at 15:25 IST.
- **Costs**: 5bps Slippage + Taxes + Brokerage.
- **Sanity**: Daily 1D check to prevent catastrophic failure.
