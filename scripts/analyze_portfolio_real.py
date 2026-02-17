import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add paths
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'scripts'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'utils'))

from trading_utils import APIClient
from base_strategy import BaseStrategy

# Import Strategies
try:
    import supertrend_vwap_strategy
    import ai_hybrid_reversion_breakout
    import mcx_commodity_momentum_strategy
except ImportError as e:
    print(f"Error importing strategies: {e}")
    sys.exit(1)

def main():
    print("Initializing Correlation Analysis...")
    client = APIClient(api_key="ANALYSIS")

    # 1. Fetch Real Data (NIFTY 50, 15m, 30 days)
    symbol = "NIFTY"
    exchange = "NSE"
    interval = "15m"
    days = 30

    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    print(f"Fetching data for {symbol} ({start_date} to {end_date})...")
    df = client.history(symbol, exchange, interval, start_date, end_date)

    if df.empty:
        print("Error: No data fetched. Using Mock Data for analysis.")
        # Fallback to mock data
        # Use '15min' for pandas frequency (15m is ambiguous/deprecated)
        freq = "15min" if interval == "15m" else interval
        dates = pd.date_range(end=datetime.now(), periods=days*75, freq=freq)
        df = pd.DataFrame(index=dates)
        df['close'] = 100 + np.random.randn(len(dates)).cumsum()
        df['open'] = df['close'] + np.random.randn(len(dates))
        df['high'] = df[['open', 'close']].max(axis=1) + 1
        df['low'] = df[['open', 'close']].min(axis=1) - 1
        df['volume'] = np.random.randint(1000, 100000, len(dates))
        df['datetime'] = df.index
    else:
        print(f"Loaded {len(df)} bars.")

    # 2. Define Strategies to Test
    strategies = {
        'SuperTrendVWAP': supertrend_vwap_strategy,
        'AIHybrid': ai_hybrid_reversion_breakout,
        'MCXMomentum': mcx_commodity_momentum_strategy
    }

    signals = {}

    # 3. Generate Signals
    print("Generating Signals...")
    # Use a rolling window to simulate live trading?
    # generate_signal usually takes a DF and returns signal for the last bar.
    # To be accurate, we must iterate. This is slow but correct.
    # We'll skip the first 50 bars.

    for name, module in strategies.items():
        print(f"  Processing {name}...")
        strat_signals = []

        # We need a client instance for strategy if it needs it (e.g. for extra data fetching)
        # We'll pass the same client.

        # Optimization: Don't iterate every bar if slow.
        # But for 30 days of 15m data (approx 30 * 25 = 750 bars), it's fast enough.

        for i in range(50, len(df)):
            window = df.iloc[:i+1]
            try:
                # generate_signal is module level
                if hasattr(module, 'generate_signal'):
                    action, score, details = module.generate_signal(
                        window,
                        client=client,
                        symbol=symbol
                    )

                    val = 0
                    if action == 'BUY': val = 1
                    elif action == 'SELL': val = -1

                    strat_signals.append(val)
                else:
                    strat_signals.append(0)
            except Exception as e:
                # print(f"Error: {e}")
                strat_signals.append(0)

        signals[name] = strat_signals

    # 4. Correlation Analysis
    # Ensure all lengths match
    min_len = min(len(s) for s in signals.values())
    data = {k: v[:min_len] for k, v in signals.items()}

    df_signals = pd.DataFrame(data)

    print("\n" + "="*50)
    print("CORRELATION MATRIX")
    print("="*50)
    corr_matrix = df_signals.corr()
    print(corr_matrix)

    print("\nAnalysis Results:")
    found_high_corr = False
    for i in range(len(corr_matrix.columns)):
        for j in range(i+1, len(corr_matrix.columns)):
            s1 = corr_matrix.columns[i]
            s2 = corr_matrix.columns[j]
            val = corr_matrix.iloc[i, j]

            if abs(val) > 0.7:
                print(f"⚠️  High Correlation detected between {s1} and {s2}: {val:.2f}")
                print(f"   Action: Merge into 'Hybrid' strategy or keep higher Calmar Ratio.")
                found_high_corr = True

    if not found_high_corr:
        print("✅ No high correlation (>0.7) detected between active strategies.")

if __name__ == "__main__":
    main()
