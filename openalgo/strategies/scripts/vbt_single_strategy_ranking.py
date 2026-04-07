import vectorbt as vbt
import pandas_ta_classic as ta
import pandas as pd

def main():
    # 1. Single symbol backtest
    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    # 2. VectorBT 0.28+ specifics:
    # - period passed directly
    # - ticker_kwargs contains only valid yfinance.Ticker parameters (like session)
    data = vbt.YFData.download(
        symbol,
        period="1y",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    # We can use pandas-ta-classic for indicators explicitly
    fast_ma = ta.sma(price, length=10)
    slow_ma = ta.sma(price, length=50)

    # Check if they are None/empty
    if fast_ma is None or slow_ma is None:
        # Fallback to vectorbt's MA
        fast_ma = vbt.MA.run(price, 10).ma
        slow_ma = vbt.MA.run(price, 50).ma

    # Create signals
    entries = (fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1))
    exits = (fast_ma < slow_ma) & (fast_ma.shift(1) >= slow_ma.shift(1))

    # 4. Create Portfolio
    # freq is specified to prevent warnings
    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        freq="1D"
    )

    # 5. Handle single-symbol metric (scalar float natively returned in vbt 0.28+)
    ret = pf.total_return()
    ret_pct = float(ret) * 100

    # 6. Rank the strategy
    if ret_pct > 50:
        rank = "Premium"
    elif ret_pct >= 10:
        rank = "Moderate"
    else:
        rank = "Low"

    print("\n--- Strategy Performance Ranking ---")
    print(f"Symbol: {symbol}")
    print(f"Total Return: {ret_pct:.2f}%")
    print(f"Rank: {rank}")
    print("-" * 30)

    # Mention Plotly 6 support
    print("\nPlotly 6 is supported for visualization (e.g., pf.plot().show()).")

if __name__ == "__main__":
    main()
