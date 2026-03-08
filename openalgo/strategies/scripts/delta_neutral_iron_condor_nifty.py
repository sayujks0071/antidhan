#!/usr/bin/env python3
import sys
import os
import argparse
import logging
from strategy_preamble import BaseStrategy
from option_analytics import calculate_greeks, calculate_max_pain

# Configure logging
logger = logging.getLogger("DeltaNeutralIronCondor")

class DeltaNeutralIronCondor(BaseStrategy):
    def __init__(self, **kwargs):
        kwargs.setdefault("symbol", "NIFTY")
        super().__init__(**kwargs)
        self.qty = getattr(self, "qty", 50)
        self.max_vix = getattr(self, "max_vix", 30)
        self.sentiment_score = getattr(self, "sentiment_score", None)

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--sentiment_score", type=float, default=None, help="External Sentiment Score (0.0-1.0)")
        parser.add_argument("--max_vix", type=float, default=30.0, help="Max VIX threshold")

    def get_vix(self):
        q = self.client.get_quote("INDIA VIX", "NSE")
        return float(q['ltp']) if q and 'ltp' in q else 15.0

    def select_strikes(self, spot, vix, chain_data):
        """
        Select strikes based on Delta and VIX.
        """
        # Calculate Max Pain
        max_pain = calculate_max_pain(chain_data)
        self.logger.info(f"Max Pain Strike: {max_pain}")

        # Use Max Pain as center if close to Spot (within 1%)
        center_price = spot
        if max_pain and abs(spot - max_pain) < (spot * 0.01):
            self.logger.info("Using Max Pain as Center Price for Strike Selection")
            center_price = max_pain

        # Target Delta for Shorts
        target_delta = 0.20

        # Adjust Wing Width based on VIX
        wing_width = 200 # Default
        if vix >= 20:
            wing_width = 400
            self.logger.info(f"High VIX ({vix}) -> Widening Wings to {wing_width}")
        elif vix < 12:
            wing_width = 100
            self.logger.info(f"Low VIX ({vix}) -> Narrowing Wings to {wing_width}")
        else:
            self.logger.info(f"Medium VIX ({vix}) -> Default Wings {wing_width}")

        # Delta-Based Selection Logic
        ce_short = None
        pe_short = None

        try:
            strikes = sorted([item for item in chain_data if 'strike' in item], key=lambda x: x['strike'])
            best_ce_diff = 1.0
            best_pe_diff = 1.0

            # Assumptions
            T = 7/365.0
            r = 0.06

            for item in strikes:
                strike = item['strike']

                def get_iv(itm, type_key):
                    iv = itm.get(f'{type_key}_iv', 0)
                    if iv == 0:
                        iv = itm.get(type_key, {}).get('iv', 0)
                    if iv > 0:
                         return iv / 100.0
                    return vix / 100.0

                iv_ce = get_iv(item, 'ce')
                ce_greeks = calculate_greeks(spot, strike, T, r, iv_ce, 'ce')
                ce_delta = ce_greeks.get('delta', 0.5)

                if strike > spot and abs(ce_delta - target_delta) < best_ce_diff:
                    best_ce_diff = abs(ce_delta - target_delta)
                    ce_short = strike

                iv_pe = get_iv(item, 'pe')
                pe_greeks = calculate_greeks(spot, strike, T, r, iv_pe, 'pe')
                pe_delta = abs(pe_greeks.get('delta', -0.5))

                if strike < spot and abs(pe_delta - target_delta) < best_pe_diff:
                    best_pe_diff = abs(pe_delta - target_delta)
                    pe_short = strike

            self.logger.info(f"Delta Search Results: CE Short {ce_short} (Diff: {best_ce_diff:.4f}), PE Short {pe_short} (Diff: {best_pe_diff:.4f})")

        except Exception as e:
            self.logger.error(f"Delta calculation failed: {e}")
            ce_short = None
            pe_short = None

        # Fallback to ATM + Width
        atm = round(center_price / 50) * 50

        if not ce_short:
            ce_short = atm + wing_width
        if not pe_short:
            pe_short = atm - wing_width

        # Longs (Wings)
        ce_long = ce_short + wing_width
        pe_long = pe_short - wing_width

        return {
            "ce_short": ce_short,
            "pe_short": pe_short,
            "ce_long": ce_long,
            "pe_long": pe_long
        }

    def execute(self):
        self.logger.info(f"Starting execution for {self.symbol}")

        if not self.client:
            self.logger.error("No API client available. Cannot execute strategy.")
            return

        vix = self.get_vix()
        self.logger.info(f"Current VIX: {vix}")

        # VIX Filters
        if vix < 12:
            self.logger.warning(f"VIX {vix} < 12. Too low for Iron Condor (Low Premium/High Gamma Risk). Skipping.")
            return

        if vix > self.max_vix:
            self.logger.warning(f"VIX {vix} > {self.max_vix}. Reducing Quantity by 50%.")
            self.qty = int(self.qty * 0.5)

        # Sentiment Filter
        if self.sentiment_score is not None:
            self.logger.info(f"Checking Sentiment Score: {self.sentiment_score}")
            # Score 0 (Negative) to 1 (Positive), 0.5 Neutral
            # Iron Condor is Neutral. Avoid if sentiment is extreme.
            dist_from_neutral = abs(self.sentiment_score - 0.5)
            if dist_from_neutral > 0.3: # < 0.2 or > 0.8
                self.logger.warning(f"Sentiment Score {self.sentiment_score} is strongly directional. Iron Condor risk is high. Skipping.")
                return

        quote = self.client.get_quote(self.symbol, "NSE")
        spot = float(quote['ltp']) if quote and 'ltp' in quote else 0
        if spot == 0:
            self.logger.error("Could not fetch spot price.")
            return

        self.logger.info(f"Spot: {spot}")

        # Fetch Chain
        chain_response = self.client.option_chain(self.symbol)
        chain = chain_response.get("chain", []) if isinstance(chain_response, dict) else []
        if not chain:
            self.logger.error("Could not fetch option chain.")
            return

        strikes = self.select_strikes(spot, vix, chain)
        self.logger.info(f"Selected Strikes: {strikes}")

        # Place Orders (Mock)
        self.logger.info(f"Placing orders for {self.qty} qty...")

        # In real scenario:
        # self.client.placesmartorder(...)

        self.logger.info("Strategy execution completed (Simulation).")

    def run(self):
        self.execute()

if __name__ == "__main__":
    DeltaNeutralIronCondor.cli()
