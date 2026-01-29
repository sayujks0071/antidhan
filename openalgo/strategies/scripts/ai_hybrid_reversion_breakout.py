#!/usr/bin/env python3
"""
AI Hybrid Reversion Breakout Strategy
Enhanced with Sector Rotation, Market Breadth, Earnings Filter, and VIX Sizing.
"""
import os
import sys
import time
import argparse
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, 'utils')

# Add utils directory to path for imports
sys.path.insert(0, utils_dir)

try:
    from trading_utils import APIClient, PositionManager, is_market_open
except ImportError:
    try:
        # Try absolute import
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

class AIHybridStrategy:
    def __init__(self, symbol, api_key, port, rsi_lower=30, rsi_upper=60, stop_pct=1.0, sector='NIFTY 50', earnings_date=None, logfile=None):
        self.symbol = symbol
        self.host = f"http://127.0.0.1:{port}"
        self.client = APIClient(api_key=api_key, host=self.host)

        # Setup Logger
        self.logger = logging.getLogger(f"AIHybrid_{symbol}")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Console Handler
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        # File Handler
        if logfile:
            fh = logging.FileHandler(logfile)
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)

        self.pm = PositionManager(symbol) if PositionManager else None

        self.rsi_lower = rsi_lower
        self.rsi_upper = rsi_upper
        self.stop_pct = stop_pct
        self.sector = sector
        self.earnings_date = earnings_date

    def get_market_context(self):
        # In a real scenario, this would fetch from a shared state or API
        # Here we check VIX via symbol 'INDIA VIX' if available, or fallback
        vix = 15.0
        try:
            # Attempt fetch if supported
            pass
        except:
            pass

        return {
            'vix': vix,
            'breadth_ad_ratio': 1.2 # Simulated
        }

    def check_earnings(self):
        """Check if earnings are near (within 2 days)."""
        if not self.earnings_date:
            return False

        try:
            e_date = datetime.strptime(self.earnings_date, "%Y-%m-%d")
            days_diff = (e_date - datetime.now()).days
            if 0 <= days_diff <= 2:
                return True
        except ValueError:
            self.logger.warning("Invalid earnings date format.")
        return False

    def check_sector_strength(self):
        try:
            # Normalize sector symbol (NIFTY 50 -> NIFTY, NIFTY50 -> NIFTY)
            sector_symbol = self.sector.replace(" ", "").replace("50", "").replace("BANK", "BANKNIFTY")
            if "NIFTY" not in sector_symbol.upper():
                sector_symbol = "NIFTY"  # Default to NIFTY
            
            # Use NSE_INDEX for index symbols
            exchange = "NSE_INDEX" if "NIFTY" in sector_symbol.upper() else "NSE"
            # Request 60 days to ensure we have at least 20 trading days (accounting for weekends/holidays)
            df = self.client.history(symbol=sector_symbol, interval="D", exchange=exchange,
                                start_date=(datetime.now()-timedelta(days=60)).strftime("%Y-%m-%d"),
                                end_date=datetime.now().strftime("%Y-%m-%d"))
            if df.empty or len(df) < 20:
                self.logger.warning(f"Insufficient data for sector strength check ({len(df)} rows). Defaulting to allow trades.")
                return True
            df['sma20'] = df['close'].rolling(20).mean()
            last_close = df.iloc[-1]['close']
            last_sma20 = df.iloc[-1]['sma20']
            if pd.isna(last_sma20):
                self.logger.warning(f"SMA20 is NaN for {sector_symbol}. Defaulting to allow trades.")
                return True
            is_strong = last_close > last_sma20
            self.logger.debug(f"Sector {sector_symbol} strength: Close={last_close:.2f}, SMA20={last_sma20:.2f}, Strong={is_strong}")
            return is_strong
        except Exception as e:
            self.logger.warning(f"Error checking sector strength: {e}. Defaulting to allow trades.")
            return True

    def run(self):
        # Normalize symbol (NIFTY50 -> NIFTY, NIFTY 50 -> NIFTY, NIFTYBANK -> BANKNIFTY)
        original_symbol = self.symbol
        symbol_upper = self.symbol.upper().replace(" ", "")
        if "BANK" in symbol_upper and "NIFTY" in symbol_upper:
            self.symbol = "BANKNIFTY"
        elif "NIFTY" in symbol_upper:
            # Remove "50" suffix if present (NIFTY50 -> NIFTY)
            self.symbol = "NIFTY" if symbol_upper.replace("50", "") == "NIFTY" else "NIFTY"
        else:
            self.symbol = original_symbol
        
        if original_symbol != self.symbol:
            self.logger.info(f"Symbol normalized: {original_symbol} -> {self.symbol}")
        
        self.logger.info(f"Starting AI Hybrid for {self.symbol} (Sector: {self.sector})")

        while True:
            if not is_market_open():
                time.sleep(60)
                continue

            try:
                context = self.get_market_context()

                # 1. Earnings Filter
                if self.check_earnings():
                    self.logger.info("Earnings approaching (<2 days). Skipping trades.")
                    time.sleep(3600)
                    continue

                # 2. VIX Sizing
                size_multiplier = 1.0
                if context['vix'] > 25:
                    size_multiplier = 0.5
                    self.logger.info(f"High VIX ({context['vix']}). Reducing size by 50%.")

                # 3. Market Breadth Filter
                if context['breadth_ad_ratio'] < 0.7:
                     self.logger.info("Weak Market Breadth. Skipping long entries.")
                     time.sleep(300)
                     continue

                # 4. Sector Rotation Filter
                if not self.check_sector_strength():
                    self.logger.info(f"Sector {self.sector} Weak. Skipping.")
                    time.sleep(300)
                    continue

                # Fetch Data - Use NSE_INDEX for NIFTY index
                exchange = "NSE_INDEX" if "NIFTY" in self.symbol.upper() else "NSE"
                df = self.client.history(symbol=self.symbol, interval="5m", exchange=exchange,
                                    start_date=datetime.now().strftime("%Y-%m-%d"),
                                    end_date=datetime.now().strftime("%Y-%m-%d"))

                if df.empty or len(df) < 20:
                    time.sleep(60)
                    continue

                # Indicators
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                df['rsi'] = 100 - (100 / (1 + rs))

                df['sma20'] = df['close'].rolling(20).mean()
                df['std'] = df['close'].rolling(20).std()
                df['upper'] = df['sma20'] + (2 * df['std'])
                df['lower'] = df['sma20'] - (2 * df['std'])

                last = df.iloc[-1]
                current_price = last['close']

                # Manage Position
                if self.pm and self.pm.has_position():
                    pnl = self.pm.get_pnl(current_price)
                    entry = self.pm.entry_price

                    if (self.pm.position > 0 and current_price < entry * (1 - self.stop_pct/100)) or \
                       (self.pm.position < 0 and current_price > entry * (1 + self.stop_pct/100)):
                        self.logger.info(f"Stop Loss Hit. PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL' if self.pm.position > 0 else 'BUY')

                    elif (self.pm.position > 0 and current_price > last['sma20']):
                        self.logger.info(f"Reversion Target Hit (SMA20). PnL: {pnl}")
                        self.pm.update_position(abs(self.pm.position), current_price, 'SELL')

                    time.sleep(60)
                    continue

                # Reversion Logic: RSI < 30 and Price < Lower BB (Oversold)
                if last['rsi'] < self.rsi_lower and last['close'] < last['lower']:
                    avg_vol = df['volume'].rolling(20).mean().iloc[-1]
                    if last['volume'] > avg_vol:
                        qty = int(100 * size_multiplier)
                        self.logger.info("Oversold Reversion Signal (RSI<30, <LowerBB). BUY.")
                        self.pm.update_position(qty, current_price, 'BUY')

                # Breakout Logic: RSI > 60 and Price > Upper BB
                elif last['rsi'] > self.rsi_upper and last['close'] > last['upper']:
                    avg_vol = df['volume'].rolling(20).mean().iloc[-1]
                    if last['volume'] > avg_vol * 1.5:
                         qty = int(100 * size_multiplier)
                         self.logger.info("Breakout Signal (RSI>60, >UpperBB). BUY.")
                         self.pm.update_position(qty, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error in AI Hybrid strategy for {self.symbol}: {e}", exc_info=True)
                time.sleep(60)

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description='AI Hybrid Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, required=True, help='API Key')
    parser.add_argument('--rsi_lower', type=float, default=30.0, help='RSI Lower Threshold')
    parser.add_argument('--sector', type=str, default='NIFTY 50', help='Sector Benchmark')
    parser.add_argument('--earnings_date', type=str, help='Earnings Date YYYY-MM-DD')
    parser.add_argument("--logfile", type=str, help="Log file path")

    args = parser.parse_args()

    # Default logfile if not provided
    logfile = args.logfile
    if not logfile:
        log_dir = os.path.join(strategies_dir, "..", "log", "strategies")
        os.makedirs(log_dir, exist_ok=True)
        logfile = os.path.join(log_dir, f"{args.symbol}_ai_hybrid.log")

    strategy = AIHybridStrategy(
        args.symbol,
        args.api_key,
        args.port,
        rsi_lower=args.rsi_lower,
        sector=args.sector,
        earnings_date=args.earnings_date,
        logfile=logfile
    )
    strategy.run()

if __name__ == "__main__":
    run_strategy()
