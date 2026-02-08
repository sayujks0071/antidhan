import re
from datetime import datetime

log_file = "logs/openalgo.log"

def parse_logs():
    latencies = []
    last_signal_time = None

    try:
        with open(log_file, "r") as f:
            for line in f:
                # Extract timestamp
                match = re.search(r"\[(.*?)\]", line)
                if not match:
                    continue

                timestamp_str = match.group(1)
                try:
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f")
                except ValueError:
                    continue

                if "Signal Generated" in line:
                    last_signal_time = timestamp
                elif "Order Placed" in line and last_signal_time:
                    latency = (timestamp - last_signal_time).total_seconds() * 1000
                    latencies.append(latency)
                    print(f"Latency: {latency:.2f}ms")
                    last_signal_time = None # Reset
    except FileNotFoundError:
        print(f"Log file {log_file} not found.")
        return

    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        print(f"\nAverage Latency: {avg_latency:.2f}ms")
        if avg_latency > 500:
            print("❌ Latency exceeds 500ms!")
        else:
            print("✅ Latency is acceptable (<500ms).")
    else:
        print("No signal/order pairs found.")

if __name__ == "__main__":
    parse_logs()
