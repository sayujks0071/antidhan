import vectorbt as vbt
import numpy as np

def run_backtest(symbol="BTC-USD", period="1y", fast_window=10, slow_window=50):
    # Download data using VectorBT 0.28+ API
    data = vbt.YFData.download(symbol, period=period)
    price = data.get("Close")

    # Calculate moving averages
    fast_ma = vbt.MA.run(price, fast_window)
    slow_ma = vbt.MA.run(price, slow_window)

    # Generate signals
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Run backtest
    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=100)

    # Get total return
    total_ret = pf.total_return()

    # Handle scalar return values for parameterless indicators/single symbol
    if isinstance(total_ret, float) or isinstance(total_ret, np.floating):
        ret_val = float(total_ret)
    else:
        # In case it returns a Series due to some multi-index, we get the scalar
        ret_val = float(total_ret.iloc[0])

    ret_pct = ret_val * 100

    # Rank strategy based on total return
    if ret_pct > 50:
        rank = "Premium"
    elif ret_pct >= 10:
        rank = "Moderate"
    else:
        rank = "Low"

    print(f"Symbol: {symbol}")
    print(f"Total Return: {ret_pct:.2f}%")
    print(f"Strategy Ranking: {rank}")

    return pf, rank

if __name__ == "__main__":
    run_backtest()
