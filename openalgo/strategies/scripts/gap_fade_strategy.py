#!/usr/bin/env python3
import sys
import os
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add repo root to path to allow imports
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, 'utils')
sys.path.insert(0, utils_dir)

try:
    from base_strategy import BaseStrategy
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.base_strategy import BaseStrategy
    except ImportError:
        sys.path.append(utils_dir)
        from base_strategy import BaseStrategy

class GapFadeStrategy(BaseStrategy):
    def __init__(self, symbol, quantity, gap_threshold=0.5, api_key=None, host=None, logfile=None, client=None):
        super().__init__(
            name="GapFadeStrategy",
            symbol=symbol,
            quantity=quantity,
            api_key=api_key,
            host=host,
            log_file=logfile,
            client=client
        )
        self.gap_threshold = gap_threshold

    def cycle(self):
        self.logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # Handle NIFTY -> NIFTY 50 logic for history and quote
        # This preserves the original behavior where NIFTY implies NIFTY 50
        target_symbol = f"{self.symbol} 50" if self.symbol == "NIFTY" else self.symbol

        # 1. Get Previous Close
        # Get daily candles
        df = self.fetch_history(days=5, interval="day", symbol=target_symbol)

        if df.empty or len(df) < 1:
            self.logger.error("Could not fetch history for previous close.")
            return

        prev_close = df.iloc[-1]['close']

        quote = self.client.get_quote(target_symbol, "NSE")
        if not quote:
            self.logger.error("Could not fetch quote.")
            return

        current_price = float(quote['ltp'])

        # Some APIs provide 'close' in quote which is prev_close
        if 'close' in quote and quote['close'] > 0:
            prev_close = float(quote['close'])

        self.logger.info(f"Prev Close: {prev_close}, Current: {current_price}")

        gap_pct = ((current_price - prev_close) / prev_close) * 100
        self.logger.info(f"Gap: {gap_pct:.2f}%")

        if abs(gap_pct) < self.gap_threshold:
            self.logger.info(f"Gap {gap_pct:.2f}% < Threshold {self.gap_threshold}%. No trade.")
            return

        # 2. Determine Action
        action = None
        option_type = None

        if gap_pct > self.gap_threshold:
            # Gap UP -> Fade (Sell/Short or Buy Put)
            self.logger.info("Gap UP detected. Looking to FADE (Short).")
            action = "SELL"
            option_type = "PE"

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Buy/Long or Buy Call)
            self.logger.info("Gap DOWN detected. Looking to FADE (Long).")
            action = "BUY"
            option_type = "CE"

        # 3. Select Option Strike (ATM)
        atm = round(current_price / 50) * 50

        self.logger.info(f"Signal: Buy {option_type} at {atm} (Gap Fade)")

        # 4. Check VIX
        vix = self.get_vix()
        qty = self.quantity
        if vix > 30:
            qty = int(qty * 0.5)
            self.logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 5. Place Order (Simulation)
        self.logger.info(f"Executing {option_type} Buy for {qty} qty.")
        if self.pm:
            self.pm.update_position(qty, 100, "BUY")

def main():
    parser = BaseStrategy.get_standard_parser("Gap Fade Strategy")
    parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")
    args = parser.parse_args()

    # Default logfile
    logfile = args.logfile
    if not logfile:
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        logfile = project_root / "openalgo" / "strategies" / "logs" / "gap_fade.log"

    strategy = GapFadeStrategy(
        symbol=args.symbol or "NIFTY",
        quantity=args.quantity,
        gap_threshold=args.threshold,
        api_key=args.api_key,
        host=args.host,
        logfile=str(logfile)
    )
    # Execute logic once
    strategy.cycle()

if __name__ == "__main__":
    main()
