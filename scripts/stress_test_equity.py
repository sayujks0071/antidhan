import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import MagicMock

# Add openalgo root to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'scripts'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'utils'))

# Import SimpleBacktestEngine
from simple_backtest_engine import SimpleBacktestEngine

# Import Strategies
try:
    import advanced_ml_momentum_strategy as ml_strat
    import supertrend_vwap_strategy as st_strat
    import mcx_commodity_momentum_strategy as mcx_strat
    import nse_rsi_bol_trend as nse_strat
except ImportError as e:
    print(f"Error importing strategies: {e}")
    sys.exit(1)

def generate_mock_data(days=30, interval="15min"):
    """Generate synthetic OHLCV data with some trends."""
    dates = pd.date_range(end=datetime.now(), periods=days*25, freq=interval)

    # Random walk with drift
    np.random.seed(42)
    returns = np.random.normal(0.0001, 0.002, len(dates))
    price = 100 * np.cumprod(1 + returns)

    df = pd.DataFrame(index=dates)
    df['close'] = price
    df['open'] = price * (1 + np.random.normal(0, 0.001, len(dates)))
    df['high'] = df[['open', 'close']].max(axis=1) * (1 + abs(np.random.normal(0, 0.001, len(dates))))
    df['low'] = df[['open', 'close']].min(axis=1) * (1 - abs(np.random.normal(0, 0.001, len(dates))))
    df['volume'] = np.random.randint(1000, 100000, len(dates))

    # Ensure datetime index is named or column exists
    df['datetime'] = df.index

    return df

class MockClient:
    def __init__(self, data):
        self.data = data
        self.api_key = "MOCK"
        self.host = "http://MOCK"

    def history(self, *args, **kwargs):
        return self.data.copy()

def main():
    print("Generating Mock Data...")
    mock_data = generate_mock_data(days=30)

    strategies = {
        'AdvancedML': ml_strat,
        'SuperTrendVWAP': st_strat,
        'MCXMomentum': mcx_strat,
        'NSERsiBol': nse_strat
    }

    portfolio_equity = {} # Key: date, Value: equity
    initial_capital_per_strat = 1000000.0

    results = {}

    for name, module in strategies.items():
        print(f"Backtesting {name}...")
        engine = SimpleBacktestEngine(initial_capital=initial_capital_per_strat)
        # Inject Mock Client
        engine.client = MockClient(mock_data)
        # Also need to make sure engine doesn't try to validate data with DataValidator if it fails?
        # SimpleBacktestEngine handles exceptions.

        # Run backtest
        # We need to pass dates as strings
        start_date = mock_data.index[0].strftime("%Y-%m-%d")
        end_date = mock_data.index[-1].strftime("%Y-%m-%d")

        try:
            res = engine.run_backtest(
                strategy_module=module,
                symbol="MOCK",
                exchange="NSE",
                start_date=start_date,
                end_date=end_date,
                interval="15min" # Use updated interval format for pandas compatibility in engine if needed?
                                # Engine calls load_historical_data which calls client.history.
                                # Our mock client returns df directly.
                                # However, run_backtest calls load_historical_data using interval string.
            )
            results[name] = res

            # Aggregate Equity Curve
            # res['equity_curve'] is list of (timestamp_str, equity_float)
            for ts_str, equity in res['equity_curve']:
                # Convert ts_str back to datetime or date
                try:
                    ts = pd.to_datetime(ts_str).date()
                except:
                    continue

                if ts not in portfolio_equity:
                    portfolio_equity[ts] = 0
                portfolio_equity[ts] += (equity - initial_capital_per_strat) # Add PnL

        except Exception as e:
            print(f"Error backtesting {name}: {e}")
            import traceback
            traceback.print_exc()

    # Total Portfolio Value (Assuming sum of initial capitals + PnL)
    total_initial = len(strategies) * initial_capital_per_strat

    # Sort dates
    sorted_dates = sorted(portfolio_equity.keys())

    daily_equity = []
    for d in sorted_dates:
        pnl = portfolio_equity[d]
        daily_equity.append({'date': d, 'equity': total_initial + pnl, 'pnl': pnl})

    df_equity = pd.DataFrame(daily_equity)

    if df_equity.empty:
        print("No equity curve generated.")
        return

    # Calculate Drawdowns
    df_equity['peak'] = df_equity['equity'].cummax()
    df_equity['drawdown'] = df_equity['equity'] - df_equity['peak']
    df_equity['drawdown_pct'] = (df_equity['drawdown'] / df_equity['peak']) * 100

    worst_day_row = df_equity.loc[df_equity['pnl'].idxmin()]
    max_dd_row = df_equity.loc[df_equity['drawdown_pct'].idxmin()]

    print("\n" + "="*50)
    print("STRESS TEST RESULTS")
    print("="*50)
    print(f"Total Return: {df_equity.iloc[-1]['equity'] - total_initial:.2f}")
    print(f"Worst Day: {worst_day_row['date']} (PnL: {worst_day_row['pnl']:.2f})")
    print(f"Max Drawdown: {max_dd_row['drawdown_pct']:.2f}% on {max_dd_row['date']}")

    # Save Report
    with open("EQUITY_STRESS_TEST.md", "w") as f:
        f.write("# Equity Curve Stress Test Report\n\n")
        f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d')}\n\n")
        f.write("## Portfolio Performance\n")
        f.write(f"- **Total Return**: {df_equity.iloc[-1]['equity'] - total_initial:.2f}\n")
        f.write(f"- **Worst Day**: {worst_day_row['date']} (PnL: {worst_day_row['pnl']:.2f})\n")
        f.write(f"- **Max Drawdown**: {max_dd_row['drawdown_pct']:.2f}% on {max_dd_row['date']}\n\n")

        f.write("## Strategy Performance\n")
        f.write("| Strategy | Trades | Win Rate | Profit Factor | Total Return |\n")
        f.write("|----------|--------|----------|---------------|--------------|\n")

        for name, res in results.items():
            metrics = res.get('metrics', {})
            f.write(f"| {name} | {res.get('total_trades', 0)} | {metrics.get('win_rate', 0):.2f}% | {metrics.get('profit_factor', 0):.2f} | {metrics.get('total_return_pct', 0):.2f}% |\n")

if __name__ == "__main__":
    main()
