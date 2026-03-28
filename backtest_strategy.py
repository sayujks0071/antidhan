import vectorbt as vbt
import pandas_ta_classic as ta

def run_backtest():
    print("Downloading data...")
    # New in 0.28: ticker_kwargs
    data = vbt.YFData.download(
        "BTC-USD",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running strategy (10/50 SMA Crossover)...")
    fast_ma = vbt.MA.run(price, 10)
    slow_ma = vbt.MA.run(price, 50)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=100)

    # In VectorBT 0.28+, metrics like total_return() natively return a scalar float
    total_return = float(pf.total_return())

    print(f"Total Return: {total_return * 100:.2f}%")

    # Rank based on OpenAlgo thresholds
    # Premium (>50%), Moderate (>=10%), and Low (<10%).
    if total_return > 0.5:
        rank = "Premium"
    elif total_return >= 0.1:
        rank = "Moderate"
    else:
        rank = "Low"

    print(f"Strategy Rank: {rank}")
    return rank

if __name__ == "__main__":
    run_backtest()
