#!/usr/bin/env python3
"""
[Nifty Smart Trend OI] - NIFTY Options (OpenAlgo Web UI Compatible)
Combines EMA Trend Following with PCR Sentiment to trade Credit Spreads or Iron Condors.
"""
import sys
from strategy_preamble import BaseStrategy
from optionchain_utils import (
    OptionChainClient,
    OptionPositionTracker,
    choose_nearest_expiry,
    is_chain_valid,
    safe_float,
    safe_int
)
from strategy_common import SignalDebouncer, TradeLimiter, format_kv

class PrintLogger:
    def info(self, msg): print(msg, flush=True)
    def warning(self, msg): print(msg, flush=True)
    def error(self, msg, exc_info=False): print(msg, flush=True)
    def debug(self, msg): print(msg, flush=True)

class NiftySmartTrendOI(BaseStrategy):
    def setup(self):
        self.symbol = "NIFTY"
        self.exchange = "NSE"
        self.name = "Nifty_Smart_Trend_OI"

        self.params = {
            "ema_fast": getattr(self, "ema_fast", 9),
            "ema_slow": getattr(self, "ema_slow", 21),
            "min_spread_dist": getattr(self, "min_spread_dist", 50),
            "max_spread_dist": getattr(self, "max_spread_dist", 150),
            "stop_loss_pts": getattr(self, "stop_loss_pts", 20),
            "target_pts": getattr(self, "target_pts", 40),
            "base_qty": getattr(self, "base_qty", 50),
            "polling_interval": getattr(self, "polling_interval", 60)
        }

        self.logger = PrintLogger()
        if self.api_key:
            self.option_client = OptionChainClient(api_key=self.api_key, host=self.host)
        else:
            self.option_client = None

        self.position = OptionPositionTracker(self.name)
        self.signal_debouncer = SignalDebouncer(cooldown_sec=120)
        self.trade_limiter = TradeLimiter(max_trades_per_day=3)
        self.last_run_time = 0

    def cycle(self):
        # We handle loop inside `run` in older scripts, but since we inherit from BaseStrategy,
        # `cycle` is called periodically by `run`.
        pass

    def run(self):
        self.logger.info("=" * 60)
        self.logger.info(f"STARTING: {self.name} (Smart Trend + Options OI)")
        self.logger.info(format_kv("Symbol", self.symbol))
        self.logger.info(format_kv("EMA Fast", self.params["ema_fast"]))
        self.logger.info(format_kv("EMA Slow", self.params["ema_slow"]))
        self.logger.info("=" * 60)

        import time

        while True:
            try:
                if not self.ignore_time and not self.is_market_open(exchange="NSE"):
                    self.logger.info("[WAIT] Market is closed. Sleeping 60s...")
                    time.sleep(60)
                    continue

                if self.trade_limiter.is_limit_reached():
                    self.logger.warning("[LIMIT] Max daily trades reached. Sleeping 5m...")
                    time.sleep(300)
                    continue

                self.execute_logic()

            except Exception as e:
                self.logger.error(f"[ERROR] Main Loop Exception: {e}", exc_info=True)

            time.sleep(self.params["polling_interval"])

    def is_market_open(self, exchange="NSE"):
        from trading_utils import is_market_open
        return is_market_open(exchange)

    def execute_logic(self):
        if not self.option_client or not self.client:
            self.logger.error("API Clients not initialized. Skipping execution.")
            return

        self.logger.debug("--- Polling Cycle ---")

        # 1. Fetch Option Chain data
        chain_response = self.option_client.option_chain(self.symbol)
        if not chain_response or chain_response.get("status") != "success":
            self.logger.warning("[DATA] Failed to fetch option chain.")
            return

        expiries = chain_response.get("expiries", [])
        nearest_expiry = choose_nearest_expiry(expiries)
        if not nearest_expiry:
            self.logger.warning("[DATA] No valid expiry found.")
            return

        chain_data = chain_response.get("chain", [])
        valid, msg = is_chain_valid(chain_response)
        if not valid:
            self.logger.warning(f"[DATA] Invalid Chain: {msg}")
            return

        # 2. Extract spot price & basic metrics
        spot_price = safe_float(chain_response.get("metadata", {}).get("spot_price"))
        if spot_price <= 0:
            self.logger.warning("[DATA] Spot price unavailable.")
            return

        self.logger.debug(f"Spot: {spot_price:.2f} | Expiry: {nearest_expiry}")

        # 3. Calculate PCR (Volume and OI)
        total_ce_oi = 0
        total_pe_oi = 0
        total_ce_vol = 0
        total_pe_vol = 0

        for item in chain_data:
            total_ce_oi += safe_int(item.get("ce", {}).get("oi"))
            total_pe_oi += safe_int(item.get("pe", {}).get("oi"))
            total_ce_vol += safe_int(item.get("ce", {}).get("volume"))
            total_pe_vol += safe_int(item.get("pe", {}).get("volume"))

        pcr_oi = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 1.0
        pcr_vol = total_pe_vol / total_ce_vol if total_ce_vol > 0 else 1.0

        # 4. Fetch Historical Data for EMA
        df = self.client.history(symbol=self.symbol, exchange="NSE_INDEX", interval="5m", days=3)
        if df.empty or len(df) < self.params["ema_slow"] + 5:
            self.logger.warning("[DATA] Insufficient historical data for EMAs.")
            return

        # 5. Calculate EMAs
        df["ema_fast"] = self.calculate_ema(df["close"], period=self.params["ema_fast"])
        df["ema_slow"] = self.calculate_ema(df["close"], period=self.params["ema_slow"])

        current = df.iloc[-1]
        prev = df.iloc[-2]

        bullish_crossover = current["ema_fast"] > current["ema_slow"] and prev["ema_fast"] <= prev["ema_slow"]
        bearish_crossover = current["ema_fast"] < current["ema_slow"] and prev["ema_fast"] >= prev["ema_slow"]

        trend = "Neutral"
        if current["ema_fast"] > current["ema_slow"]: trend = "Bullish"
        if current["ema_fast"] < current["ema_slow"]: trend = "Bearish"

        self.logger.info(f"[METRICS] Spot: {spot_price:.2f} | Trend: {trend} | PCR_OI: {pcr_oi:.2f} | PCR_Vol: {pcr_vol:.2f}")

        # Check existing positions
        if self.position.is_active():
            # Basic Management
            self.logger.info("[POS] Active position monitoring... (Placeholder)")
            # Complex exit logic would go here
            return

        # Entry Logic
        if bullish_crossover and pcr_oi > 1.0:
            if self.signal_debouncer.should_execute("BULLISH_SPREAD"):
                self.logger.info(">>> ENTRY TRIGGERED: Bullish Setup (EMA Crossover + PCR > 1)")
                self.execute_trade("BULL_PUT_SPREAD", spot_price, chain_data)
        elif bearish_crossover and pcr_oi < 1.0:
            if self.signal_debouncer.should_execute("BEARISH_SPREAD"):
                self.logger.info(">>> ENTRY TRIGGERED: Bearish Setup (EMA Crossover + PCR < 1)")
                self.execute_trade("BEAR_CALL_SPREAD", spot_price, chain_data)

    def execute_trade(self, strategy_type, spot, chain):
        # Placeholder for complex multi-leg execution
        self.logger.info(f"[EXEC] Deploying {strategy_type} around spot {spot:.2f}...")
        self.position.open_position(strategy_type, self.params["base_qty"], {"spot_at_entry": spot})
        self.trade_limiter.record_trade()

if __name__ == "__main__":
    NiftySmartTrendOI.cli()
