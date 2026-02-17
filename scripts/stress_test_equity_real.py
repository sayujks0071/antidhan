import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add paths
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'scripts'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'utils'))

from simple_backtest_engine import SimpleBacktestEngine
from trading_utils import APIClient

# Import Strategies
try:
    import supertrend_vwap_strategy
    import ai_hybrid_reversion_breakout
    import mcx_commodity_momentum_strategy
except ImportError as e:
    print(f"Error importing strategies: {e}")
    sys.exit(1)

# Mock Client to inject Mock Data
class MockDataClient:
    def __init__(self, data_map):
        self.data_map = data_map
        self.api_key = "MOCK"
        self.host = "http://MOCK"

    def history(self, symbol, exchange, interval, start_date, end_date, **kwargs):
        # Return data from map if available
        if symbol in self.data_map:
            df = self.data_map[symbol].copy()
            # Filter by date
            if 'datetime' in df.columns:
                 mask = (df['datetime'] >= pd.to_datetime(start_date)) & (df['datetime'] <= pd.to_datetime(end_date))
                 return df.loc[mask]
            return df
        return pd.DataFrame()

    def get_quote(self, symbol, exchange="NSE", **kwargs):
        return None

def generate_stress_data(days=30, interval="15min", scenario="crash"):
    """
    Generate synthetic data for stress testing.
    Scenario: 'crash', 'choppy', 'bull_run'
    """
    dates = pd.date_range(end=datetime.now(), periods=days*25, freq=interval)

    np.random.seed(42)

    if scenario == "crash":
        # Trend down with high volatility
        returns = np.random.normal(-0.002, 0.02, len(dates)) # Negative drift, High Vol
    elif scenario == "choppy":
        # No trend, mean reversion
        returns = np.random.normal(0, 0.01, len(dates))
    else:
        # Bull run
        returns = np.random.normal(0.001, 0.01, len(dates))

    price = 1000 * np.cumprod(1 + returns)

    df = pd.DataFrame(index=dates)
    df['close'] = price
    df['open'] = price * (1 + np.random.normal(0, 0.002, len(dates)))
    df['high'] = df[['open', 'close']].max(axis=1) * (1 + abs(np.random.normal(0, 0.002, len(dates))))
    df['low'] = df[['open', 'close']].min(axis=1) * (1 - abs(np.random.normal(0, 0.002, len(dates))))
    df['volume'] = np.random.randint(1000, 100000, len(dates))
    df['datetime'] = df.index

    return df

def main():
    print("Initializing Equity Stress Test...")

    # 1. Generate Data for different scenarios
    # We use NIFTY for SuperTrend, RELIANCE for Hybrid, SILVER for MCX

    # Crash Scenario Data
    nifty_crash = generate_stress_data(scenario="crash")
    reliance_crash = generate_stress_data(scenario="crash")
    silver_crash = generate_stress_data(scenario="crash")

    data_map = {
        'NIFTY': nifty_crash,
        'RELIANCE': reliance_crash,
        'SILVER': silver_crash
    }

    mock_client = MockDataClient(data_map)

    strategies = {
        'SuperTrendVWAP': {'module': supertrend_vwap_strategy, 'symbol': 'NIFTY', 'exchange': 'NSE_INDEX'},
        'AIHybrid': {'module': ai_hybrid_reversion_breakout, 'symbol': 'RELIANCE', 'exchange': 'NSE'},
        'MCXMomentum': {'module': mcx_commodity_momentum_strategy, 'symbol': 'SILVER', 'exchange': 'MCX'}
    }

    start_date = nifty_crash.index[0].strftime("%Y-%m-%d")
    end_date = nifty_crash.index[-1].strftime("%Y-%m-%d")

    portfolio_equity = {} # Date -> Equity
    initial_capital = 1000000.0
    total_capital = len(strategies) * initial_capital

    print(f"Running Stress Test (Scenario: CRASH) from {start_date} to {end_date}...")

    strategy_results = {}

    for name, config in strategies.items():
        print(f"  Testing {name} on {config['symbol']}...")
        engine = SimpleBacktestEngine(initial_capital=initial_capital)
        engine.client = mock_client # Inject mock client

        try:
            res = engine.run_backtest(
                strategy_module=config['module'],
                symbol=config['symbol'],
                exchange=config['exchange'],
                start_date=start_date,
                end_date=end_date,
                interval="15m"
            )
            strategy_results[name] = res

            # Aggregate Equity
            for ts_str, eq in res['equity_curve']:
                ts = pd.to_datetime(ts_str).date()
                if ts not in portfolio_equity:
                    portfolio_equity[ts] = 0
                portfolio_equity[ts] += (eq - initial_capital)

        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()

    # Analyze Portfolio Equity
    sorted_dates = sorted(portfolio_equity.keys())
    daily_values = []

    current_eq = total_capital
    for d in sorted_dates:
        pnl = portfolio_equity[d]
        # PnL in portfolio_equity is cumulative for that day across strategies?
        # simple_backtest_engine returns equity_curve which is cumulative equity over time.
        # But here I am summing (eq - initial).
        # Wait, simple_backtest_engine returns list of (timestamp, equity).
        # Since timestamps might differ slightly (if strategies trade on different bars), summing by Date is approx.
        # Ideally, we align by timestamp. But Date is fine for Daily Equity.
        # Actually, `portfolio_equity[ts]` accumulates the *current equity - initial* for all strategies at that date.
        # If a strategy has multiple entries for a date, it might overwrite?
        # No, I should take the *last* equity value for each date for each strategy.
        pass

    # Better Aggregation:
    # 1. Create a DF with all dates.
    # 2. For each strategy, resample equity curve to Daily Close.
    # 3. Sum.

    df_all = pd.DataFrame(index=sorted(list(set([pd.to_datetime(ts).date() for ts in nifty_crash.index]))))

    for name, res in strategy_results.items():
        if 'equity_curve' in res and res['equity_curve']:
            # Convert to DF
            eq_data = [(pd.to_datetime(t), v) for t, v in res['equity_curve']]
            df_eq = pd.DataFrame(eq_data, columns=['datetime', 'equity'])
            df_eq['date'] = df_eq['datetime'].dt.date
            # Take last value per day
            daily = df_eq.groupby('date')['equity'].last()
            df_all[name] = daily

    # Forward fill (if no trade, equity remains same)
    df_all = df_all.ffill().fillna(initial_capital)

    df_all['Portfolio'] = df_all.sum(axis=1)
    df_all['PnL'] = df_all['Portfolio'].diff()

    # Identify Worst Day
    worst_day = df_all['PnL'].idxmin()
    worst_day_pnl = df_all.loc[worst_day]['PnL']

    # Identify Max Drawdown
    peak = df_all['Portfolio'].cummax()
    drawdown = (df_all['Portfolio'] - peak)
    dd_pct = (drawdown / peak) * 100
    max_dd_day = dd_pct.idxmin()
    max_dd_val = dd_pct.min()

    print("\n" + "="*50)
    print("STRESS TEST RESULTS (CRASH SCENARIO)")
    print("="*50)
    print(f"Total Return: {df_all['Portfolio'].iloc[-1] - total_capital:.2f}")
    print(f"Worst Day: {worst_day} (PnL: {worst_day_pnl:.2f})")
    print(f"Max Drawdown: {max_dd_val:.2f}% on {max_dd_day}")

    # Strategy contribution to Worst Day
    print("\nWorst Day Breakdown:")
    row = df_all.loc[worst_day]
    prev_row = df_all.shift(1).loc[worst_day]
    for name in strategies.keys():
        if name in df_all.columns:
            strat_pnl = row[name] - prev_row[name]
            print(f"  {name}: {strat_pnl:.2f}")
        else:
            print(f"  {name}: N/A (Failed/No Data)")

    # Generate Report
    with open("EQUITY_STRESS_TEST.md", "w") as f:
        f.write("# Equity Curve Stress Test Report\n\n")
        f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d')}\n")
        f.write(f"**Scenario**: Crash (Simulated High Volatility Down Trend)\n\n")

        f.write("## Portfolio Performance\n")
        if not df_all.empty:
            f.write(f"- **Total Return**: {df_all['Portfolio'].iloc[-1] - total_capital:.2f}\n")
            f.write(f"- **Worst Day**: {worst_day} (PnL: {worst_day_pnl:.2f})\n")
            f.write(f"- **Max Drawdown**: {max_dd_val:.2f}% on {max_dd_day}\n\n")
        else:
            f.write("No portfolio data generated.\n\n")

        f.write("## Strategy Performance\n")
        f.write("| Strategy | Trades | Win Rate | Profit Factor | Total Return |\n")
        f.write("|----------|--------|----------|---------------|--------------|\n")

        for name, res in strategy_results.items():
            metrics = res.get('metrics', {})
            ret = res.get('final_capital', 0) - res.get('initial_capital', 0)
            f.write(f"| {name} | {res.get('total_trades', 0)} | {metrics.get('win_rate', 0):.2f}% | {metrics.get('profit_factor', 0):.2f} | {ret:.2f} |\n")

        f.write("\n## Root Cause Analysis (Worst Day)\n")
        if not df_all.empty:
            f.write(f"On {worst_day}, the portfolio lost {worst_day_pnl:.2f}.\n")
            f.write("Breakdown:\n")
            for name in strategies.keys():
                if name in df_all.columns:
                    strat_pnl = row[name] - prev_row[name]
                    f.write(f"- **{name}**: {strat_pnl:.2f}\n")
                else:
                    f.write(f"- **{name}**: N/A\n")

        f.write("\n### Recommendations\n")
        f.write("1. **Adaptive Sizing**: Ensure strategies reduce size during high volatility (VIX > 25).\n")
        f.write("2. **Correlation**: Diversify across non-correlated assets (e.g., Gold/Silver during Equity Crash).\n")
        f.write("3. **Circuit Breakers**: Implement daily loss limits (e.g., stop trading if Portfolio DD > 2%).\n")

if __name__ == "__main__":
    main()
