#!/usr/bin/env python3
"""
MCX Gold Price Action Strategy
MCX Commodity trading strategy with multi-factor analysis (Price Action + Smart Momentum)
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
# Add openalgo root to sys.path to resolve 'utils' package
openalgo_root = os.path.dirname(strategies_dir)
sys.path.insert(0, openalgo_root)
# Add strategies/utils to sys.path to resolve 'trading_utils'
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
            is_market_open = lambda *args, **kwargs: True

# Setup Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("MCX_Gold_Price_Action")

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
                interval="15m",  # MCX typically uses 5m, 15m, or 1h
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

        # EMA 9 and 21
        df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
        df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()

        # RSI 14
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.params.get("period_rsi", 14)).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.params.get("period_rsi", 14)).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))

        # ATR 14
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df["atr"] = true_range.rolling(window=self.params.get("period_atr", 14)).mean()

        # ADX 14
        plus_dm = df['high'].diff()
        minus_dm = df['low'].diff()
        plus_dm = np.where(plus_dm < 0, 0, plus_dm)
        minus_dm = np.where(minus_dm > 0, 0, minus_dm)

        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - df['close'].shift(1)).abs()
        tr3 = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_adx = tr.rolling(window=14).mean()

        plus_di = 100 * (pd.Series(plus_dm).ewm(alpha=1/14).mean() / atr_adx)
        minus_di = 100 * (pd.Series(minus_dm).abs().ewm(alpha=1/14).mean() / atr_adx)
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        df["adx"] = dx.rolling(window=14).mean()

        self.data = df

    def check_signals(self):
        """Check entry and exit conditions"""
        if self.data.empty or len(self.data) < 50:
            return

        current = self.data.iloc[-1]

        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.params.get("seasonality_score", 50) > 40
        usd_vol_high = self.params.get("usd_inr_volatility", 0) > 1.0

        # Position sizing adjustment for volatility
        base_qty = 1
        if usd_vol_high:
            logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(base_qty * 0.7))

        if not seasonality_ok and not has_position:
            logger.info("Seasonality Weak: Skipping new entries.")
            return

        # Entry Logic
        if not has_position:
            # Buy: Close > EMA(21) AND RSI > 55 AND ADX > 25
            buy_signal = (current['close'] > current['ema_21']) and (current['rsi'] > 55) and (current['adx'] > 25)
            # Sell: Close < EMA(21) AND RSI < 45 AND ADX > 25
            sell_signal = (current['close'] < current['ema_21']) and (current['rsi'] < 45) and (current['adx'] > 25)

            if buy_signal:
                logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                if self.pm:
                    self.pm.update_position(base_qty, current["close"], "BUY")
            elif sell_signal:
                logger.info(f"SELL SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                if self.pm:
                    self.pm.update_position(base_qty, current["close"], "SELL") # Shorting requires special handling usually, assuming pm handles negative

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position
            entry_price = self.pm.entry_price

            exit_signal = False
            reason = ""

            if pos_qty > 0: # Long Position
                # Exit if Close < EMA(9) or RSI < 40
                if current['close'] < current['ema_9']:
                    exit_signal = True
                    reason = "EMA Cross (Trend Reversal)"
                elif current['rsi'] < 40:
                    exit_signal = True
                    reason = "RSI Weakness"

            elif pos_qty < 0: # Short Position
                 # Exit if Close > EMA(9) or RSI > 60
                if current['close'] > current['ema_9']:
                    exit_signal = True
                    reason = "EMA Cross (Trend Reversal)"
                elif current['rsi'] > 60:
                    exit_signal = True
                    reason = "RSI Strength"

            if exit_signal:
                logger.info(f"EXIT: {reason}")
                self.pm.update_position(abs(pos_qty), current["close"], "SELL" if pos_qty > 0 else "BUY")

    def generate_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        self.data = df
        self.calculate_indicators()

        current = self.data.iloc[-1]

        # Logic mirroring check_signals
        buy_signal = (current['close'] > current['ema_21']) and (current['rsi'] > 55) and (current['adx'] > 25)
        sell_signal = (current['close'] < current['ema_21']) and (current['rsi'] < 45) and (current['adx'] > 25)

        if buy_signal:
            return "BUY", 1.0, {"reason": "Price Action Buy", "rsi": current['rsi'], "adx": current['adx']}
        elif sell_signal:
            return "SELL", 1.0, {"reason": "Price Action Sell", "rsi": current['rsi'], "adx": current['adx']}

        return "HOLD", 0.0, {}

    def run(self):
        logger.info(f"Starting MCX Strategy for {self.symbol}")
        while True:
            # MCX Market Hours Check
            if not is_market_open("MCX"): # Pass explicit exchange if needed, or rely on implementation
                logger.info("Market is closed. Sleeping...")
                time.sleep(300)
                continue

            self.fetch_data()
            self.calculate_indicators()
            self.check_signals()
            time.sleep(900)  # 15 minutes

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCX Commodity Strategy")
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
                # Last resort import
                sys.path.append(utils_dir)
                try:
                    from symbol_resolver import SymbolResolver
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
    "period_atr": 14,
}
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = DEFAULT_PARAMS.copy()
    if params:
        strat_params.update(params)

    api_key = client.api_key if client and hasattr(client, "api_key") else "BACKTEST"
    host = client.host if client and hasattr(client, "host") else "http://127.0.0.1:5001"

    strat = MCXStrategy(symbol or "TEST", api_key, host, strat_params)
    return strat.generate_signal(df)
