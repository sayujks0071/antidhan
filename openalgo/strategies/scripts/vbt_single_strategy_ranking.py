import vectorbt as vbt
import numpy as np

def run_backtest_and_rank():
    # Backtest a single symbol using Dual SMA crossover
    data = vbt.YFData.download("BTC-USD", period="5y")
    price = data.get("Close")

    # Fast and slow SMA
    fast_ma = vbt.MA.run(price, 10)
    slow_ma = vbt.MA.run(price, 50)
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=100)

    # Calculate total return
    # total_return() natively returns a scalar float (numpy.float64) in VectorBT 0.28+
    # for a single symbol and parameterless strategy.
    ret = pf.total_return()

    # Evaluate total return (ret is a fraction, e.g. 0.50 means +50%)
    if ret > 0.50:
        ranking = "Premium"
    elif ret >= 0.10:
        ranking = "Moderate"
    else:
        ranking = "Low"

    print(f"Total Return: {ret:.2%}")
    print(f"Strategy Ranking: {ranking}")

    return ranking, ret

if __name__ == "__main__":
    run_backtest_and_rank()
