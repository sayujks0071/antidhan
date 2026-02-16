#!/usr/bin/env python3
"""
MCX Aluminium Trend Strategy
MCX Commodity trading strategy with multi-factor analysis (MACD, RSI, ATR)
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
    from trading_utils import APIClient, PositionManager, is_market_open, calculate_rsi, calculate_atr, calculate_macd
except ImportError:
    try:
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_market_open, calculate_rsi, calculate_atr, calculate_macd
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, calculate_rsi, calculate_atr, calculate_macd
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            is_market_open = lambda: True
            calculate_rsi = lambda s, p: pd.Series(0, index=s.index)
            calculate_atr = lambda d, p: pd.Series(0, index=d.index)
            calculate_macd = lambda s, f, sl, si: (pd.Series(0, index=s.index), pd.Series(0, index=s.index), pd.Series(0, index=s.index))

# Setup Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("MCX_Aluminium_Trend")

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

        # MACD
        macd, sig, hist = calculate_macd(
            df["close"],
            fast=self.params.get("macd_fast", 12),
            slow=self.params.get("macd_slow", 26),
            signal=self.params.get("macd_signal", 9)
        )
        df["macd_line"] = macd
        df["macd_signal"] = sig
        df["macd_hist"] = hist

        # RSI
        df["rsi"] = calculate_rsi(df["close"], period=self.params.get("period_rsi", 14))

        # ATR
        df["atr"] = calculate_atr(df, period=self.params.get("period_atr", 14))

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
            base_qty = max(1, int(base_qty * 0.7)) # Should result in 1 usually unless base is high

        if not seasonality_ok and not has_position:
            logger.info("Seasonality Weak: Skipping new entries.")
            return

        # Entry Logic (Long)
        # MACD Line > Signal Line (Bullish Trend) AND RSI > 50 (Momentum)
        bullish_crossover = (current["macd_line"] > current["macd_signal"])
        momentum_ok = (current["rsi"] > 50)

        entry_signal = bullish_crossover and momentum_ok

        if not has_position:
            if entry_signal:
                logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, MACD={current['macd_line']:.2f}, Signal={current['macd_signal']:.2f}")
                if self.pm:
                    self.pm.update_position(base_qty, current["close"], "BUY")

        # Exit Logic
        elif has_position:
            pos_qty = self.pm.position

            # Exit if MACD Line < Signal Line (Trend Reversal) OR RSI < 40 (Momentum Lost)
            trend_reversal = (current["macd_line"] < current["macd_signal"])
            momentum_lost = (current["rsi"] < 40)

            exit_signal = trend_reversal or momentum_lost

            if exit_signal:
                reason = "Trend Reversal" if trend_reversal else "Momentum Lost"
                logger.info(f"EXIT: {reason}. Price={current['close']}, RSI={current['rsi']:.2f}")
                self.pm.update_position(abs(pos_qty), current["close"], "SELL" if pos_qty > 0 else "BUY")

    def generate_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        self.data = df
        self.calculate_indicators()

        current = self.data.iloc[-1]

        # MACD Line > Signal Line AND RSI > 50
        bullish_crossover = (current["macd_line"] > current["macd_signal"])
        momentum_ok = (current["rsi"] > 50)

        if bullish_crossover and momentum_ok:
            return "BUY", 1.0, {
                "reason": "signal_triggered",
                "rsi": current["rsi"],
                "macd": current["macd_line"],
                "signal": current["macd_signal"]
            }

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
    parser = argparse.ArgumentParser(description="MCX Aluminium Trend Strategy")
    parser.add_argument("--symbol", type=str, help="MCX Symbol (e.g., ALUMINIUMxxFEB26FUT)")
    parser.add_argument("--underlying", type=str, help="Commodity Name (e.g., ALUMINIUM)")
    parser.add_argument("--port", type=int, default=5001, help="API Port")
    parser.add_argument("--api_key", type=str, help="API Key")

    # Multi-Factor Arguments
    parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
    parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility %%")
    parser.add_argument("--seasonality_score", type=int, default=50, help="Seasonality Score (0-100)")
    parser.add_argument("--global_alignment_score", type=int, default=50, help="Global Alignment Score")

    # Strategy Parameters
    parser.add_argument("--period_rsi", type=int, default=14, help="RSI Period")
    parser.add_argument("--period_atr", type=int, default=14, help="ATR Period")
    parser.add_argument("--macd_fast", type=int, default=12, help="MACD Fast Period")
    parser.add_argument("--macd_slow", type=int, default=26, help="MACD Slow Period")
    parser.add_argument("--macd_signal", type=int, default=9, help="MACD Signal Period")

    args = parser.parse_args()

    # Strategy Parameters
    PARAMS = {
        "period_rsi": args.period_rsi,
        "period_atr": args.period_atr,
        "macd_fast": args.macd_fast,
        "macd_slow": args.macd_slow,
        "macd_signal": args.macd_signal,
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
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
}
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = DEFAULT_PARAMS.copy()
    if params:
        strat_params.update(params)

    api_key = client.api_key if client and hasattr(client, "api_key") else "BACKTEST"
    host = client.host if client and hasattr(client, "host") else "http://127.0.0.1:5001"

    strat = MCXStrategy(symbol or "TEST", api_key, host, strat_params)
    return strat.generate_signal(df)
