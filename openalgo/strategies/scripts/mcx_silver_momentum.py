#!/usr/bin/env python3
"""
MCX Silver Momentum Strategy
MCX Commodity trading strategy with RSI, ATR, and SMA analysis.
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
openalgo_root = os.path.dirname(strategies_dir)
repo_root = os.path.dirname(openalgo_root)

# Add paths for imports
sys.path.insert(0, utils_dir := os.path.join(strategies_dir, "utils"))
sys.path.insert(0, openalgo_root)
sys.path.insert(0, repo_root)

try:
    from trading_utils import APIClient, PositionManager, is_market_open, calculate_rsi, calculate_atr, calculate_sma
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_market_open, calculate_rsi, calculate_atr, calculate_sma
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, calculate_rsi, calculate_atr, calculate_sma
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            is_market_open = lambda *args, **kwargs: True
            calculate_rsi = lambda *args, **kwargs: pd.Series()
            calculate_atr = lambda *args, **kwargs: pd.Series()
            calculate_sma = lambda *args, **kwargs: pd.Series()

# Setup Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("MCX_Silver_Momentum")

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
            start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

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

        # RSI
        df["rsi"] = calculate_rsi(df["close"], period=self.params["period_rsi"])

        # ATR
        df["atr"] = calculate_atr(df, period=self.params["period_atr"])

        # SMA 50
        df["sma_50"] = calculate_sma(df["close"], period=50)

        self.data = df

    def get_monthly_atr(self):
        """Fetch daily data and calculate ATR for adaptive sizing."""
        if not self.client: return 0.0
        try:
            start_date = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
            end_date = datetime.now().strftime("%Y-%m-%d")
            df = self.client.history(
                symbol=self.symbol,
                interval="1d", # Daily
                exchange="MCX",
                start_date=start_date,
                end_date=end_date
            )
            if df.empty or len(df) < 15:
                return 0.0

            # Calculate ATR using utility function
            atr_series = calculate_atr(df, period=14)
            if atr_series.empty: return 0.0
            return atr_series.iloc[-1]
        except Exception as e:
            logger.error(f"Error calculating Monthly ATR: {e}")
            return 0.0

    def check_signals(self):
        """Check entry and exit conditions"""
        if self.data.empty or len(self.data) < 50:
            return

        current = self.data.iloc[-1]
        close = current['close']

        has_position = False
        if self.pm:
            has_position = self.pm.has_position()

        # Multi-Factor Checks
        seasonality_ok = self.params.get("seasonality_score", 50) > 40
        usd_vol = self.params.get("usd_inr_volatility", 0)
        usd_vol_high = usd_vol > 0.8

        # Position sizing adjustment for volatility
        base_qty = 1 # Default Futures Lot

        # Adaptive Sizing (Monthly ATR)
        monthly_atr = self.get_monthly_atr()
        if monthly_atr > 0 and self.pm:
             # Assuming 500k capital, 1% risk
             qty = self.pm.calculate_adaptive_quantity_monthly_atr(500000, 1.0, monthly_atr, close)
             if qty > 0:
                 base_qty = qty
                 logger.info(f"Adaptive Base Qty: {base_qty} (Monthly ATR: {monthly_atr:.2f})")

        if usd_vol_high:
            logger.warning("⚠️ High USD/INR Volatility: Trading effectively halted or reduced.")
            if usd_vol > 1.5:
                logger.warning("Volatility too high, skipping trade.")
                return

        if not seasonality_ok and not has_position:
            logger.info("Seasonality Weak: Skipping new entries.")
            return

        close = current['close']
        sma_50 = current['sma_50']
        rsi = current['rsi']
        atr = current['atr']

        # Entry Logic
        if not has_position:
            # BUY
            if close > sma_50 and rsi > 55:
                logger.info(f"BUY SIGNAL: Price={close}, SMA50={sma_50:.2f}, RSI={rsi:.2f}")
                if self.pm:
                    self.pm.update_position(base_qty, close, "BUY")
            # SELL (Short)
            elif close < sma_50 and rsi < 45:
                logger.info(f"SELL SIGNAL: Price={close}, SMA50={sma_50:.2f}, RSI={rsi:.2f}")
                if self.pm:
                    self.pm.update_position(base_qty, close, "SELL")

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position
            entry_price = self.pm.entry_price

            is_long = pos_qty > 0

            stop_loss_dist = 2 * atr
            take_profit_dist = 4 * atr

            exit_signal = False
            exit_reason = ""

            if is_long:
                if close < (entry_price - stop_loss_dist):
                    exit_signal = True
                    exit_reason = "Stop Loss"
                elif close > (entry_price + take_profit_dist):
                    exit_signal = True
                    exit_reason = "Take Profit"
                elif close < sma_50 or rsi < 40:
                     exit_signal = True
                     exit_reason = "Trend Reversal"
            else: # Short
                if close > (entry_price + stop_loss_dist):
                    exit_signal = True
                    exit_reason = "Stop Loss"
                elif close < (entry_price - take_profit_dist):
                    exit_signal = True
                    exit_reason = "Take Profit"
                elif close > sma_50 or rsi > 60:
                    exit_signal = True
                    exit_reason = "Trend Reversal"

            if exit_signal:
                logger.info(f"EXIT ({exit_reason}): Price={close}")
                self.pm.update_position(abs(pos_qty), close, "SELL" if is_long else "BUY")

    def generate_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        self.data = df
        self.calculate_indicators()

        current = self.data.iloc[-1]

        close = current['close']
        # Check if 'sma_50' exists (might not if not enough data)
        if 'sma_50' not in current or pd.isna(current['sma_50']):
             return "HOLD", 0.0, {}

        sma_50 = current['sma_50']
        rsi = current['rsi']

        # BUY
        if close > sma_50 and rsi > 55:
            return "BUY", 1.0, {"reason": f"Price > SMA50 & RSI({rsi:.1f}) > 55"}

        # SELL (Short)
        if close < sma_50 and rsi < 45:
             return "SELL", 1.0, {"reason": f"Price < SMA50 & RSI({rsi:.1f}) < 45"}

        return "HOLD", 0.0, {}

    def run(self):
        logger.info(f"Starting MCX Strategy for {self.symbol}")
        while True:
            if not is_market_open(exchange="MCX"):
                logger.info("Market is closed. Sleeping...")
                time.sleep(300)
                continue

            self.fetch_data()
            self.calculate_indicators()
            self.check_signals()
            time.sleep(900)  # 15 minutes

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCX Silver Momentum Strategy")
    # Escape percent sign in help to avoid formatting errors, and use placeholder to pass validation
    parser.add_argument("--symbol", type=str, help="MCX Symbol (e.g., SILVERMXXFEB26FUT)")
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
            else:
                logger.warning(f"Could not resolve symbol for {args.underlying}")

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
