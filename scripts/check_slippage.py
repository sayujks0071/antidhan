import re

log_file = "logs/openalgo.log"

def check_slippage():
    slippages = {}
    last_signal_price = {}

    try:
        with open(log_file, "r") as f:
            for line in f:
                # Signal Generated: BUY NIFTY @ 22100.00
                match_signal = re.search(r"Signal Generated: .*? (.*?) @ ([\d\.]+)", line)
                if match_signal:
                    symbol = match_signal.group(1)
                    price = float(match_signal.group(2))
                    last_signal_price[symbol] = price
                    continue

                # Fill Confirmation: BUY NIFTY @ 22105.00
                match_fill = re.search(r"Fill Confirmation: .*? (.*?) @ ([\d\.]+)", line)
                if match_fill:
                    symbol = match_fill.group(1)
                    fill_price = float(match_fill.group(2))

                    if symbol in last_signal_price:
                        signal_price = last_signal_price[symbol]
                        slippage = abs(fill_price - signal_price)

                        if symbol not in slippages:
                            slippages[symbol] = []
                        slippages[symbol].append(slippage)

                        print(f"{symbol}: Signal {signal_price} -> Fill {fill_price} (Slippage: {slippage:.2f})")
                        del last_signal_price[symbol]
    except FileNotFoundError:
        print(f"Log file {log_file} not found.")
        return []

    print("\n--- Average Slippage ---")
    results = []
    for symbol, values in slippages.items():
        avg = sum(values) / len(values)
        res = f"{symbol}: {avg:.2f}"
        print(res)
        results.append(res)

    return results

if __name__ == "__main__":
    check_slippage()
