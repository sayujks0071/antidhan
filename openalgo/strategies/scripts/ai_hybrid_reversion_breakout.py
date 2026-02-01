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
    from trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol
except ImportError:
    try:
        # Try absolute import
        sys.path.insert(0, strategies_dir)
        from utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol
    except ImportError:
        try:
            from openalgo.strategies.utils.trading_utils import APIClient, PositionManager, is_market_open, normalize_symbol
        except ImportError:
            print("Warning: openalgo package not found or imports failed.")
            APIClient = None
            PositionManager = None
            normalize_symbol = lambda s: s
            is_market_open = lambda: True

class AIHybridStrategy:
    def __init__(self, symbol, api_key, port, rsi_lower=30, rsi_upper=60, stop_pct=1.0, sector='NIFTY 50', earnings_date=None, logfile=None, time_stop_bars=12):
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
        self.time_stop_bars = time_stop_bars

    def calculate_signal(self, df):
        """Calculate signal for a given dataframe (Backtesting support)."""
        if df.empty or len(df) < 20:
            return 'HOLD', 0.0, {}

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

        # Regime Filter (SMA200)
        df['sma200'] = df['close'].rolling(200).mean()

        last = df.iloc[-1]

        # Volatility Sizing (Target Risk)
        # Robust Sizing: Risk 1% of Capital (1000) per trade
        # Stop Loss distance is roughly 2 * ATR
        # Risk = Qty * 2 * ATR  => Qty = Risk / (2 * ATR)

        atr = df['high'].diff().abs().rolling(14).mean().iloc[-1] # Simple ATR approx

        risk_amount = 1000.0 # 1% of 100k

        if atr > 0:
            qty = int(risk_amount / (2.0 * atr))
            qty = max(1, min(qty, 500)) # Cap to reasonable limits
        else:
            qty = 50 # Safe default

        # Note: External filters (Sector, Earnings, Breadth) are skipped in simple backtest
        # unless mocked via client or params. Here we focus on price action.

        # Check Regime
        is_bullish_regime = True
        if not pd.isna(last.get('sma200')) and last['close'] < last['sma200']:
            is_bullish_regime = False

        # Reversion Logic: RSI < 30 and Price < Lower BB (Oversold)
        if last['rsi'] < self.rsi_lower and last['close'] < last['lower']:
            avg_vol = df['volume'].rolling(20).mean().iloc[-1]
            # Enhanced Volume Confirmation (Stricter than average)
            if last['volume'] > avg_vol * 1.2:
                # Reversion can trade against trend, so maybe ignore regime or be strict?
                # Let's say Reversion is allowed in any regime if oversold enough.
                return 'BUY', 1.0, {'type': 'REVERSION', 'rsi': last['rsi'], 'close': last['close'], 'quantity': qty}

        # Breakout Logic: RSI > 60 and Price > Upper BB
        elif last['rsi'] > self.rsi_upper and last['close'] > last['upper']:
            avg_vol = df['volume'].rolling(20).mean().iloc[-1]
            # Breakout needs significant volume (2x avg)
            # Breakout ONLY in Bullish Regime
            if last['volume'] > avg_vol * 2.0 and is_bullish_regime:
                 return 'BUY', 1.0, {'type': 'BREAKOUT', 'rsi': last['rsi'], 'close': last['close'], 'quantity': qty}

        return 'HOLD', 0.0, {}

    def get_market_context(self):
        # Fetch VIX
        vix = 15.0
        try:
            vix_df = self.client.history("INDIA VIX", exchange="NSE_INDEX", interval="day",
                                       start_date=(datetime.now()-timedelta(days=5)).strftime("%Y-%m-%d"),
                                       end_date=datetime.now().strftime("%Y-%m-%d"))
            if not vix_df.empty:
                vix = vix_df['close'].iloc[-1]
        except Exception as e:
            self.logger.warning(f"VIX fetch failed: {e}")

        # Fetch Breadth (Placeholder for now, usually requires full market scan or index internals)
        # We can use NIFTY Trend as a proxy for breadth health
        breadth = 1.2
        try:
            nifty = self.client.history("NIFTY 50", exchange="NSE_INDEX", interval="day",
                                      start_date=(datetime.now()-timedelta(days=5)).strftime("%Y-%m-%d"),
                                      end_date=datetime.now().strftime("%Y-%m-%d"))
            if not nifty.empty and nifty['close'].iloc[-1] > nifty['open'].iloc[-1]:
                breadth = 1.5 # Bullish proxy
            elif not nifty.empty:
                breadth = 0.8 # Bearish proxy
        except:
            pass

        return {
            'vix': vix,
            'breadth_ad_ratio': breadth
        }

    def check_earnings(self):
        """Check if earnings are near (within 2 days)."""
        if not self.earnings_date:
            return False

        try:
            e_date = None
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
                try:
                    e_date = datetime.strptime(self.earnings_date, fmt)
                    break
                except ValueError:
                    continue

            if not e_date:
                self.logger.warning(f"Invalid earnings date format: {self.earnings_date}")
                return False

            days_diff = (e_date - datetime.now()).days
            if 0 <= days_diff <= 2:
                return True
        except Exception as e:
            self.logger.warning(f"Error checking earnings: {e}")
        return False

    def check_sector_strength(self):
        try:
            sector_symbol = normalize_symbol(self.sector)
            
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
        self.symbol = normalize_symbol(self.symbol)
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
                    # Enhanced Volume Confirmation (Stricter than average)
                    if last['volume'] > avg_vol * 1.2:
                        qty = int(100 * size_multiplier)
                        self.logger.info("Oversold Reversion Signal (RSI<30, <LowerBB, Vol>1.2x). BUY.")
                        self.pm.update_position(qty, current_price, 'BUY')

                # Breakout Logic: RSI > 60 and Price > Upper BB
                elif last['rsi'] > self.rsi_upper and last['close'] > last['upper']:
                    avg_vol = df['volume'].rolling(20).mean().iloc[-1]
                    # Breakout needs significant volume (2x avg)
                    if last['volume'] > avg_vol * 2.0:
                         qty = int(100 * size_multiplier)
                         self.logger.info("Breakout Signal (RSI>60, >UpperBB, Vol>2x). BUY.")
                         self.pm.update_position(qty, current_price, 'BUY')

            except Exception as e:
                self.logger.error(f"Error in AI Hybrid strategy for {self.symbol}: {e}", exc_info=True)
                time.sleep(60)

            time.sleep(60)

def run_strategy():
    parser = argparse.ArgumentParser(description='AI Hybrid Strategy')
    parser.add_argument('--symbol', type=str, required=True, help='Stock Symbol')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key (or set OPENALGO_APIKEY env var)')
    parser.add_argument('--rsi_lower', type=float, default=30.0, help='RSI Lower Threshold')
    parser.add_argument('--sector', type=str, default='NIFTY 50', help='Sector Benchmark')
    parser.add_argument('--earnings_date', type=str, help='Earnings Date YYYY-MM-DD')
    parser.add_argument("--logfile", type=str, help="Log file path")

    args = parser.parse_args()

    # Support env var fallback for API key
    api_key = args.api_key or os.getenv('OPENALGO_APIKEY')
    if not api_key:
        print("Error: API Key required via --api_key or OPENALGO_APIKEY")
        return

    # Default logfile if not provided
    logfile = args.logfile
    if not logfile:
        log_dir = os.path.join(strategies_dir, "..", "log", "strategies")
        os.makedirs(log_dir, exist_ok=True)
        logfile = os.path.join(log_dir, f"{args.symbol}_ai_hybrid.log")

    strategy = AIHybridStrategy(
        args.symbol,
        api_key,
        args.port,
        rsi_lower=args.rsi_lower,
        sector=args.sector,
        earnings_date=args.earnings_date,
        logfile=logfile
    )
    strategy.run()

# Module level wrapper for SimpleBacktestEngine
def generate_signal(df, client=None, symbol=None, params=None):
    strat_params = {
        'rsi_lower': 30.0,
        'rsi_upper': 60.0,
        'stop_pct': 1.0,
        'sector': 'NIFTY 50'
    }
    if params:
        strat_params.update(params)

    strat = AIHybridStrategy(
        symbol=symbol or "TEST",
        api_key="dummy",
        port=5001,
        rsi_lower=float(strat_params.get('rsi_lower', 30.0)),
        rsi_upper=float(strat_params.get('rsi_upper', 60.0)),
        stop_pct=float(strat_params.get('stop_pct', 1.0)),
        sector=strat_params.get('sector', 'NIFTY 50')
    )

    # Silence logger for backtest
    strat.logger.handlers = []
    strat.logger.addHandler(logging.NullHandler())

    # Set Time Stop (if using attribute injection for engine)
    # The class sets it in __init__ but engine might look for it on instance or module?
    # SimpleBacktestEngine checks: if strategy_module and hasattr(strategy_module, 'TIME_STOP_BARS')
    # It checks the MODULE (passed as strategy_module).
    # Wait, SimpleBacktestEngine receives `strategy_module` which is the python module.
    # So `TIME_STOP_BARS` must be module-level attribute?
    # The wrapper generates the signal.
    # The engine loop:
    # check_exits(..., strategy_module)
    # def check_exits(..., strategy_module=None):
    #    if strategy_module and hasattr(strategy_module, 'TIME_STOP_BARS'):

    # So I need to set module level attribute dynamically? That's bad for concurrency.
    # But for this simple engine, it's fine.
    # Or better, I set it on the module object that 'run_leaderboard' loaded.

    # However, 'generate_signal' is just a function.
    # I can't easily change the module level attribute from here for the *current* backtest
    # unless I know which module object is being used.
    # But since params change, the Time Stop might change.

    # For now, I will set it on the function object? No.
    # I will assume fixed Time Stop for now or set it globally in module.

    # Let's set it globally for this run.
    global TIME_STOP_BARS
    TIME_STOP_BARS = getattr(strat, 'time_stop_bars', 12)

    return strat.calculate_signal(df)

# Global default for engine check
TIME_STOP_BARS = 12

if __name__ == "__main__":
    run_strategy()
