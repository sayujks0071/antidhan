#!/usr/bin/env python3
"""
MCX Natural Gas Trend Strategy
MCX Commodity trading strategy with multi-factor analysis: SMA Crossover + RSI + ADX
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
# Add project root (openalgo folder) to path to allow 'from utils import httpx_client'
project_root = os.path.dirname(strategies_dir)
sys.path.insert(0, project_root)

try:
    from trading_utils import (
        APIClient,
        PositionManager,
        is_market_open,
        calculate_sma,
        calculate_rsi,
        calculate_adx
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
            calculate_adx
        )
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import (
                APIClient,
                PositionManager,
                is_market_open,
                calculate_sma,
                calculate_rsi,
                calculate_adx
            )
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            is_market_open = lambda: True
            calculate_sma = lambda s, p: s.rolling(p).mean()
            calculate_rsi = lambda s, p: s
            calculate_adx = lambda df, p: pd.Series(0, index=df.index)

# Setup Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("MCX_NATURALGAS_TREND")

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
            # Fetch enough history for 50-period SMA + buffer
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

        # Calculate indicators
        period_rsi = self.params.get("period_rsi", 14)
        period_adx = self.params.get("period_adx", 14)
        period_fast = self.params.get("period_sma_fast", 20)
        period_slow = self.params.get("period_sma_slow", 50)

        df["rsi"] = calculate_rsi(df["close"], period=period_rsi)
        df["adx"] = calculate_adx(df, period=period_adx)
        df["sma_fast"] = calculate_sma(df["close"], period=period_fast)
        df["sma_slow"] = calculate_sma(df["close"], period=period_slow)

        self.data = df.dropna()

    def check_signals(self):
        """Check entry and exit conditions"""
        if self.data.empty or len(self.data) < 2:
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

        rsi_buy_threshold = self.params.get("rsi_buy", 55)
        rsi_sell_threshold = self.params.get("rsi_sell", 45)
        adx_threshold = self.params.get("adx_threshold", 25)

        # Entry Logic: SMA Crossover + RSI + ADX
        # Long Entry
        buy_condition = (
            (current["sma_fast"] > current["sma_slow"]) and
            (current["rsi"] > rsi_buy_threshold) and
            (current["adx"] > adx_threshold)
        )

        # Exit Logic
        # Exit Long
        sell_condition = (
            (current["sma_fast"] < current["sma_slow"]) or
            (current["rsi"] < rsi_sell_threshold)
        )

        if not has_position:
            if buy_condition:
                logger.info(f"BUY SIGNAL: Price={current['close']}, RSI={current['rsi']:.2f}, ADX={current['adx']:.2f}")
                if self.pm:
                    self.pm.update_position(base_qty, current["close"], "BUY")

        elif has_position:
            pos_qty = self.pm.position

            if sell_condition and pos_qty > 0:
                logger.info(f"EXIT: Trend Faded or Reversal")
                self.pm.update_position(abs(pos_qty), current["close"], "SELL")

            # Note: Short logic could be added similarly if params support it
            # For commodities, often long-only or distinct short logic is used.
            # Assuming Long-Only for now based on "Trend" description typically implying capture up moves,
            # but usually trends can be both ways. Adding Short logic just in case:

            short_condition = (
                (current["sma_fast"] < current["sma_slow"]) and
                (current["rsi"] < rsi_sell_threshold) and
                (current["adx"] > adx_threshold)
            )

            buy_cover_condition = (
                (current["sma_fast"] > current["sma_slow"]) or
                (current["rsi"] > rsi_buy_threshold)
            )

            if pos_qty < 0 and buy_cover_condition:
                 logger.info(f"EXIT SHORT: Trend Faded or Reversal")
                 self.pm.update_position(abs(pos_qty), current["close"], "BUY")

    def generate_signal(self, df):
        """Generate signal for backtesting"""
        if df.empty:
            return "HOLD", 0.0, {}

        self.data = df
        self.calculate_indicators()

        if self.data.empty:
             return "HOLD", 0.0, {}

        current = self.data.iloc[-1]

        rsi_buy_threshold = self.params.get("rsi_buy", 55)
        rsi_sell_threshold = self.params.get("rsi_sell", 45)
        adx_threshold = self.params.get("adx_threshold", 25)

        buy_condition = (
            (current["sma_fast"] > current["sma_slow"]) and
            (current["rsi"] > rsi_buy_threshold) and
            (current["adx"] > adx_threshold)
        )

        sell_condition = (
            (current["sma_fast"] < current["sma_slow"]) or
            (current["rsi"] < rsi_sell_threshold)
        )

        if buy_condition:
            return "BUY", 1.0, {"reason": "trend_confirmed"}
        elif sell_condition:
            return "SELL", 1.0, {"reason": "trend_reversal"}

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
    parser = argparse.ArgumentParser(description="MCX Natural Gas Trend Strategy")
    parser.add_argument("--symbol", type=str, help="MCX Symbol (e.g., NATURALGASM05FEB26FUT)")
    parser.add_argument("--underlying", type=str, help="Commodity Name (e.g., NATURALGAS)")
    parser.add_argument("--port", type=int, default=5001, help="API Port")
    parser.add_argument("--api_key", type=str, help="API Key")

    # Multi-Factor Arguments
    parser.add_argument("--usd_inr_trend", type=str, default="Neutral", help="USD/INR Trend")
    parser.add_argument("--usd_inr_volatility", type=float, default=0.0, help="USD/INR Volatility (Percentage)")
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
                # Fallback import attempt
                try:
                    sys.path.append(utils_dir)
                    from symbol_resolver import SymbolResolver
                except ImportError:
                    SymbolResolver = None

        if SymbolResolver:
            resolver = SymbolResolver()
            res = resolver.resolve({"underlying": args.underlying, "type": "FUT", "exchange": "MCX"})
            if res:
                symbol = res
                logger.info(f"Resolved {args.underlying} -> {symbol}")
            else:
                 # Fallback if resolver returns None or fails
                 logger.warning(f"Could not resolve {args.underlying}, defaulting to constructed symbol")
                 symbol = f"{args.underlying}FUT" # Placeholder
        else:
             logger.warning("SymbolResolver not found.")

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
    "period_adx": 14,
    "period_sma_fast": 20,
    "period_sma_slow": 50,
}
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = DEFAULT_PARAMS.copy()
    if params:
        strat_params.update(params)

    api_key = client.api_key if client and hasattr(client, "api_key") else "BACKTEST"
    host = client.host if client and hasattr(client, "host") else "http://127.0.0.1:5001"

    strat = MCXStrategy(symbol or "TEST", api_key, host, strat_params)
    return strat.generate_signal(df)
