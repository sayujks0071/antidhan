#!/usr/bin/env python3
import sys
import os
import argparse
import pandas as pd
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

        # 1. Get Recent Intraday Data
        # We need the open of today and the close of yesterday, plus current candle to check reversal
        df = self.fetch_history(days=2, interval="5m", symbol=target_symbol)
        if df is None or df.empty or len(df) < 2:
            self.logger.error("Could not fetch history for gap and reversal analysis.")
            return

        # Ensure datetime index
        if 'datetime' in df.columns:
            df.set_index('datetime', inplace=True)
            df.index = pd.to_datetime(df.index)

        # Get previous close
        # To do this safely, group by date
        df['date'] = df.index.date
        dates = df['date'].unique()
        if len(dates) < 2:
            self.logger.info("Not enough days to determine gap.")
            return

        # previous day's data
        prev_day_data = df[df['date'] == dates[-2]]
        if prev_day_data.empty:
            return
        prev_close = prev_day_data.iloc[-1]['close']

        # current day's first candle
        current_day_data = df[df['date'] == dates[-1]]
        if current_day_data.empty:
            return

        today_open = current_day_data.iloc[0]['open']
        first_candle_high = current_day_data.iloc[0]['high']
        first_candle_low = current_day_data.iloc[0]['low']

        current_price = current_day_data.iloc[-1]['close']

        self.logger.info(f"Prev Close: {prev_close}, Today Open: {today_open}, Current: {current_price}")

        gap_pct = ((today_open - prev_close) / prev_close) * 100
        self.logger.info(f"Gap: {gap_pct:.2f}%")

        if abs(gap_pct) < self.gap_threshold:
            self.logger.info(f"Gap {gap_pct:.2f}% < Threshold {self.gap_threshold}%. No trade.")
            return

        # 2. Determine Reversal & Action
        action = None
        option_type = None

        # Need current candle logic to see if there's a reversal
        last_candle = df.iloc[-1]

        if gap_pct > self.gap_threshold:
            # Gap UP -> Fade (Sell/Short or Buy Put)
            # Reversal condition: Close < Open on the current candle (bearish candle)
            if last_candle['close'] < last_candle['open']:
                self.logger.info("Gap UP detected AND bearish reversal candle. Looking to FADE (Short).")
                action = "SELL"
                option_type = "PE"
            else:
                self.logger.info("Gap UP but no bearish reversal candle. Waiting.")
                return

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Buy/Long or Buy Call)
            # Reversal condition: Close > Open on the current candle (bullish candle)
            if last_candle['close'] > last_candle['open']:
                self.logger.info("Gap DOWN detected AND bullish reversal candle. Looking to FADE (Long).")
                action = "BUY"
                option_type = "CE"
            else:
                self.logger.info("Gap DOWN but no bullish reversal candle. Waiting.")
                return

        # 3. Select Option Strike (ATM)
        atm = round(current_price / 50) * 50

        self.logger.info(f"Signal: Buy {option_type} at {atm} (Gap Fade)")

        # 4. Check VIX
        vix = self.get_vix()
        qty = self.quantity
        if vix > 30:
            qty = int(qty * 0.5)
            self.logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # Stop loss calculation (based on first candle's High/Low)
        stop_loss = first_candle_high if option_type == "PE" else first_candle_low

        # 5. Place Order (Simulation)
        self.logger.info(f"Executing {option_type} Buy for {qty} qty. Stop Loss: {stop_loss}")
        if self.pm:
            self.pm.update_position(qty, current_price, "BUY", stop_loss=stop_loss)

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
