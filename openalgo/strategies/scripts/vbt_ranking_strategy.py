import vectorbt as vbt
import warnings
import sys

def main():
    # Backtest a Dual SMA strategy on BTC-USD
    symbols = ["BTC-USD"]

    # In VectorBT 0.28+, we can pass ticker_kwargs to yfinance.Ticker
    # Using an empty dict or valid ticker_kwargs
    data = vbt.YFData.download(
        symbols,
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    # Compute 10-day and 50-day SMAs
    fast_ma = vbt.MA.run(price, 10)
    slow_ma = vbt.MA.run(price, 50)

    # Generate entry and exit signals
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Run the backtest using Portfolio.from_signals
    # The 'freq' parameter must be specified to prevent UserWarnings during metrics generation
    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=100, freq="1D")

    # Get the total return (this is a float when evaluating a single strategy/symbol)
    total_return = pf.total_return()

    if hasattr(total_return, "iloc"):
        ret_val = total_return.iloc[0]
    else:
        ret_val = float(total_return)

    # Convert to percentage
    ret_pct = ret_val * 100

    # Rank strategy performance:
    # Premium (>50%), Moderate (10-50%), and Low (<10%)
    if ret_pct > 50:
        rank = "Premium"
    elif ret_pct >= 10:
        rank = "Moderate"
    else:
        rank = "Low"

    print(f"Total Return: {ret_pct:.2f}%")
    print(f"Strategy Rank: {rank}")

if __name__ == "__main__":
    main()
