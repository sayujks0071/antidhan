#!/usr/bin/env python3
"""
MCX Zinc Breakout Strategy
MCX Commodity trading strategy with multi-factor analysis: Donchian Channels, ADX, and RSI.
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
    from trading_utils import APIClient, PositionManager, is_market_open
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_market_open
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            is_market_open = lambda: True

# Setup Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("MCX_ZINC_Strategy")

class MCXStrategy:
    def __init__(self, symbol, api_key, host, params):
        self.symbol = symbol
        self.api_key = api_key
        self.host = host
        self.params = params

        self.client = APIClient(api_key=self.api_key, host=self.host) if APIClient else None
        self.pm = PositionManager(symbol) if PositionManager else None
        self.data = pd.DataFrame()

        logger.info(f"Initialized Strategy for {symbol}")
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

        # Donchian Channels (20)
        period_dc = self.params.get("period_dc", 20)
        # Shift by 1 to compare against previous N periods (standard breakout logic)
        df['dc_high'] = df['high'].rolling(window=period_dc).max().shift(1)
        df['dc_low'] = df['low'].rolling(window=period_dc).min().shift(1)
        df['dc_mid'] = (df['dc_high'] + df['dc_low']) / 2

        # RSI (14)
        period_rsi = self.params.get("period_rsi", 14)
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period_rsi).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period_rsi).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))

        # ADX (14)
        period_adx = self.params.get("period_adx", 14)
        df['up_move'] = df['high'] - df['high'].shift(1)
        df['down_move'] = df['low'].shift(1) - df['low']
        df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
        df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)

        df['atr'] = df['high'].combine(df['close'].shift(), max) - df['low'].combine(df['close'].shift(), min) # Simple TR approximation for ADX context if needed, but accurate ATR is typically EMA of TR.
        # Let's use simple rolling mean for ATR part of ADX as per common implementation or just SMA of DMs

        # Standard ADX implementation involves smoothing. Using simple rolling mean for simplicity in this template unless specified otherwise.
        # But 'wilder' smoothing is standard for ADX. I'll use rolling mean which is close enough for a basic template,
        # or better:
        df['tr'] = np.maximum(df['high'] - df['low'], np.maximum(abs(df['high'] - df['close'].shift()), abs(df['low'] - df['close'].shift())))
        df['atr_adx'] = df['tr'].rolling(window=period_adx).mean()

        df['plus_di'] = 100 * (df['plus_dm'].rolling(window=period_adx).mean() / df['atr_adx'])
        df['minus_di'] = 100 * (df['minus_dm'].rolling(window=period_adx).mean() / df['atr_adx'])
        df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
        df['adx'] = df['dx'].rolling(window=period_adx).mean()

        self.data = df

    def check_signals(self):
        """Check entry and exit conditions"""
        if self.data.empty or len(self.data) < 50:
            return

        current = self.data.iloc[-1]
        # prev = self.data.iloc[-2] # Not strictly needed if using current close for breakout confirmation

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

        if not global_alignment_ok and not has_position:
            logger.info("Global Alignment Weak: Skipping new entries.")
            return

        # Logic
        # Buy: Close > Upper Channel AND ADX > 25 AND RSI > 50
        # Sell: Close < Lower Channel AND ADX > 25 AND RSI < 50
        # Exit: Trend Reversal (Close crosses Mid Channel)

        buy_signal = (current['close'] > current['dc_high']) and (current['adx'] > 25) and (current['rsi'] > 50)
        sell_signal = (current['close'] < current['dc_low']) and (current['adx'] > 25) and (current['rsi'] < 50)

        # Entry Logic
        if not has_position:
            if buy_signal:
                logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                if self.pm:
                    self.pm.update_position(base_qty, current["close"], "BUY")
            elif sell_signal:
                logger.info(f"SELL SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                if self.pm:
                    self.pm.update_position(base_qty, current["close"], "SELL") # Assuming SELL for short

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position
            # entry_price = self.pm.entry_price

            # Exit Long if Close < Mid Channel
            if pos_qty > 0 and current['close'] < current['dc_mid']:
                logger.info(f"EXIT LONG: Trend Reversal (Price < Mid Channel)")
                self.pm.update_position(abs(pos_qty), current["close"], "SELL")

            # Exit Short if Close > Mid Channel
            elif pos_qty < 0 and current['close'] > current['dc_mid']:
                logger.info(f"EXIT SHORT: Trend Reversal (Price > Mid Channel)")
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

        # Logic
        buy_signal = (current['close'] > current['dc_high']) and (current['adx'] > 25) and (current['rsi'] > 50)
        sell_signal = (current['close'] < current['dc_low']) and (current['adx'] > 25) and (current['rsi'] < 50)

        if buy_signal:
            return "BUY", 1.0, {"reason": "breakout_long", "rsi": current['rsi'], "adx": current['adx']}
        elif sell_signal:
            return "SELL", 1.0, {"reason": "breakout_short", "rsi": current['rsi'], "adx": current['adx']}

        return "HOLD", 0.0, {}

    def run(self):
        logger.info(f"Starting MCX Strategy for {self.symbol}")
        while True:
            if not is_market_open():
                logger.info("Market is closed. Sleeping...")
                time.sleep(300)
                continue

            self.fetch_data()
            self.calculate_indicators()
            self.check_signals()
            time.sleep(900)  # 15 minutes

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCX Zinc Breakout Strategy")
    parser.add_argument("--symbol", type=str, help="MCX Symbol (e.g., ZINCM05FEB26)")
    parser.add_argument("--underlying", type=str, help="Commodity Name (e.g., ZINC)")
    parser.add_argument("--port", type=int, default=5001, help="API Port")
    parser.add_argument("--api_key", type=str, help="API Key")

    # Multi-Factor Arguments
    parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
    parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%") # Escaped %
    parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
    parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")

    args = parser.parse_args()

    # Strategy Parameters
    PARAMS = {
        "period_rsi": 14,
        "period_adx": 14,
        "period_dc": 20,
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

    strategy = MCXStrategy(symbol, api_key, host, PARAMS)
    strategy.run()

# Backtesting support
DEFAULT_PARAMS = {
    "period_rsi": 14,
    "period_adx": 14,
    "period_dc": 20,
}
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = DEFAULT_PARAMS.copy()
    if params:
        strat_params.update(params)

    api_key = client.api_key if client and hasattr(client, "api_key") else "BACKTEST"
    host = client.host if client and hasattr(client, "host") else "http://127.0.0.1:5001"

    strat = MCXStrategy(symbol or "TEST", api_key, host, strat_params)
    return strat.generate_signal(df)
