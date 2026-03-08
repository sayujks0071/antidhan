#!/usr/bin/env python3
"""
MCX Zinc Trend Strategy
MCX Commodity trading strategy with multi-factor analysis using ADX, RSI, ATR, and Moving Averages.
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

# Import indicator functions separately to prevent breaking core utils import fallback
try:
    from trading_utils import calculate_rsi, calculate_atr, calculate_adx, calculate_sma
except ImportError:
    try:
        from utils.trading_utils import calculate_rsi, calculate_atr, calculate_adx, calculate_sma
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import calculate_rsi, calculate_atr, calculate_adx, calculate_sma
        except ImportError:
            calculate_rsi = None
            calculate_atr = None
            calculate_adx = None
            calculate_sma = None

# Setup Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("MCX_ZINC_TREND_STRATEGY")

class MCXZincTrendStrategy:
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
            start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

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

        period_rsi = self.params.get("period_rsi", 14)
        period_atr = self.params.get("period_atr", 14)
        period_adx = self.params.get("period_adx", 14)
        period_sma_fast = self.params.get("period_sma_fast", 20)
        period_sma_slow = self.params.get("period_sma_slow", 50)

        if calculate_rsi and calculate_atr and calculate_adx and calculate_sma:
            df["rsi"] = calculate_rsi(df["close"], period=period_rsi)
            df["atr"] = calculate_atr(df, period=period_atr)
            df["adx"] = calculate_adx(df, period=period_adx)
            df["sma_fast"] = calculate_sma(df["close"], period=period_sma_fast)
            df["sma_slow"] = calculate_sma(df["close"], period=period_sma_slow)
        else:
            # Fallback inline calculation
            # RSI
            delta = df["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period_rsi).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period_rsi).mean()
            rs = gain / loss
            df["rsi"] = 100 - (100 / (1 + rs))

            # ATR
            high_low = df["high"] - df["low"]
            high_close = (df["high"] - df["close"].shift()).abs()
            low_close = (df["low"] - df["close"].shift()).abs()
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            df["atr"] = true_range.rolling(window=period_atr).mean()

            # SMA
            df["sma_fast"] = df["close"].rolling(window=period_sma_fast).mean()
            df["sma_slow"] = df["close"].rolling(window=period_sma_slow).mean()

            # ADX approximation
            plus_dm = df['high'].diff()
            minus_dm = df['low'].diff()
            plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
            minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)

            tr_series = true_range
            atr_series = df["atr"]

            plus_di = 100 * (pd.Series(plus_dm, index=df.index).ewm(alpha=1/period_adx, min_periods=period_adx).mean() / atr_series)
            minus_di = 100 * (pd.Series(minus_dm, index=df.index).ewm(alpha=1/period_adx, min_periods=period_adx).mean() / atr_series)

            dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
            df["adx"] = dx.rolling(window=period_adx).mean()

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

        adx_threshold = self.params.get("adx_threshold", 25)
        rsi_buy = self.params.get("rsi_buy", 55)
        rsi_sell = self.params.get("rsi_sell", 45)

        # Position sizing adjustment for volatility
        base_qty = 1
        if usd_vol_high:
            logger.warning("⚠️ High USD/INR Volatility: Reducing position size by 30%.")
            base_qty = max(1, int(round(base_qty * 0.7)))

        if not seasonality_ok and not has_position:
            logger.info("Seasonality Weak: Skipping new entries.")
            return

        if not global_alignment_ok and not has_position:
             logger.info("Global Alignment Weak: Skipping new entries.")
             return

        # Condition Flags
        uptrend = (current['sma_fast'] > current['sma_slow'])
        downtrend = (current['sma_fast'] < current['sma_slow'])
        strong_trend = (current['adx'] > adx_threshold)

        # Entry Logic
        if not has_position:
            # BUY SIGNAL
            if uptrend and strong_trend and (current['rsi'] > rsi_buy):
                logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                if self.pm:
                    self.pm.update_position(base_qty, current["close"], "BUY")

            # SELL SIGNAL
            elif downtrend and strong_trend and (current['rsi'] < rsi_sell):
                logger.info(f"SELL SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                if self.pm:
                    self.pm.update_position(base_qty, current["close"], "SELL")

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position

            if pos_qty > 0: # Long position
                if (current['close'] < current['sma_fast']) or (current['rsi'] < 40):
                    logger.info(f"EXIT BUY: Trend Faded. Price={current['close']}, RSI={current['rsi']:.2f}")
                    if self.pm:
                        self.pm.update_position(abs(pos_qty), current["close"], "SELL")

            elif pos_qty < 0: # Short position
                if (current['close'] > current['sma_fast']) or (current['rsi'] > 60):
                     logger.info(f"EXIT SELL: Trend Faded. Price={current['close']}, RSI={current['rsi']:.2f}")
                     if self.pm:
                         self.pm.update_position(abs(pos_qty), current["close"], "BUY")

    def generate_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty or len(df) < 50:
            return "HOLD", 0.0, {}

        self.data = df
        self.calculate_indicators()

        current = self.data.iloc[-1]
        prev = self.data.iloc[-2]

        adx_threshold = self.params.get("adx_threshold", 25)
        rsi_buy = self.params.get("rsi_buy", 55)
        rsi_sell = self.params.get("rsi_sell", 45)

        uptrend_current = (current['sma_fast'] > current['sma_slow'])
        downtrend_current = (current['sma_fast'] < current['sma_slow'])
        strong_trend_current = (current['adx'] > adx_threshold)

        # Entry Signals
        if uptrend_current and strong_trend_current and (current['rsi'] > rsi_buy):
            return "BUY", 1.0, {"reason": "Trend_Momentum_Buy", "rsi": current['rsi'], "adx": current['adx']}

        if downtrend_current and strong_trend_current and (current['rsi'] < rsi_sell):
            return "SELL", 1.0, {"reason": "Trend_Momentum_Sell", "rsi": current['rsi'], "adx": current['adx']}

        # Exit Signals (Checking crossovers to emit only once)
        # Exit Buy: Close crosses below SMA Fast
        if (prev['close'] >= prev['sma_fast']) and (current['close'] < current['sma_fast']):
             return "EXIT_BUY", 1.0, {"reason": "Exit_Buy_SMA_Cross", "close": current['close'], "sma_fast": current['sma_fast']}

        # Exit Sell: Close crosses above SMA Fast
        if (prev['close'] <= prev['sma_fast']) and (current['close'] > current['sma_fast']):
             return "EXIT_SELL", 1.0, {"reason": "Exit_Sell_SMA_Cross", "close": current['close'], "sma_fast": current['sma_fast']}

        return "HOLD", 0.0, {}

    def run(self):
        logger.info(f"Starting MCX Zinc Trend Strategy for {self.symbol}")
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
    parser = argparse.ArgumentParser(description="MCX Commodity Strategy")
    parser.add_argument("--symbol", type=str, help="MCX Symbol (e.g., <ZINC_SYMBOL_FUT>)")
    parser.add_argument("--underlying", type=str, help="Commodity Name (e.g., ZINC)")
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
        "period_adx": 14,
        "period_sma_fast": 20,
        "period_sma_slow": 50,
        "rsi_buy": 55,
        "rsi_sell": 45,
        "adx_threshold": 25,
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
                try:
                    from openalgo.strategies.utils.symbol_resolver import SymbolResolver
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

    strategy = MCXZincTrendStrategy(symbol, api_key, host, PARAMS)
    strategy.run()

# Backtesting support
DEFAULT_PARAMS = {
    "period_rsi": 14,
    "period_atr": 14,
    "period_adx": 14,
    "period_sma_fast": 20,
    "period_sma_slow": 50,
    "rsi_buy": 55,
    "rsi_sell": 45,
    "adx_threshold": 25,
}

def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = DEFAULT_PARAMS.copy()
    if params:
        strat_params.update(params)

    api_key = client.api_key if client and hasattr(client, "api_key") else "BACKTEST"
    host = client.host if client and hasattr(client, "host") else "http://127.0.0.1:5001"

    strat = MCXZincTrendStrategy(symbol or "TEST", api_key, host, strat_params)
    return strat.generate_signal(df)
