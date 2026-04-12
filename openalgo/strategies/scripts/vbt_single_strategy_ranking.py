import vectorbt as vbt
import numpy as np
from curl_cffi import requests

def rank_strategy(total_return):
    """
    Rank strategy based on total return:
    Premium: > 50%
    Moderate: >= 10% and <= 50%
    Low: < 10%
    """
    if total_return > 0.50:
        return "Premium"
    elif total_return >= 0.10:
        return "Moderate"
    else:
        return "Low"

def main():
    session = requests.Session(impersonate="chrome")
    # Using ticker_kwargs as new in 0.28
    data = vbt.YFData.download(
        "BTC-USD",
        period="2y",
        ticker_kwargs=dict(session=session)
    )
    price = data.get("Close")

    fast_ma = vbt.MA.run(price, 10)
    slow_ma = vbt.MA.run(price, 50)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=100, freq="1D")

    total_ret = float(pf.total_return())

    ranking = rank_strategy(total_ret)

    print(f"Total Return: {total_ret:.2%}")
    print(f"Strategy Ranking: {ranking}")

if __name__ == "__main__":
    main()
