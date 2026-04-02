import re

LOG_FILE = "logs/openalgo.log"
REPORT_FILE = "DAILY_PERFORMANCE.md"

def calculate_slippage():
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print("Log file not found.")
        return

    # Map symbol -> {'side': 'BUY'/'SELL', 'price': float}
    signal_map = {}
    slippage_data = {} # symbol -> list of slippage values

    # Regex
    # Signal Generated: BUY NIFTY at 2400.00
    signal_pattern = re.compile(r"Signal Generated: (BUY|SELL) (.*) at (\d+\.\d+)")
    # Order Placed: NIFTY. Fill Price: 2400.50
    order_pattern = re.compile(r"Order Placed: (.*)\. Fill Price: (\d+\.\d+)")

    for line in lines:
        signal_match = signal_pattern.search(line)
        if signal_match:
            side, symbol, price_str = signal_match.groups()
            symbol = symbol.strip()
            signal_map[symbol] = {'side': side, 'price': float(price_str)}
            continue

        order_match = order_pattern.search(line)
        if order_match:
            symbol, fill_price_str = order_match.groups()
            symbol = symbol.strip()
            fill_price = float(fill_price_str)

            if symbol in signal_map:
                signal_data = signal_map[symbol]
                signal_price = signal_data['price']
                side = signal_data['side']

                slippage = 0.0
                if side == 'BUY':
                    slippage = fill_price - signal_price
                elif side == 'SELL':
                    slippage = signal_price - fill_price

                if symbol not in slippage_data:
                    slippage_data[symbol] = []
                slippage_data[symbol].append(slippage)

                print(f"{symbol} {side}: Signal {signal_price} -> Fill {fill_price}. Slippage: {slippage:.2f}")

    with open(REPORT_FILE, "a") as f:
        f.write("\n## Slippage Check\n")
        if slippage_data:
            f.write("Average Slippage per Symbol:\n")
            for symbol, values in slippage_data.items():
                avg_slippage = sum(values) / len(values)
                f.write(f"- **{symbol}**: {avg_slippage:.2f} pts\n")
        else:
            f.write("No slippage data calculated.\n")

if __name__ == "__main__":
    calculate_slippage()
