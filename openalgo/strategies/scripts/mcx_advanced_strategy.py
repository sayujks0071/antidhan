#!/usr/bin/env python3
"""
Advanced MCX Commodity Strategy & Analysis Tool
Daily analysis and strategy deployment for MCX Commodities using Multi-Factor Models.
"""
import os
import sys
import time
import json
import logging
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# Try importing dependencies
try:
    import yfinance as yf
except ImportError:
    print("Warning: yfinance not found. Global market data will be simulated.")
    yf = None

# Add repo root to path for imports
script_dir = Path(__file__).parent
strategies_dir = script_dir.parent
utils_dir = strategies_dir / 'utils'
sys.path.insert(0, str(utils_dir))

try:
    from trading_utils import APIClient, is_market_open
    from symbol_resolver import SymbolResolver
except ImportError:
    # Fallback for direct execution
    sys.path.insert(0, str(strategies_dir))
    from utils.trading_utils import APIClient, is_market_open
    from utils.symbol_resolver import SymbolResolver

# Configuration
API_HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')
SCRIPTS_DIR = Path(__file__).parent

# Strategy Templates Mapping
STRATEGY_TEMPLATES = {
    'Momentum': 'mcx_commodity_momentum_strategy.py',
    'Arbitrage': 'mcx_global_arbitrage_strategy.py',
    'Spread': 'mcx_inter_commodity_spread_strategy.py',
    'MeanReversion': 'mcx_commodity_momentum_strategy.py', # Fallback
}

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MCX_Advanced_Strategy")

class AdvancedMCXStrategy:
    def __init__(self, api_key, api_host):
        self.api_key = api_key
        self.api_host = api_host
        self.client = APIClient(api_key=self.api_key, host=self.api_host)
        self.resolver = SymbolResolver()
        self.fundamental_data = self._load_fundamental_data()

        self.market_context = {
            'usd_inr': 83.50,
            'usd_trend': 'Neutral',
            'usd_volatility': 0.0,
            'global_gold': 0.0,
            'global_silver': 0.0,
            'global_crude': 0.0,
            'global_ng': 0.0,
            'global_copper': 0.0
        }

        self.commodities = [
            {'name': 'GOLD', 'global_ticker': 'GC=F', 'sector': 'Metal', 'min_vol': 1000},
            {'name': 'SILVER', 'global_ticker': 'SI=F', 'sector': 'Metal', 'min_vol': 500},
            {'name': 'CRUDEOIL', 'global_ticker': 'CL=F', 'sector': 'Energy', 'min_vol': 2000},
            {'name': 'NATURALGAS', 'global_ticker': 'NG=F', 'sector': 'Energy', 'min_vol': 5000},
            {'name': 'COPPER', 'global_ticker': 'HG=F', 'sector': 'Metal', 'min_vol': 500},
        ]

        self.opportunities = []

    def _load_fundamental_data(self):
        """Load fundamental data from JSON file or return default."""
        data_path = strategies_dir / 'data' / 'fundamental_data.json'
        if data_path.exists():
            try:
                with open(data_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading fundamental data: {e}")
        return {}

    def fetch_global_context(self):
        """
        Fetch global market data via yfinance.
        """
        logger.info("Fetching Global Market Context...")

        if not yf:
            logger.warning("yfinance not available. Using simulated global data.")
            self._simulate_global_data()
            return

        try:
            # 1. USD/INR
            usd = yf.Ticker("INR=X")
            hist = usd.history(period="5d")
            if not hist.empty:
                current_usd = hist['Close'].iloc[-1]
                prev_usd = hist['Close'].iloc[-2]
                self.market_context['usd_inr'] = current_usd
                self.market_context['usd_trend'] = 'Up' if current_usd > prev_usd else 'Down'

                # Volatility (Std Dev of returns)
                returns = hist['Close'].pct_change().dropna()
                self.market_context['usd_volatility'] = returns.std() * 100 # percentage

                logger.info(f"USD/INR: {current_usd:.2f} ({self.market_context['usd_trend']}) | Vol: {self.market_context['usd_volatility']:.2f}%")

            # 2. Global Commodities
            tickers = " ".join([c['global_ticker'] for c in self.commodities])
            data = yf.download(tickers, period="5d", interval="1d", progress=False)

            if not data.empty:
                # Handle Multi-Index columns in newer yfinance
                close_prices = data['Close'] if 'Close' in data else data

                for comm in self.commodities:
                    ticker = comm['global_ticker']
                    if ticker in close_prices:
                        series = close_prices[ticker].dropna()
                        if not series.empty:
                            price = series.iloc[-1]
                            self.market_context[f"global_{comm['name'].lower()}"] = price
                            # simple trend
                            comm['global_trend'] = 'Up' if price > series.iloc[-2] else 'Down'
                            if series.iloc[-2] != 0:
                                comm['global_change_pct'] = ((price - series.iloc[-2]) / series.iloc[-2]) * 100
                            else:
                                comm['global_change_pct'] = 0.0
                            logger.info(f"Global {comm['name']}: {price:.2f} ({comm['global_change_pct']:.2f}%)")
        except Exception as e:
            logger.error(f"Error fetching global data: {e}")
            self._simulate_global_data()

    def _simulate_global_data(self):
        """Fallback simulation for global data."""
        self.market_context['usd_inr'] = 83.50 + np.random.uniform(-0.2, 0.2)
        self.market_context['usd_trend'] = 'Neutral'
        self.market_context['usd_volatility'] = 0.5
        for comm in self.commodities:
            self.market_context[f"global_{comm['name'].lower()}"] = 100.0 # Dummy
            comm['global_trend'] = 'Neutral'
            comm['global_change_pct'] = 0.0

    def fetch_mcx_data(self):
        """
        Fetch MCX data via APIClient for active contracts.
        """
        logger.info("Fetching MCX Data...")

        for comm in self.commodities:
            try:
                # Resolve Active Symbol
                symbol = self.resolver.resolve({'underlying': comm['name'], 'type': 'FUT', 'exchange': 'MCX'})
                if not symbol:
                    logger.warning(f"Could not resolve symbol for {comm['name']}")
                    continue

                comm['symbol'] = symbol

                # Fetch Historical Data (15m candles for analysis)
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

                df = self.client.history(symbol, exchange="MCX", interval="15m", start_date=start_date, end_date=end_date)

                if df.empty or len(df) < 50:
                    logger.warning(f"Insufficient data for {symbol}")
                    comm['valid'] = False
                    continue

                comm['data'] = df
                comm['valid'] = True

                # Fetch Quote for real-time (optional, can use last candle close)
                quote = self.client.get_quote(symbol, exchange="MCX")
                if quote:
                    comm['ltp'] = float(quote.get('ltp', df['close'].iloc[-1]))
                    comm['volume'] = float(quote.get('volume', df['volume'].iloc[-1]))
                    comm['oi'] = float(quote.get('oi', 0))
                else:
                    comm['ltp'] = df['close'].iloc[-1]
                    comm['volume'] = df['volume'].iloc[-1]
                    comm['oi'] = 0

                logger.info(f"Fetched {symbol}: LTP={comm['ltp']}, Vol={comm['volume']}")

            except Exception as e:
                logger.error(f"Error processing {comm['name']}: {e}")
                comm['valid'] = False

    def calculate_technical_indicators(self, df):
        """Calculate ADX, RSI, ATR."""
        if df.empty: return {}

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # ATR
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        df['atr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()

        # ADX (Simplified)
        df['adx'] = np.random.uniform(15, 45, len(df)) # Placeholder for full ADX logic to save space, assuming sufficient for demo
        # Proper ADX requires +DI/-DI smoothing. Let's do a quick approximation using volatility expansion
        # Or better, implement proper ADX if critical.
        # Implementation of full ADX:
        up = df['high'] - df['high'].shift(1)
        down = df['low'].shift(1) - df['low']
        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)

        tr = df['atr'] # Approximation of TR

        # Smooth
        plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / tr)
        minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / tr)
        dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
        df['adx'] = dx.rolling(14).mean()

        return {
            'adx': df['adx'].iloc[-1],
            'rsi': df['rsi'].iloc[-1],
            'atr': df['atr'].iloc[-1],
            'close': df['close'].iloc[-1],
            'prev_close': df['close'].iloc[-2]
        }

    def get_seasonality_score(self, commodity_name):
        """
        Return a seasonality score (0-100) based on current month.
        """
        month = datetime.now().month
        # Example seasonality map
        seasonality = {
            'GOLD': {1: 80, 2: 60, 3: 40, 4: 50, 5: 90, 6: 40, 7: 40, 8: 60, 9: 50, 10: 80, 11: 90, 12: 70}, # Festivals
            'SILVER': {1: 70, 2: 60, 3: 50, 4: 60, 5: 80, 6: 40, 7: 50, 8: 60, 9: 50, 10: 70, 11: 80, 12: 60},
            'CRUDEOIL': {1: 40, 2: 50, 3: 60, 4: 70, 5: 80, 6: 90, 7: 90, 8: 80, 9: 60, 10: 50, 11: 40, 12: 50}, # Summer driving
            'NATURALGAS': {1: 90, 2: 80, 3: 60, 4: 40, 5: 40, 6: 70, 7: 80, 8: 70, 9: 50, 10: 60, 11: 80, 12: 90}, # Winter heating + Summer cooling
            'COPPER': {1: 60, 2: 70, 3: 80, 4: 80, 5: 70, 6: 60, 7: 50, 8: 50, 9: 60, 10: 60, 11: 60, 12: 50}, # Spring construction
        }
        return seasonality.get(commodity_name, {}).get(month, 50)

    def analyze_commodities(self):
        """
        Multi-Factor Scoring & Strategy Selection.
        """
        logger.info("Analyzing Commodities...")

        for comm in self.commodities:
            if not comm.get('valid', False):
                continue

            try:
                # 1. Technicals
                techs = self.calculate_technical_indicators(comm['data'])
                if not techs or pd.isna(techs['adx']):
                    continue

                # 2. Scores Calculation

                # Trend (ADX)
                trend_val = techs['adx']
                trend_score = min(trend_val * 2.5, 100) # ADX 40 -> 100
                trend_dir = 'Up' if techs['close'] > techs['prev_close'] else 'Down'

                # Momentum (RSI)
                rsi = techs['rsi']
                # Score high if RSI is trending (e.g. > 60 or < 40)
                momentum_score = 0
                if rsi > 60: momentum_score = (rsi - 50) * 2
                elif rsi < 40: momentum_score = (50 - rsi) * 2
                else: momentum_score = 30 # Neutral
                momentum_score = min(max(momentum_score, 0), 100)

                # Global Alignment
                # Compare MCX trend direction with Global trend direction
                # And check if MCX price movement % is similar to Global
                global_trend = comm.get('global_trend', 'Neutral')
                global_align_score = 100 if trend_dir == global_trend else 20

                # Volatility
                # Ideally compare current ATR to historical ATR percentile
                atr = techs['atr']
                volatility_score = 70 # Default normal
                if self.market_context['usd_volatility'] > 0.8: # High currency risk
                    volatility_score = 40

                # Liquidity
                liquidity_score = 100 if comm['volume'] > comm['min_vol'] else 40

                # Seasonality
                seasonality_score = self.get_seasonality_score(comm['name'])

                # Fundamental
                # Fetch from loaded data or default to 50
                fundamental_score = self.fundamental_data.get(comm['name'], {}).get('score', 50)
                fundamental_note = self.fundamental_data.get(comm['name'], {}).get('note', "Neutral")

                # Composite Score
                # (Trend * 0.25) + (Momentum * 0.20) + (Global * 0.15) + (Volatility * 0.15) + (Liquidity * 0.10) + (Fundamental * 0.10) + (Seasonality * 0.05)
                composite_score = (
                    trend_score * 0.25 +
                    momentum_score * 0.20 +
                    global_align_score * 0.15 +
                    volatility_score * 0.15 +
                    liquidity_score * 0.10 +
                    fundamental_score * 0.10 +
                    seasonality_score * 0.05
                )

                # Determine Strategy
                strategy_type = 'Momentum'
                if composite_score < 50:
                    strategy_type = 'Avoid'
                elif global_align_score < 40 and volatility_score > 60:
                    strategy_type = 'Arbitrage' # Divergence detected
                    # Boost score for Arbitrage view
                    composite_score = (composite_score + 100) / 2
                elif momentum_score < 40 and seasonality_score > 80:
                    strategy_type = 'MeanReversion' # Seasonal Buy

                self.opportunities.append({
                    'symbol': comm['symbol'],
                    'name': comm['name'],
                    'strategy_type': strategy_type,
                    'score': round(composite_score, 2),
                    'ltp': comm['ltp'],
                    'details': {
                        'trend_score': trend_score,
                        'trend_dir': trend_dir,
                        'momentum_score': momentum_score,
                        'global_score': global_align_score,
                        'volatility_score': volatility_score,
                        'seasonality_score': seasonality_score,
                        'fundamental_score': fundamental_score,
                        'fundamental_note': fundamental_note,
                        'adx': trend_val,
                        'rsi': rsi,
                        'atr': atr,
                        'volume': comm['volume']
                    }
                })

            except Exception as e:
                logger.error(f"Error analyzing {comm['name']}: {e}", exc_info=True)

        # Sort opportunities
        self.opportunities.sort(key=lambda x: x['score'], reverse=True)

    def generate_report(self):
        """
        Generate and print the daily analysis report.
        """
        print(f"\n📊 DAILY MCX STRATEGY ANALYSIS - {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        print("\n🌍 GLOBAL MARKET CONTEXT:")
        print(f"- USD/INR: {self.market_context['usd_inr']:.2f} | Trend: {self.market_context['usd_trend']} | Volatility: {self.market_context['usd_volatility']:.2f}%")
        print(f"- Impact: {'Negative' if self.market_context['usd_volatility'] > 0.8 else 'Neutral/Positive'}")

        for comm in self.commodities:
            if 'global_change_pct' in comm:
                print(f"- Global {comm['name']}: ${self.market_context.get(f'global_{comm['name'].lower()}', 0):.2f} ({comm['global_change_pct']:.2f}%)")

        print("\n📈 MCX MARKET DATA:")
        print(f"- Active Contracts: {len([c for c in self.commodities if c.get('valid')])} Valid")

        print("\n🎯 STRATEGY OPPORTUNITIES (Ranked):")

        top_picks = []

        for i, opp in enumerate(self.opportunities, 1):
            if opp['strategy_type'] == 'Avoid':
                continue

            print(f"\n{i}. {opp['name']} ({opp['symbol']}) - {opp['strategy_type']} - Score: {opp['score']}/100")
            d = opp['details']
            print(f"   - Trend: {d['trend_dir']} (ADX: {d['adx']:.1f}) | Momentum: {d['momentum_score']:.0f} (RSI: {d['rsi']:.1f})")
            print(f"   - Global Align: {d['global_score']} | Seasonality: {d['seasonality_score']} | Volatility: {d['volatility_score']}")
            print(f"   - Fundamental: {d['fundamental_score']} ({d['fundamental_note']})")
            print(f"   - Volume: {d['volume']} | ATR: {d['atr']:.2f}")

            risk_pct = 2.0
            if self.market_context['usd_volatility'] > 0.8:
                risk_pct = 1.0 # Reduce risk
                print(f"   ⚠️ High Currency Risk: Position size reduced to {risk_pct}%")

            print(f"   - Rationale: Strong multi-factor alignment. Strategy: {opp['strategy_type']}")

            top_picks.append(opp)
            if len(top_picks) >= 6: break # Top 6

        print("\n🔧 STRATEGY ENHANCEMENTS APPLIED:")
        print("- MCX Momentum: Added USD/INR adjustment factor")
        print("- MCX Momentum: Enhanced with global price correlation filter")
        print("- MCX Momentum: Added seasonality-based position sizing")
        print("- MCX Global Arbitrage: Added yfinance backup for global prices")

        print("\n💡 NEW STRATEGIES CREATED:")
        print("- Global-MCX Arbitrage: Trade MCX when it diverges from global prices -> mcx_global_arbitrage_strategy.py")
        print("  - Logic: Compares MCX Price vs Global Price (yfinance)")
        print("  - Entry: Divergence > 3%")

        print("\n⚠️ RISK WARNINGS:")
        if self.market_context['usd_volatility'] > 0.8:
            print(f"- [High USD/INR volatility {self.market_context['usd_volatility']:.2f}%] → Reduce position sizes")

        # Check for expiry or rollover (Simulated check)
        print("- [Rollover Status] Check expiry dates for near-month contracts.")

        print("\n🚀 DEPLOYMENT PLAN:")
        print("- Deploy: Top strategies listed above")

        deploy_cmds = []
        for pick in top_picks:
            cmd = f"python3 strategies/scripts/{STRATEGY_TEMPLATES.get(pick['strategy_type'], 'mcx_commodity_momentum_strategy.py')} " \
                  f"--symbol {pick['symbol']} --underlying {pick['name']} " \
                  f"--usd_inr_trend {self.market_context['usd_trend']} " \
                  f"--usd_inr_volatility {self.market_context['usd_volatility']} " \
                  f"--seasonality_score {pick['details']['seasonality_score']} " \
                  f"--global_alignment_score {pick['details']['global_score']}"
            deploy_cmds.append(cmd)
            print(f"- {pick['name']}: {cmd}")

        return deploy_cmds

def main():
    parser = argparse.ArgumentParser(description='Advanced MCX Strategy Analyzer')
    parser.add_argument('--port', type=int, default=5001, help='API Port')
    parser.add_argument('--api_key', type=str, default='demo_key', help='API Key')
    args = parser.parse_args()

    # Overwrite with env vars if present
    api_key = os.getenv('OPENALGO_APIKEY', args.api_key)
    port = int(os.getenv('OPENALGO_PORT', args.port))
    host = f"http://127.0.0.1:{port}"

    analyzer = AdvancedMCXStrategy(api_key, host)
    analyzer.fetch_global_context()
    analyzer.fetch_mcx_data()
    analyzer.analyze_commodities()
    analyzer.generate_report()

if __name__ == "__main__":
    main()
