
import time
import hashlib
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

# Mock classes to avoid dependencies in benchmark script
@dataclass
class Bar:
    token: int
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

@dataclass
class Instrument:
    token: int
    symbol: str
    tradingsymbol: str
    strike: float

def original_logic(bars, symbol, strike, option_type):
    # Mimics _process_day loop
    start_time = time.time()

    generated_instruments = []

    for i in range(len(bars)):
        history_bars = bars[:i+1]

        # Mimic _generate_signals
        token_str = f"{symbol}_{strike}_{option_type}"
        token_hash = hashlib.md5(token_str.encode()).hexdigest()
        token = int(token_hash[:8], 16)

        # The O(N^2) part
        for b in history_bars:
            b.token = token

        instrument = Instrument(
            token=token,
            symbol=symbol,
            tradingsymbol=f"{symbol}{int(strike)}{option_type}",
            strike=strike
        )
        generated_instruments.append(instrument)

    return time.time() - start_time

def optimized_logic(bars, symbol, strike, option_type):
    start_time = time.time()

    # 1. Generate token once
    token_str = f"{symbol}_{strike}_{option_type}"
    token_hash = hashlib.md5(token_str.encode()).hexdigest()
    token = int(token_hash[:8], 16)

    # 2. Set token on all bars once (O(N))
    for b in bars:
        b.token = token

    # 3. Create Instrument once
    instrument = Instrument(
        token=token,
        symbol=symbol,
        tradingsymbol=f"{symbol}{int(strike)}{option_type}",
        strike=strike
    )

    generated_instruments = []

    for i in range(len(bars)):
        history_bars = bars[:i+1]

        # Mimic _generate_signals (now faster)
        # No token loop, no hash, no instrument creation

        generated_instruments.append(instrument)

    return time.time() - start_time

def run_benchmark():
    N_BARS = 10000 # ~1 month of minute bars
    symbol = "NIFTY"
    strike = 18000.0
    option_type = "CE"

    print(f"Benchmarking with {N_BARS} bars...")

    # Setup data
    bars_orig = [Bar(0, datetime.now(), 100, 110, 90, 105, 1000) for _ in range(N_BARS)]
    bars_opt = [Bar(0, datetime.now(), 100, 110, 90, 105, 1000) for _ in range(N_BARS)]

    # Run Original
    time_orig = original_logic(bars_orig, symbol, strike, option_type)
    print(f"Original logic time: {time_orig:.4f}s")

    # Run Optimized
    time_opt = optimized_logic(bars_opt, symbol, strike, option_type)
    print(f"Optimized logic time: {time_opt:.4f}s")

    speedup = time_orig / time_opt if time_opt > 0 else 0
    print(f"Speedup: {speedup:.2f}x")

if __name__ == "__main__":
    run_benchmark()
