import re
from datetime import datetime
from collections import defaultdict

def analyze(log_file):
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error: {e}")
        return

    # To track matching signals
    signal_map = {}
    latencies = []
    slippages = defaultdict(list)
    signals_list = []

    # Patterns
    sig_vwap = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) INFO VWAP Crossover Buy\. Price: ([\d\.]+), .* RSI: ([\d\.]+), EMA_Fast: ([\d\.]+), EMA_Slow: ([\d\.]+)")
    sig_legacy = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) INFO Signal Generated: BUY (\w+) @ ([\d\.]+)")

    order_pat = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) INFO Order Placed: BUY (\w+)")
    fill_pat = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) INFO Order Filled: BUY (\w+) @ ([\d\.]+)")

    for line in lines:
        mv = sig_vwap.search(line)
        if mv:
            ts, price, rsi, ema_f, ema_s = mv.groups()
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S,%f")
            signal_map["NIFTY"] = {"ts": dt, "price": float(price)}
            signals_list.append({"symbol": "NIFTY", "time": dt, "price": float(price), "rsi": float(rsi), "ema_fast": float(ema_f), "ema_slow": float(ema_s)})
            continue

        ml = sig_legacy.search(line)
        if ml:
            ts, sym, price = ml.groups()
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S,%f")
            signal_map[sym] = {"ts": dt, "price": float(price)}
            signals_list.append({"symbol": sym, "time": dt, "price": float(price)})
            continue

        mo = order_pat.search(line)
        if mo:
            ts, sym = mo.groups()
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S,%f")
            if sym in signal_map:
                sig_ts = signal_map[sym]["ts"]
                diff = (dt - sig_ts).total_seconds() * 1000
                if diff < 5000: # 5 secs limit for validity
                    latencies.append((sym, diff))
            continue

        mf = fill_pat.search(line)
        if mf:
            ts, sym, price = mf.groups()
            if sym in signal_map:
                sig_p = signal_map[sym]["price"]
                slip = float(price) - sig_p
                slippages[sym].append(slip)

    if latencies:
        avg_lat = sum(l[1] for l in latencies) / len(latencies)
        print(f"Average Latency: {avg_lat:.2f} ms")
        for sym, lat in latencies:
            if lat > 500:
                print(f"  [WARNING] Bottleneck for {sym}: {lat:.2f} ms")
    else:
        print("No latencies found.")

    print("\nSlippages:")
    for sym, slips in slippages.items():
        avg_s = sum(slips) / len(slips)
        print(f"  {sym}: {avg_s:.2f} pts")

    print(f"\nLast 3 Market Buy Signals:")
    last_3 = [s for s in signals_list if s['symbol'] == 'NIFTY'][-3:]
    for s in last_3:
         print(f"  {s['time']} | {s['symbol']} Price: {s['price']} | RSI: {s.get('rsi')} | EMA Fast: {s.get('ema_fast')} | EMA Slow: {s.get('ema_slow')}")

if __name__ == '__main__':
    analyze('logs/mock_openalgo.log')
