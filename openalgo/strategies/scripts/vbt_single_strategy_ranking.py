import vectorbt as vbt
from curl_cffi import requests

def main():
    session = requests.Session(impersonate='chrome')

    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    data = vbt.YFData.download(
        symbol,
        period="1y",
        missing_index="drop",
        ticker_kwargs=dict(session=session)
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest...")

    # Using vbt.MA.run
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

    total_returns = pf.total_return()

    print("\n--- Strategy Performance Ranking ---")

    # total_returns is a scalar float when testing a single symbol without param combinations
    if isinstance(total_returns, float):
        ret_pct = total_returns * 100
    else:
        # Fallback if it returns a pandas Series
        ret_pct = total_returns.iloc[0] * 100 if hasattr(total_returns, 'iloc') else float(total_returns) * 100

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
