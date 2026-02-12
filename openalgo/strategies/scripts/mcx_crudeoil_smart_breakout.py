#!/usr/bin/env python3
"""
[Strategy Description]
MCX Smart Breakout Strategy
Innovative volatility-adjusted breakout strategy with dynamic risk management.
Uses Bollinger Bands Squeeze/Expansion logic and ATR-based exits.
"""
import os
import sys
import time
import logging
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
# Add repo root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, "utils")
sys.path.insert(0, utils_dir)
try:
    from trading_utils import (
        APIClient,
        PositionManager,
        is_market_open,
        calculate_sma,
        calculate_rsi,
        calculate_bollinger_bands,
        calculate_atr
    )
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import (
            APIClient,
            PositionManager,
            is_market_open,
            calculate_sma,
            calculate_rsi,
            calculate_bollinger_bands,
            calculate_atr
        )
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import (
                APIClient,
                PositionManager,
                is_market_open,
                calculate_sma,
                calculate_rsi,
                calculate_bollinger_bands,
                calculate_atr
            )
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            is_market_open = lambda x="NSE": True
            calculate_sma = lambda x, y: x
            calculate_rsi = lambda x, y: x
            calculate_bollinger_bands = lambda x, y, z: (x, x, x)
            calculate_atr = lambda x, y: x

# Setup Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("MCX_Smart_Breakout")

class MCXSmartStrategy:
    def __init__(self, symbol, api_key, host, params):
        self.symbol = symbol
        self.api_key = api_key
        self.host = host
        self.params = params

        self.client = APIClient(api_key=self.api_key, host=self.host) if APIClient else None
        self.pm = PositionManager(symbol) if PositionManager else None
        self.data = pd.DataFrame()

        logger.info(f"Initialized Smart Strategy for {symbol}")
        logger.info(f"Filters: Seasonality={params.get('seasonality_score', 'N/A')}, USD_Vol={params.get('usd_inr_volatility', 'N/A')}")

    def fetch_data(self):
        """Fetch live or historical data from OpenAlgo"""
        if not self.client:
            logger.error("API Client not initialized.")
            return

        try:
            logger.info(f"Fetching data for {self.symbol}...")
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

            df = self.client.history(
                symbol=self.symbol,
                interval="15m",
                exchange="MCX",
                start_date=start_date,
                end_date=end_date,
            )

            if not df.empty and len(df) > 50:
                self.data = df
                logger.info(f"Fetched {len(df)} candles.")
            else:
                logger.warning(f"Insufficient data for {self.symbol}.")

        except Exception as e:
            logger.error(f"Error fetching data: {e}", exc_info=True)

    def calculate_indicators(self):
        """Calculate technical indicators"""
        if self.data.empty:
            return

        df = self.data.copy()

        # Calculate Indicators
        # SMA 50 for Trend Filter
        df['sma_50'] = calculate_sma(df['close'], period=50)

        # RSI 14
        df['rsi'] = calculate_rsi(df['close'], period=self.params.get("period_rsi", 14))

        # Bollinger Bands (20, 2)
        df['bb_mid'], df['bb_upper'], df['bb_lower'] = calculate_bollinger_bands(df['close'], window=20, num_std=2)

        # ATR 14 for Volatility and Stop Loss
        # Note: calculate_atr returns a Series
        df['atr'] = calculate_atr(df, period=14)

        # ATR Moving Average (Volatility Expansion Check)
        df['atr_ma'] = calculate_sma(df['atr'], period=10)

        self.data = df

    def check_signals(self):
        """Check entry and exit conditions"""
        if self.data.empty or len(self.data) < 50:
            return

        current = self.data.iloc[-1]
        prev = self.data.iloc[-2]

        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.params.get("seasonality_score", 50) > 40
        global_alignment_ok = self.params.get("global_alignment_score", 50) >= 40
        usd_vol_high = self.params.get("usd_inr_volatility", 0) > 1.0

        # Position sizing adjustment for volatility
        base_qty = 1
        if usd_vol_high:
            logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(base_qty * 0.7))

        if not seasonality_ok and not has_position:
            logger.info("Seasonality Weak: Skipping new entries.")
            return

        # ---------------------------------------------------------
        # INNOVATIVE LOGIC: Volatility-Adjusted Breakout
        # ---------------------------------------------------------

        # Volatility Check: Is current ATR > Average ATR? (Market is waking up)
        volatility_expanding = current['atr'] > current['atr_ma']

        # Trend Filter: Long only if price > SMA 50, Short only if price < SMA 50
        trend_up = current['close'] > current['sma_50']
        trend_down = current['close'] < current['sma_50']

        # Entry Logic
        if not has_position:
            # BUY: Price breaks Upper BB, Volatility Expanding, RSI Healthy (50-70)
            if (current['close'] > current['bb_upper'] and
                volatility_expanding and
                trend_up and
                50 < current['rsi'] < 70):

                stop_loss = current['close'] - (1.5 * current['atr'])
                take_profit = current['close'] + (3.0 * current['atr'])

                logger.info(f"BUY SIGNAL (Smart Breakout): Price={current['close']}, ATR={current['atr']:.2f}, SL={stop_loss:.2f}, TP={take_profit:.2f}")

                if self.pm:
                    self.pm.update_position(base_qty, current["close"], "BUY")
                    # Store SL/TP in state if PM supported it, currently we manage dynamically

            # SELL: Price breaks Lower BB, Volatility Expanding, RSI Healthy (30-50)
            elif (current['close'] < current['bb_lower'] and
                  volatility_expanding and
                  trend_down and
                  30 < current['rsi'] < 50):

                stop_loss = current['close'] + (1.5 * current['atr'])
                take_profit = current['close'] - (3.0 * current['atr'])

                logger.info(f"SELL SIGNAL (Smart Breakdown): Price={current['close']}, ATR={current['atr']:.2f}, SL={stop_loss:.2f}, TP={take_profit:.2f}")

                if self.pm:
                    self.pm.update_position(base_qty, current["close"], "SELL")

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position
            entry_price = self.pm.entry_price

            # Dynamic Exits based on ATR calculated at entry (approximated by current ATR for simplicity in this stateless example)
            # In a real system, we'd store the entry ATR. Here we use current ATR for dynamic stops.

            if pos_qty > 0: # Long Position
                # Stop Loss: Close below SMA 20 (Trailing) OR Hard ATR Stop
                stop_hit = current['close'] < (entry_price - (1.5 * current['atr']))
                trend_reversal = current['close'] < current['bb_mid'] # SMA 20 is BB Mid
                target_hit = current['close'] > (entry_price + (3.0 * current['atr']))

                if stop_hit or trend_reversal or target_hit:
                    reason = "Stop Loss" if stop_hit else "Target" if target_hit else "Trend Reversal"
                    logger.info(f"EXIT LONG ({reason}): Price={current['close']}, Entry={entry_price}")
                    self.pm.update_position(abs(pos_qty), current["close"], "SELL")

            elif pos_qty < 0: # Short Position
                # Stop Loss
                stop_hit = current['close'] > (entry_price + (1.5 * current['atr']))
                trend_reversal = current['close'] > current['bb_mid']
                target_hit = current['close'] < (entry_price - (3.0 * current['atr']))

                if stop_hit or trend_reversal or target_hit:
                    reason = "Stop Loss" if stop_hit else "Target" if target_hit else "Trend Reversal"
                    logger.info(f"EXIT SHORT ({reason}): Price={current['close']}, Entry={entry_price}")
                    self.pm.update_position(abs(pos_qty), current["close"], "BUY")

    def generate_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        self.data = df
        self.calculate_indicators()

        if len(self.data) < 50:
            return "HOLD", 0.0, {}

        current = self.data.iloc[-1]

        # Logic mirroring check_signals
        volatility_expanding = current['atr'] > current['atr_ma']
        trend_up = current['close'] > current['sma_50']
        trend_down = current['close'] < current['sma_50']

        if (current['close'] > current['bb_upper'] and
            volatility_expanding and
            trend_up and
            50 < current['rsi'] < 70):
            return "BUY", 1.0, {"reason": "Smart Breakout"}

        elif (current['close'] < current['bb_lower'] and
              volatility_expanding and
              trend_down and
              30 < current['rsi'] < 50):
            return "SELL", 1.0, {"reason": "Smart Breakdown"}

        return "HOLD", 0.0, {}

    def run(self):
        logger.info(f"Starting Smart MCX Strategy for {self.symbol}")
        while True:
            if not is_market_open("MCX"):
                logger.info("Market is closed. Sleeping...")
                time.sleep(300)
                continue

            self.fetch_data()
            self.calculate_indicators()
            self.check_signals()
            time.sleep(900)  # 15 minutes

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCX Smart Commodity Strategy")
    parser.add_argument("--symbol", type=str, help="MCX Symbol (e.g., GOLDM05FEB26FUT)")
    parser.add_argument("--underlying", type=str, help="Commodity Name (e.g., GOLD, SILVER)")
    parser.add_argument("--port", type=int, default=5001, help="API Port")
    parser.add_argument("--api_key", type=str, help="API Key")

    # Multi-Factor Arguments
    parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
    parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
    parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
    parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")

    args = parser.parse_args()

    # Strategy Parameters
    PARAMS = {
        "period_rsi": 14,
        "period_atr": 14,
        "usd_inr_trend": args.usd_inr_trend,
        "usd_inr_volatility": args.usd_inr_volatility,
        "seasonality_score": args.seasonality_score,
        "global_alignment_score": args.global_alignment_score,
    }

    # Symbol Resolution
    symbol = args.symbol or os.getenv("SYMBOL")

    # Try to resolve from underlying
    if not symbol and args.underlying:
        try:
            from symbol_resolver import SymbolResolver
        except ImportError:
            try:
                from utils.symbol_resolver import SymbolResolver
            except ImportError:
                SymbolResolver = None

        if SymbolResolver:
            resolver = SymbolResolver()
            res = resolver.resolve({"underlying": args.underlying, "type": "FUT", "exchange": "MCX"})
            if res:
                symbol = res
                logger.info(f"Resolved {args.underlying} -> {symbol}")

    if not symbol:
        logger.error("Symbol not provided. Use --symbol or --underlying")
        sys.exit(1)

    api_key = args.api_key or os.getenv("OPENALGO_APIKEY")
    port = args.port or int(os.getenv("OPENALGO_PORT", 5001))
    host = f"http://127.0.0.1:{port}"

    strategy = MCXSmartStrategy(symbol, api_key, host, PARAMS)
    strategy.run()

# Backtesting support
DEFAULT_PARAMS = {
    "period_rsi": 14,
    "period_atr": 14,
}
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = DEFAULT_PARAMS.copy()
    if params:
        strat_params.update(params)

    api_key = client.api_key if client and hasattr(client, "api_key") else "BACKTEST"
    host = client.host if client and hasattr(client, "host") else "http://127.0.0.1:5001"

    strat = MCXSmartStrategy(symbol or "TEST", api_key, host, strat_params)
    return strat.generate_signal(df)
