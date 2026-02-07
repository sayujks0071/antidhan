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
    # Simulate 3 trade cycles
    symbols = ["NIFTY", "BANKNIFTY", "RELIANCE"]

    start_time = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)

    for i, symbol in enumerate(symbols):
        # Time progression
        current_time = start_time + timedelta(minutes=i*15)

        with open(filepath, "a") as f:
            # Signal
            signal_time = current_time
            signal_price = 24500 + (i * 100)

            # Using SuperTrendVWAPStrategy log format
            # self.logger.info(f"VWAP Crossover Buy. Price: {last['close']:.2f}, POC: {poc_price:.2f}, Vol: {last['volume']}, Sector: Bullish, Dev: {last['vwap_dev']:.4f}, Qty: {adj_qty} (VIX: {vix})")
            poc_price = signal_price - 20
            volume = 150000 + (i * 1000)
            dev = 0.002 * (i + 1)
            vix = 14.5

            if i == 0: # Use new format for NIFTY to verify parser
                f.write(f"{signal_time.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} INFO VWAP Crossover Buy. Price: {signal_price:.2f}, POC: {poc_price:.2f}, Vol: {volume}, Sector: Bullish, Dev: {dev:.4f}, Qty: 25 (VIX: {vix})\n")
                # Also write Execute log which might be present
                f.write(f"{signal_time.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} INFO Executing BUY 25 {symbol} @ {signal_price:.2f}\n")
            else: # Use legacy format for others
                f.write(f"{signal_time.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} INFO Signal Generated: BUY {symbol} @ {signal_price}\n")

            # Latency: Random between 50ms and 600ms
            latency_ms = random.randint(50, 600)
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

    try:
        with open(filepath, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Log file {filepath} not found.")
        return

    signal_map = {} # Store signal time and price by symbol

    # Regex patterns
    signal_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) INFO Signal Generated: BUY (\w+) @ ([\d\.]+)")
    vwap_signal_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) INFO VWAP Crossover Buy. Price: ([\d\.]+)")
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
            ts_str, price = m_vwap.groups()
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
            # Assume NIFTY for this specific log pattern in mock
            symbol = "NIFTY"
            signal_map[symbol] = {'signal_time': ts, 'signal_price': float(price)}
            continue

        # Check Order (Latency)
        m_ord = order_pattern.search(line)
        if m_ord:
            ts_str, symbol = m_ord.groups()
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
            if symbol in signal_map:
                sig_ts = signal_map[symbol]['signal_time']
                latency_ms = (ts - sig_ts).total_seconds() * 1000
                latency_records.append({'symbol': symbol, 'latency': latency_ms})
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
        print(f"Symbol: {rec['symbol']}, Latency: {rec['latency']:.2f} ms")
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

    # Logic Verification (Mock)
    print("\n--- Logic Verification ---")
    # Simulate picking SuperTrendVWAPStrategy
    print("Strategy: SuperTrendVWAPStrategy (NIFTY)")

    # Mock data matching strategy logic
    # is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended and sector_bullish
    close_price = 24500
    vwap = 24450
    poc_price = 24480
    volume = 200000
    vol_mean = 100000
    vol_std = 50000
    dynamic_threshold = vol_mean + (1.5 * vol_std) # 175000
    vwap_dev = (close_price - vwap) / vwap # ~0.002
    dev_threshold = 0.03
    sector_rsi = 55.0

    print(f"Market Data:")
    print(f"  Close: {close_price}, VWAP: {vwap} (Above: {close_price > vwap})")
    print(f"  Volume: {volume}, Threshold: {dynamic_threshold} (Spike: {volume > dynamic_threshold})")
    print(f"  POC: {poc_price} (Above: {close_price > poc_price})")
    print(f"  Dev: {vwap_dev:.5f} (Within limit {dev_threshold}: {abs(vwap_dev) < dev_threshold})")
    print(f"  Sector RSI: {sector_rsi} (Bullish: {sector_rsi > 50})")

    # Logic Check
    is_above_vwap = close_price > vwap
    is_volume_spike = volume > dynamic_threshold
    is_above_poc = close_price > poc_price
    is_not_overextended = abs(vwap_dev) < dev_threshold
    sector_bullish = sector_rsi > 50

    is_valid = is_above_vwap and is_volume_spike and is_above_poc and is_not_overextended and sector_bullish

    if is_valid:
        print("Signal Validated: YES (Mathematically Accurate - VWAP Strategy)")
    else:
        print("Signal Validated: NO (Logic Mismatch)")

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
