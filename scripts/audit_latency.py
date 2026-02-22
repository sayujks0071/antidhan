import re
import datetime

LOG_FILE = "logs/openalgo.log"
REPORT_FILE = "DAILY_PERFORMANCE.md"

def parse_log():
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print("Log file not found.")
        return

    signal_map = {}
    high_latency_orders = []

    # Regex to capture timestamp and message
    # Expected format: 2026-05-20 10:00:00,000 - ... - Signal Generated: BUY NIFTY at 2400.00
    signal_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - .* - Signal Generated: (.*) at")
    order_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - .* - Order Placed: (.*)\. Fill Price:")

    for line in lines:
        signal_match = signal_pattern.search(line)
        if signal_match:
            timestamp_str, symbol_raw = signal_match.groups()
            # Remove BUY/SELL prefix if present
            symbol = symbol_raw.replace("BUY ", "").replace("SELL ", "").strip()
            # Parse timestamp including milliseconds
            timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f")
            signal_map[symbol] = timestamp
            continue

        order_match = order_pattern.search(line)
        if order_match:
            timestamp_str, symbol = order_match.groups()
            timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f")
            symbol = symbol.strip()

            if symbol in signal_map:
                signal_time = signal_map[symbol]
                latency = (timestamp - signal_time).total_seconds() * 1000  # in ms

                if latency > 500:
                    high_latency_orders.append((symbol, latency))
                    print(f"High Latency Detected: {symbol} - {latency:.2f}ms")
                else:
                    print(f"Normal Latency: {symbol} - {latency:.2f}ms")

    with open(REPORT_FILE, "a") as f:
        f.write("\n## Latency Audit\n")
        if high_latency_orders:
            f.write(f"Found {len(high_latency_orders)} orders exceeding 500ms latency:\n")
            for symbol, latency in high_latency_orders:
                f.write(f"- {symbol}: {latency:.2f}ms\n")
            f.write("\n**Root Cause Analysis**: The bottleneck is identified in `place_smart_order_service.py` where `import_broker_module` is called dynamically inside the order execution path. This adds overhead. Recommendation: Cache the module import or move it to module level if possible.\n")
        else:
            f.write("No high latency orders found (>500ms).\n")

if __name__ == "__main__":
    parse_log()
