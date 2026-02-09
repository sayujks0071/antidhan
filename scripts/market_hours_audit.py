import os
import re
import logging
import argparse
from datetime import datetime, timedelta
import random

# Ensure logs directory exists
if not os.path.exists("logs"):
    os.makedirs("logs")

LOG_FILE = "logs/mock_openalgo.log"

def setup_logger(filepath):
    # clean up previous log if mocking
    if filepath == "logs/mock_openalgo.log" and os.path.exists(filepath):
        os.remove(filepath)

    logging.basicConfig(filename=filepath, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', force=True)
    return logging.getLogger()

def generate_mock_logs(filepath):
    print(f"Generating mock logs at {filepath}...")
    setup_logger(filepath)
    global LOG_FILE
    LOG_FILE = filepath

    # Simulate 3 trade cycles for NIFTY (SuperTrendVWAPStrategy) to verify logic
    # And keep existing cycles for other symbols for variety

    start_time = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)

    # NIFTY Signals (3 signals)
    nifty_signals = []
    for i in range(3):
        ts = start_time + timedelta(minutes=i*30)
        price = 24500 + (i * 100)
        vwap = price - 50
        poc = price - 20
        vol = 150000 + (i * 1000)
        dev = 0.002 * (i + 1)
        vix = 14.5 + (i * 0.1)
        qty = 25
        # RSI/EMA for verification
        rsi = 55 + (i * 2) # Rising RSI > 50
        ema_fast = price - 10
        ema_slow = price - 40 # EMA Fast > EMA Slow
        nifty_signals.append({
            'symbol': 'NIFTY',
            'time': ts,
            'price': price,
            'vwap': vwap,
            'poc': poc,
            'vol': vol,
            'dev': dev,
            'vix': vix,
            'qty': qty,
            'rsi': rsi,
            'ema_fast': ema_fast,
            'ema_slow': ema_slow
        })

    # Other Signals (Legacy)
    other_signals = [
        {'symbol': 'BANKNIFTY', 'time': start_time + timedelta(minutes=10), 'price': 52000.0},
        {'symbol': 'RELIANCE', 'time': start_time + timedelta(minutes=45), 'price': 2500.0}
    ]

    all_signals = nifty_signals + other_signals
    all_signals.sort(key=lambda x: x['time'])

    with open(filepath, "a") as f:
        for sig in all_signals:
            symbol = sig['symbol']
            signal_time = sig['time']
            signal_price = sig['price']

            if symbol == 'NIFTY':
                # VWAP Strategy Format with RSI/EMA
                # log: VWAP Crossover Buy. Price: {price}, POC: {poc}, Vol: {vol}, Sector: Bullish, Dev: {dev}, Qty: {qty} (VIX: {vix}), RSI: {rsi}, EMA_Fast: {ema_fast}, EMA_Slow: {ema_slow}
                log_line = f"{signal_time.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} INFO VWAP Crossover Buy. Price: {signal_price:.2f}, POC: {sig['poc']:.2f}, Vol: {sig['vol']}, Sector: Bullish, Dev: {sig['dev']:.4f}, Qty: {sig['qty']} (VIX: {sig['vix']:.1f}), RSI: {sig['rsi']:.2f}, EMA_Fast: {sig['ema_fast']:.2f}, EMA_Slow: {sig['ema_slow']:.2f}\n"
                f.write(log_line)
                # Execute log
                f.write(f"{signal_time.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} INFO Executing BUY {sig['qty']} {symbol} @ {signal_price:.2f}\n")
            else:
                # Legacy Format
                f.write(f"{signal_time.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} INFO Signal Generated: BUY {symbol} @ {signal_price}\n")

            # Latency: Random between 50ms and 600ms
            latency_ms = random.randint(50, 450) # Mostly good latency
            if symbol == 'RELIANCE': latency_ms = random.randint(400, 600) # simulate slight bottleneck

            order_time = signal_time + timedelta(milliseconds=latency_ms)
            f.write(f"{order_time.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} INFO Order Placed: BUY {symbol}\n")

            # Fill: Slippage random -2 to +5
            slippage = random.uniform(-1.0, 3.0)
            fill_price = signal_price + slippage
            fill_time = order_time + timedelta(milliseconds=200) # Execution time
            f.write(f"{fill_time.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} INFO Order Filled: BUY {symbol} @ {fill_price:.2f}\n")

def analyze_logs(filepath):
    print(f"\nAnalyzing logs from {filepath}...")

    latency_records = []
    slippage_records = []
    vwap_signals = [] # Store full data for verification

    try:
        with open(filepath, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Log file {filepath} not found.")
        return

    signal_map = {} # Store signal time and price by symbol (latest)

    # Regex patterns
    signal_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) INFO Signal Generated: BUY (\w+) @ ([\d\.]+)")
    # VWAP pattern with capturing groups for verification (updated for RSI/EMA)
    vwap_signal_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) INFO VWAP Crossover Buy. Price: ([\d\.]+), POC: ([\d\.]+), Vol: (\d+), Sector: (\w+), Dev: ([\d\.]+), Qty: (\d+) \(VIX: ([\d\.]+)\), RSI: ([\d\.]+), EMA_Fast: ([\d\.]+), EMA_Slow: ([\d\.]+)")
    order_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) INFO Order Placed: BUY (\w+)")
    fill_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) INFO Order Filled: BUY (\w+) @ ([\d\.]+)")

    for line in lines:
        # Check Signal (Legacy)
        m_sig = signal_pattern.search(line)
        if m_sig:
            ts_str, symbol, price = m_sig.groups()
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
            signal_map[symbol] = {'signal_time': ts, 'signal_price': float(price)}
            continue

        # Check Signal (VWAP Strategy)
        m_vwap = vwap_signal_pattern.search(line)
        if m_vwap:
            ts_str, price, poc, vol, sector, dev, qty, vix, rsi, ema_fast, ema_slow = m_vwap.groups()
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
            symbol = "NIFTY"
            signal_data = {
                'signal_time': ts,
                'signal_price': float(price),
                'poc': float(poc),
                'vol': int(vol),
                'sector': sector,
                'dev': float(dev),
                'vix': float(vix),
                'rsi': float(rsi),
                'ema_fast': float(ema_fast),
                'ema_slow': float(ema_slow)
            }
            signal_map[symbol] = signal_data # Update map for latency check
            vwap_signals.append(signal_data) # Store for logic verification
            continue

        # Check Order (Latency)
        m_ord = order_pattern.search(line)
        if m_ord:
            ts_str, symbol = m_ord.groups()
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
            if symbol in signal_map:
                # Check if this order matches the latest signal (approx time check)
                sig_ts = signal_map[symbol]['signal_time']
                if abs((ts - sig_ts).total_seconds()) < 5: # Match within 5 seconds
                    latency_ms = (ts - sig_ts).total_seconds() * 1000
                    latency_records.append({'symbol': symbol, 'latency': latency_ms, 'ts': ts})
            continue

        # Check Fill (Slippage)
        m_fill = fill_pattern.search(line)
        if m_fill:
            ts_str, symbol, price = m_fill.groups()
            fill_price = float(price)
            if symbol in signal_map:
                 sig_price = signal_map[symbol]['signal_price']
                 slippage = fill_price - sig_price
                 slippage_records.append({'symbol': symbol, 'slippage': slippage})

    # Report Latency
    print("\n--- Latency Audit ---")
    total_latency = 0
    for rec in latency_records:
        print(f"[{rec['ts'].strftime('%H:%M:%S')}] Symbol: {rec['symbol']}, Latency: {rec['latency']:.2f} ms")
        total_latency += rec['latency']
        if rec['latency'] > 500:
            print("  [WARNING] Latency > 500ms! Bottleneck investigation required.")

    if latency_records:
        avg_latency = total_latency / len(latency_records)
        print(f"Average Latency: {avg_latency:.2f} ms")

    # Report Slippage
    print("\n--- Slippage Check ---")
    total_slippage = 0
    for rec in slippage_records:
        print(f"Symbol: {rec['symbol']}, Slippage: {rec['slippage']:.2f} pts")
        total_slippage += rec['slippage']

    if slippage_records:
        avg_slippage = total_slippage / len(slippage_records)
        print(f"Average Slippage: {avg_slippage:.2f} pts")

    # Logic Verification (VWAP Strategy)
    print("\n--- Logic Verification ---")
    print(f"Strategy: SuperTrendVWAPStrategy (NIFTY) - Verifying {len(vwap_signals)} signals")

    for i, sig in enumerate(vwap_signals):
        print(f"\nSignal #{i+1} at {sig['signal_time'].strftime('%H:%M:%S')}")

        # Verify Logic based on extracted log data
        # Logic: Price > POC, Sector Bullish, Dev within limit

        close_price = sig['signal_price']
        poc_price = sig['poc']
        sector_bullish = (sig['sector'] == 'Bullish')
        dev_val = sig['dev']
        dev_threshold = 0.03

        # Infer VWAP from deviation or assume valid because it triggered
        # Dev = (Close - VWAP) / VWAP => VWAP = Close / (1 + Dev)
        vwap_inferred = close_price / (1 + dev_val)

        is_above_poc = close_price > poc_price
        is_not_overextended = abs(dev_val) < dev_threshold

        print(f"  Close: {close_price:.2f}, Inferred VWAP: {vwap_inferred:.2f}")
        print(f"  POC: {poc_price:.2f} (Above: {is_above_poc})")
        print(f"  Sector: {sig['sector']} (Bullish: {sector_bullish})")
        print(f"  Dev: {dev_val:.4f} (Within {dev_threshold}: {is_not_overextended})")

        # RSI/EMA Verification
        rsi_val = sig['rsi']
        ema_fast = sig['ema_fast']
        ema_slow = sig['ema_slow']
        ema_trend = ema_fast > ema_slow
        rsi_bullish = rsi_val > 50

        print(f"  RSI: {rsi_val:.2f} (Bullish > 50: {rsi_bullish})")
        print(f"  EMA Trend: {ema_trend} (Fast {ema_fast:.2f} > Slow {ema_slow:.2f})")

        if is_above_poc and sector_bullish and is_not_overextended and rsi_bullish and ema_trend:
             print("  Result: Signal Validated: YES (Mathematically Accurate)")
        else:
             print("  Result: Signal Validated: NO (Logic Mismatch)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit Market Hours Performance")
    parser.add_argument("--log-file", help="Path to log file to analyze", default="logs/openalgo.log")
    parser.add_argument("--mock", action="store_true", help="Force mock data generation")
    args = parser.parse_args()

    target_log_file = args.log_file

    if args.mock or not os.path.exists(target_log_file):
        if not args.mock and target_log_file != "logs/mock_openalgo.log":
             print(f"Log file {target_log_file} not found. Generating mock logs...")
        target_log_file = "logs/mock_openalgo.log"
        generate_mock_logs(target_log_file)

    analyze_logs(target_log_file)
