import vectorbt as vbt
import numpy as np

def main():
    # Backtest a single strategy and rank the strategy as premium, moderate, low based on result

    # 1. Download Data
    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    # In vectorbt 0.28+, ticker_kwargs accepts yfinance init params like 'session'
    data = vbt.YFData.download(
        symbol,
        period="1y",
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest for single symbol...")
    # Define SMA windows
    fast_window = 10
    slow_window = 50

    # Calculate MAs
    fast_ma = vbt.MA.run(price, fast_window)
    slow_ma = vbt.MA.run(price, slow_window)

    # Generate crossover signals
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # 2. Portfolio Backtest
    # Need to specify freq="1D" to prevent UserWarnings during metrics generation
    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        freq="1D"
    )

    # 3. Handle Single Symbol Metric
    # In VectorBT 0.28+, when backtesting a single symbol and parameterless strategy,
    # metrics like total_return() natively return a scalar float (e.g., numpy.float64)
    # rather than a pandas Series or DataFrame.
    total_return = pf.total_return()

    print("\n--- Strategy Performance Ranking ---")

    # Ensure we get the correct percentage format
    # total_return is typically a fraction (e.g., 0.15 for 15%)
    ret_pct = total_return * 100

    # 4. Determine Rank
    # Premium (>50%), Moderate (>=10%), and Low (<10%)
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
