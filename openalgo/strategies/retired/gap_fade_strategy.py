#!/usr/bin/env python3
import sys
import os
from datetime import datetime
from pathlib import Path

# Add repo root to path to allow imports (if running as script)
try:
    from base_strategy import BaseStrategy
except ImportError:
    # Try setting path to find utils
    script_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(script_dir)
    utils_dir = os.path.join(strategies_dir, 'utils')
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from base_strategy import BaseStrategy

class GapFadeStrategy(BaseStrategy):
    """
    Gap Fade Strategy
    -----------------
    Fades opening gaps that are significant (> threshold) but not too strong (ADX check).

    IMPROVEMENTS (2026-02-10):
    - Addressed low win rate (< 30% in mock tests) which was caused by 'fire-and-forget' entry without exits.
    - ADDED: Stop Loss (1%) and Take Profit (Gap Fill) management.
    - ADDED: Continuous monitoring loop (removed run() override) to manage trades intraday.
    - ADDED: Time-based exit (15:15) to prevent holding overnight.
    - ADDED: Explicit checks for market hours for entry (9:15-10:00 only).
    - ADDED: State recovery logic for SL/TP targets on restart.
    """

    def __init__(self, symbol, quantity, gap_threshold=0.5, api_key=None, host=None, log_file=None, client=None, **kwargs):
        super().__init__(
            name="GapFadeStrategy",
            symbol=symbol,
            quantity=quantity,
            api_key=api_key,
            host=host,
            log_file=log_file,
            client=client
        )
        self.gap_threshold = gap_threshold
        self.stop_loss_price = 0.0
        self.take_profit_price = 0.0

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--threshold", type=float, default=0.5, help="Gap Threshold %%")

    @classmethod
    def parse_arguments(cls, args):
        kwargs = super().parse_arguments(args)
        kwargs['gap_threshold'] = args.threshold
        # Default symbol for Gap Fade if not provided
        if not kwargs.get('symbol'):
            kwargs['symbol'] = "NIFTY"
        return kwargs

    def cycle(self):
        """
        Executed every minute by BaseStrategy.run()
        """
        now = datetime.now()

        # 1. Monitor Existing Position
        if self.pm.position != 0:
            self.check_exit(now)
            return

        # 2. Check Entry (Only in first 45 mins of market open)
        # Assuming market opens at 9:15
        if now.hour == 9 and 15 <= now.minute < 45:
             self.check_entry()
        elif now.hour < 9 or (now.hour == 9 and now.minute < 15):
             self.logger.info("Waiting for market open...")
        else:
             # After 9:45, we don't enter new gap fades
             if now.minute % 15 == 0: # Log occasionally
                 self.logger.info("Outside entry window (09:15-09:45). No new entries.")

    def check_entry(self):
        self.logger.info(f"Checking Entry Conditions for {self.symbol}...")

        # Handle NIFTY -> NIFTY 50 logic for history and quote
        target_symbol = f"{self.symbol} 50" if self.symbol == "NIFTY" else self.symbol

        # 1. Get Previous Close & Data
        df = self.fetch_history(days=40, interval="day", symbol=target_symbol)

        if df.empty or len(df) < 1:
            self.logger.error("Could not fetch history for previous close.")
            return

        # Calculate ADX (Trend Strength)
        try:
            adx = self.calculate_adx(df)
            self.logger.info(f"ADX: {adx:.2f}")
            if adx > 25:
                self.logger.info(f"ADX {adx:.2f} > 25 indicates strong trend. Skipping Gap Fade trade.")
                return
        except Exception as e:
            self.logger.warning(f"Could not calculate ADX: {e}")

        # Calculate RSI
        try:
            rsi_series = self.calculate_rsi(df['close'])
            rsi = rsi_series.iloc[-1]
            self.logger.info(f"RSI: {rsi:.2f}")
        except Exception as e:
            self.logger.warning(f"Could not calculate RSI: {e}")
            rsi = 50

        prev_close = df.iloc[-1]['close']

        quote = self.client.get_quote(target_symbol, "NSE")
        if not quote:
            self.logger.error("Could not fetch quote.")
            return

        current_price = float(quote['ltp'])

        # Gap Calculation
        gap_pct = ((current_price - prev_close) / prev_close) * 100
        self.logger.info(f"Prev Close: {prev_close}, Current: {current_price}, Gap: {gap_pct:.2f}%")

        if abs(gap_pct) < self.gap_threshold:
            self.logger.info(f"Gap {gap_pct:.2f}% < Threshold {self.gap_threshold}%. No trade.")
            return

        # 2. Determine Action
        action = None

        if gap_pct > self.gap_threshold:
            # Gap UP -> Fade (Short)
            if rsi > 60:
                self.logger.info(f"Gap UP detected & RSI {rsi:.2f} > 60. FADE (Short).")
                action = "SELL"
                # SL: 1% above entry
                self.stop_loss_price = current_price * 1.01
                # TP: Gap Fill (Prev Close)
                self.take_profit_price = prev_close
            else:
                self.logger.info(f"Gap UP but RSI {rsi:.2f} < 60. Skipping.")
                return

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Long)
            if rsi < 40:
                self.logger.info(f"Gap DOWN detected & RSI {rsi:.2f} < 40. FADE (Long).")
                action = "BUY"
                # SL: 1% below entry
                self.stop_loss_price = current_price * 0.99
                # TP: Gap Fill (Prev Close)
                self.take_profit_price = prev_close
            else:
                self.logger.info(f"Gap DOWN but RSI {rsi:.2f} > 40. Skipping.")
                return

        # 4. Check VIX for sizing
        vix = self.get_vix()
        qty = self.quantity
        if vix > 30:
            qty = int(qty * 0.5)
            self.logger.info(f"High VIX {vix}. Reduced Qty to {qty}")

        # 5. Execute Trade
        self.logger.info(f"Executing {action} {qty} {self.symbol} @ {current_price}")
        self.logger.info(f"Targets - SL: {self.stop_loss_price:.2f}, TP: {self.take_profit_price:.2f}")

        # Use execute_trade from BaseStrategy which handles API and PositionManager
        self.execute_trade(action, qty, current_price)


    def check_exit(self, now):
        """Monitor open position for SL/TP/Time exit."""
        target_symbol = f"{self.symbol} 50" if self.symbol == "NIFTY" else self.symbol
        quote = self.client.get_quote(target_symbol, "NSE")

        if not quote:
            return

        current_price = float(quote['ltp'])

        # Restore State on Restart
        if self.pm.position != 0 and (self.stop_loss_price == 0 or self.take_profit_price == 0):
            self.logger.info("Restoring SL/TP state after restart...")

            # Fetch Prev Close for Target (Gap Fill)
            df = self.fetch_history(days=5, interval="day", symbol=target_symbol)
            prev_close = 0
            if not df.empty:
                # If last candle is today, use previous one
                if df.iloc[-1]['datetime'].date() == now.date() and len(df) > 1:
                     prev_close = df.iloc[-2]['close']
                else:
                     prev_close = df.iloc[-1]['close']

            # Set TP
            if prev_close > 0:
                self.take_profit_price = prev_close
            else:
                # Fallback Target: 0.5% gain
                self.take_profit_price = self.pm.entry_price * (1.005 if self.pm.position > 0 else 0.995)

            # Recalculate SL (1%)
            if self.pm.position > 0:
                self.stop_loss_price = self.pm.entry_price * 0.99
            else:
                self.stop_loss_price = self.pm.entry_price * 1.01

            self.logger.info(f"Restored Targets - SL: {self.stop_loss_price:.2f}, TP: {self.take_profit_price:.2f}")

        # 1. Time Exit (15:15)
        if now.hour == 15 and now.minute >= 15:
            self.logger.info("Time Exit (15:15). Closing position.")
            self.close_position(current_price, "Time Exit")
            return

        # 2. Stop Loss / Take Profit
        if self.pm.position > 0: # LONG
            if current_price <= self.stop_loss_price:
                self.logger.info(f"Stop Loss Hit: {current_price} <= {self.stop_loss_price}")
                self.close_position(current_price, "Stop Loss")
            elif current_price >= self.take_profit_price:
                self.logger.info(f"Take Profit Hit: {current_price} >= {self.take_profit_price}")
                self.close_position(current_price, "Take Profit")

        elif self.pm.position < 0: # SHORT
            if current_price >= self.stop_loss_price:
                self.logger.info(f"Stop Loss Hit: {current_price} >= {self.stop_loss_price}")
                self.close_position(current_price, "Stop Loss")
            elif current_price <= self.take_profit_price:
                self.logger.info(f"Take Profit Hit: {current_price} <= {self.take_profit_price}")
                self.close_position(current_price, "Take Profit")

    def close_position(self, price, reason):
        qty = abs(self.pm.position)
        action = "SELL" if self.pm.position > 0 else "BUY"
        self.logger.info(f"Closing Position ({reason}): {action} {qty} @ {price}")
        self.execute_trade(action, qty, price, urgency="HIGH")
        # Reset targets
        self.stop_loss_price = 0.0
        self.take_profit_price = 0.0

if __name__ == "__main__":
    GapFadeStrategy.cli()
