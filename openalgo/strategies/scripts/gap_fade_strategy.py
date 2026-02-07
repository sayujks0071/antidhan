#!/usr/bin/env python3
import sys
import os
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

    def run(self):
        """Override run to execute only once (Gap Fade is a daily strategy)"""
        self.logger.info(f"Starting {self.name} for {self.symbol} (Single Cycle)")
        self.cycle()

    def cycle(self):
        self.logger.info(f"Starting Gap Fade Check for {self.symbol}")

        # Handle NIFTY -> NIFTY 50 logic for history and quote
        # This preserves the original behavior where NIFTY implies NIFTY 50
        target_symbol = f"{self.symbol} 50" if self.symbol == "NIFTY" else self.symbol

        # 1. Get Previous Close
        # Get daily candles (Increase lookback to 40 days for ADX calculation)
        df = self.fetch_history(days=40, interval="day", symbol=target_symbol)

        if df.empty or len(df) < 1:
            self.logger.error("Could not fetch history for previous close.")
            return

        # Calculate ADX to check trend strength
        # IMPROVEMENT: Avoid fading if trend is too strong (ADX > 25)
        # This addresses low win rate in trending markets.
        try:
            adx = self.calculate_adx(df)
            self.logger.info(f"ADX: {adx:.2f}")
            if adx > 25:
                self.logger.info(f"ADX {adx:.2f} > 25 indicates strong trend. Skipping Gap Fade trade.")
                return
        except Exception as e:
            self.logger.warning(f"Could not calculate ADX: {e}")

        # Calculate RSI for Mean Reversion confirmation
        # Added to address low win rate by ensuring we don't fade strong trends
        # We only want to Fade (Mean Revert) if RSI confirms Overbought/Oversold
        try:
            rsi_series = self.calculate_rsi(df['close'])
            current_rsi = rsi_series.iloc[-1]
            self.logger.info(f"RSI: {current_rsi:.2f}")
        except Exception as e:
            self.logger.warning(f"Could not calculate RSI: {e}")
            current_rsi = 50 # Default to neutral

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
            if current_rsi < 70:
                self.logger.info(f"Gap Up but RSI {current_rsi:.2f} < 70. Not overbought. Skipping Fade.")
                return

            self.logger.info("Gap UP detected. Looking to FADE (Short).")
            action = "SELL"
            option_type = "PE"

        elif gap_pct < -self.gap_threshold:
            # Gap DOWN -> Fade (Buy/Long or Buy Call)
            if current_rsi > 30:
                self.logger.info(f"Gap Down but RSI {current_rsi:.2f} > 30. Not oversold. Skipping Fade.")
                return

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

if __name__ == "__main__":
    GapFadeStrategy.cli()
