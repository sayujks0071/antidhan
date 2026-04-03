import vectorbt as vbt
import numpy as np

def main():
    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    data = vbt.YFData.download(
        symbol,
        period="1y",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    fast_ma = vbt.MA.run(price, 10)
    slow_ma = vbt.MA.run(price, 50)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        freq="1D"
    )

    total_return = pf.total_return()

    ret_val = float(total_return)
    ret_pct = ret_val * 100

    if ret_pct > 50:
        rank = "Premium"
    elif ret_pct >= 10:
        rank = "Moderate"
    else:
        rank = "Low"

    print(f"Symbol: {symbol}")
    print(f"Total Return: {ret_pct:.2f}%")
    print(f"Rank: {rank}")

if __name__ == "__main__":
    main()
