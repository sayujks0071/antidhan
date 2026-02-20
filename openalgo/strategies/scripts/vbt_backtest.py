import vectorbt as vbt

def run_backtest(symbol="BTC-USD", period="2y"):
    """
    Backtests a simple Dual SMA Crossover strategy using vectorbt.
    Ranks the strategy based on Sharpe Ratio and Total Return.
    """
    print(f"Backtesting {symbol} for {period}...")

    # 1. Download Data
    try:
        # Using vbt.YFData.download as per v0.28+
        data = vbt.YFData.download(symbol, period=period)
        price = data.get("Close")
    except Exception as e:
        print(f"Error downloading data: {e}")
        return

    if price.empty:
        print("No data found.")
        return

    # 2. Strategy Logic: Dual SMA Crossover
    fast_window = 10
    slow_window = 50

    fast_ma = vbt.MA.run(price, fast_window)
    slow_ma = vbt.MA.run(price, slow_window)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # 3. Run Portfolio
    # init_cash=10000, freq='1D' (assuming daily data from YF)
    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=10000, freq="1D")

    # 4. Calculate Metrics
    total_return = pf.total_return() * 100 # Convert to percentage
    sharpe_ratio = pf.sharpe_ratio()

    # 5. Rank Strategy
    # Default Ranking Logic:
    # Premium: Sharpe > 1.5 AND Total Return > 50%
    # Moderate: Sharpe > 1.0 AND Total Return > 20%
    # Low: Otherwise
    rank = "Low"
    if sharpe_ratio > 1.5 and total_return > 50:
        rank = "Premium"
    elif sharpe_ratio > 1.0 and total_return > 20:
        rank = "Moderate"

    # 6. Print Results
    print("-" * 40)
    print(f"Strategy: Dual SMA ({fast_window}/{slow_window})")
    print(f"Symbol: {symbol}")
    print(f"Period: {period}")
    print("-" * 40)

    # Print full stats using vectorbt's built-in stats method
    try:
        print(pf.stats())
    except Exception as e:
        print(f"Could not print full stats: {e}")
        print(f"Total Return: {total_return:.2f}%")
        print(f"Sharpe Ratio: {sharpe_ratio:.2f}")

    print("-" * 40)
    print(f"Strategy Rank: {rank}")
    print("-" * 40)

if __name__ == "__main__":
    run_backtest()
