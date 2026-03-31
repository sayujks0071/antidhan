"""
CHANGELOG:
- 2024-05-20: Initial creation of VectorBT 0.28+ single strategy ranking.
"""
import vectorbt as vbt
import numpy as np

def run_backtest_and_rank():
    symbol = "BTC-USD"

    # In vectorbt 0.28+, period is passed directly, and ticker_kwargs for YF Ticker
    data = vbt.YFData.download(
        symbol,
        period="4y",
        missing_index="drop"
    )
    price = data.get("Close")

    # Dual SMA crossover strategy
    fast_ma = vbt.MA.run(price, window=10)
    slow_ma = vbt.MA.run(price, window=50)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Portfolio setup
    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=100)

    # Extract total return
    # In vbt 0.28+, total_return() on single-symbol parameterless returns a scalar float
    total_ret = pf.total_return()

    # Ensure it's a float for comparisons
    total_ret_float = float(total_ret)

    # Ranking logic based on OpenAlgo guidelines:
    # Premium (>50%), Moderate (>=10%), Low (<10%)
    if total_ret_float > 0.50:
        ranking = "Premium"
    elif total_ret_float >= 0.10:
        ranking = "Moderate"
    else:
        ranking = "Low"

    print(f"Symbol: {symbol}")
    print(f"Total Return: {total_ret_float * 100:.2f}%")
    print(f"Strategy Ranking: {ranking}")

    return ranking, total_ret_float

if __name__ == "__main__":
    run_backtest_and_rank()
