import vectorbt as vbt

def main():
    # Backtest a single symbol with parameterless strategy
    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    # Use ticker_kwargs correctly for yfinance. VectorBT 0.28+ directly accepts period parameter
    data = vbt.YFData.download(
        symbol,
        period="1y",
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest...")
    fast_window = 10
    slow_window = 50

    fast_ma = vbt.MA.run(price, fast_window)
    slow_ma = vbt.MA.run(price, slow_window)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Need to specify freq="1D" to prevent UserWarnings during metrics generation
    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        freq="1D"
    )

    # For single symbol parameterless strategy, total_return() returns a scalar float in VectorBT 0.28+
    total_ret = pf.total_return()

    print("\n--- Strategy Performance Ranking ---")
    ret_pct = float(total_ret) * 100

    if ret_pct > 50:
        rank = "Premium"
    elif ret_pct >= 10:
        rank = "Moderate"
    else:
        rank = "Low"

    print(f"Symbol: {symbol}")
    print(f"Total Return: {ret_pct:.2f}%")
    print(f"Rank: {rank}")
    print("-" * 30)

if __name__ == "__main__":
    main()
