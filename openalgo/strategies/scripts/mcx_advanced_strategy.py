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
from strategy_preamble import BaseStrategy
from symbol_resolver import SymbolResolver

try:
    import yfinance as yf
except ImportError:
    print("Warning: yfinance not found. Global market data will be simulated.")
    yf = None

logger = logging.getLogger("MCX_Advanced_Strategy")

STRATEGY_TEMPLATES = {
    'Momentum': 'mcx_commodity_momentum_strategy.py',
    'Arbitrage': 'mcx_global_arbitrage_strategy.py',
    'Spread': 'mcx_inter_commodity_spread_strategy.py',
    'MeanReversion': 'mcx_commodity_momentum_strategy.py',
}

class AdvancedMCXStrategy(BaseStrategy):
    def setup(self):
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
        self.resolver = SymbolResolver()

    def _load_fundamental_data(self):
        data_path = Path(__file__).parent.parent / 'data' / 'fundamental_data.json'
        if data_path.exists():
            try:
                with open(data_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading fundamental data: {e}")
        return {}

    def fetch_global_context(self):
        logger.info("Fetching Global Market Context...")

        if not yf:
            logger.warning("yfinance not available. Using simulated global data.")
            self._simulate_global_data()
            return

        try:
            usd = yf.Ticker("INR=X")
            hist = usd.history(period="5d")
            if not hist.empty:
                current_usd = hist['Close'].iloc[-1]
                prev_usd = hist['Close'].iloc[-2]
                self.market_context['usd_inr'] = current_usd
                self.market_context['usd_trend'] = 'Up' if current_usd > prev_usd else 'Down'

                returns = hist['Close'].pct_change().dropna()
                self.market_context['usd_volatility'] = returns.std() * 100
                logger.info(f"USD/INR: {current_usd:.2f} ({self.market_context['usd_trend']}) | Vol: {self.market_context['usd_volatility']:.2f}%")

            tickers = " ".join([c['global_ticker'] for c in self.commodities])
            data = yf.download(tickers, period="5d", interval="1d", progress=False)

            if not data.empty:
                close_prices = data['Close'] if 'Close' in data else data
                for comm in self.commodities:
                    ticker = comm['global_ticker']
                    if ticker in close_prices:
                        series = close_prices[ticker].dropna()
                        if not series.empty:
                            price = series.iloc[-1]
                            self.market_context[f"global_{comm['name'].lower()}"] = price
                            comm['global_trend'] = 'Up' if price > series.iloc[-2] else 'Down'
                            comm['global_change_pct'] = ((price - series.iloc[-2]) / series.iloc[-2]) * 100 if series.iloc[-2] != 0 else 0.0
                            logger.info(f"Global {comm['name']}: {price:.2f} ({comm['global_change_pct']:.2f}%)")
        except Exception as e:
            logger.error(f"Error fetching global data: {e}")
            self._simulate_global_data()

    def _simulate_global_data(self):
        self.market_context['usd_inr'] = 83.50 + np.random.uniform(-0.2, 0.2)
        self.market_context['usd_trend'] = 'Neutral'
        self.market_context['usd_volatility'] = 0.5
        for comm in self.commodities:
            self.market_context[f"global_{comm['name'].lower()}"] = 100.0
            comm['global_trend'] = 'Neutral'
            comm['global_change_pct'] = 0.0

    def fetch_mcx_data(self):
        if not self.client:
             logger.error("No API Client initialized.")
             return

        logger.info("Fetching MCX Data...")
        for comm in self.commodities:
            try:
                symbol = self.resolver.resolve({'underlying': comm['name'], 'type': 'FUT', 'exchange': 'MCX'})
                if not symbol: continue

                comm['symbol'] = symbol
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

                df = self.client.history(symbol, exchange="MCX", interval="15m", start_date=start_date, end_date=end_date)
                if df.empty or len(df) < 50:
                    comm['valid'] = False
                    continue

                comm['data'] = df
                comm['valid'] = True

                quote = self.client.get_quote(symbol, exchange="MCX")
                if quote:
                    comm['ltp'] = float(quote.get('ltp', df['close'].iloc[-1]))
                    comm['volume'] = float(quote.get('volume', df['volume'].iloc[-1]))
                else:
                    comm['ltp'] = df['close'].iloc[-1]
                    comm['volume'] = df['volume'].iloc[-1]

                logger.info(f"Fetched {symbol}: LTP={comm['ltp']}, Vol={comm['volume']}")
            except Exception as e:
                logger.error(f"Error processing {comm['name']}: {e}")
                comm['valid'] = False

    def get_seasonality_score(self, commodity_name):
        month = datetime.now().month
        seasonality = {
            'GOLD': {1: 80, 2: 60, 3: 40, 4: 50, 5: 90, 6: 40, 7: 40, 8: 60, 9: 50, 10: 80, 11: 90, 12: 70},
            'SILVER': {1: 70, 2: 60, 3: 50, 4: 60, 5: 80, 6: 40, 7: 50, 8: 60, 9: 50, 10: 70, 11: 80, 12: 60},
            'CRUDEOIL': {1: 40, 2: 50, 3: 60, 4: 70, 5: 80, 6: 90, 7: 90, 8: 80, 9: 60, 10: 50, 11: 40, 12: 50},
            'NATURALGAS': {1: 90, 2: 80, 3: 60, 4: 40, 5: 40, 6: 70, 7: 80, 8: 70, 9: 50, 10: 60, 11: 80, 12: 90},
            'COPPER': {1: 60, 2: 70, 3: 80, 4: 80, 5: 70, 6: 60, 7: 50, 8: 50, 9: 60, 10: 60, 11: 60, 12: 50},
        }
        return seasonality.get(commodity_name, {}).get(month, 50)

    def analyze_commodities(self):
        logger.info("Analyzing Commodities...")
        for comm in self.commodities:
            if not comm.get('valid', False): continue

            try:
                df = comm['data'].copy()
                df['rsi'] = self.calculate_rsi(df['close'])
                df['atr'] = self.calculate_atr_series(df)
                df['adx'] = self.calculate_adx_series(df)

                techs = {
                    'adx': df['adx'].iloc[-1],
                    'rsi': df['rsi'].iloc[-1],
                    'atr': df['atr'].iloc[-1],
                    'close': df['close'].iloc[-1],
                    'prev_close': df['close'].iloc[-2]
                }

                if pd.isna(techs['adx']): continue

                trend_val = techs['adx']
                trend_score = min(trend_val * 2.5, 100)
                trend_dir = 'Up' if techs['close'] > techs['prev_close'] else 'Down'

                rsi = techs['rsi']
                momentum_score = 0
                if rsi > 60: momentum_score = (rsi - 50) * 2
                elif rsi < 40: momentum_score = (50 - rsi) * 2
                else: momentum_score = 30
                momentum_score = min(max(momentum_score, 0), 100)

                global_trend = comm.get('global_trend', 'Neutral')
                global_align_score = 100 if trend_dir == global_trend else 20

                atr = techs['atr']
                volatility_score = 70
                if self.market_context['usd_volatility'] > 0.8: volatility_score = 40

                liquidity_score = 100 if comm['volume'] > comm['min_vol'] else 40
                seasonality_score = self.get_seasonality_score(comm['name'])
                fundamental_score = self.fundamental_data.get(comm['name'], {}).get('score', 50)
                fundamental_note = self.fundamental_data.get(comm['name'], {}).get('note', "Neutral")

                composite_score = (
                    trend_score * 0.25 + momentum_score * 0.20 + global_align_score * 0.15 +
                    volatility_score * 0.15 + liquidity_score * 0.10 + fundamental_score * 0.10 + seasonality_score * 0.05
                )

                strategy_type = 'Momentum'
                if composite_score < 50: strategy_type = 'Avoid'
                elif global_align_score < 40 and volatility_score > 60:
                    strategy_type = 'Arbitrage'
                    composite_score = (composite_score + 100) / 2
                elif momentum_score < 40 and seasonality_score > 80:
                    strategy_type = 'MeanReversion'

                self.opportunities.append({
                    'symbol': comm['symbol'],
                    'name': comm['name'],
                    'strategy_type': strategy_type,
                    'score': round(composite_score, 2),
                    'ltp': comm['ltp'],
                    'details': {
                        'trend_score': trend_score, 'trend_dir': trend_dir, 'momentum_score': momentum_score,
                        'global_score': global_align_score, 'volatility_score': volatility_score,
                        'seasonality_score': seasonality_score, 'fundamental_score': fundamental_score,
                        'fundamental_note': fundamental_note, 'adx': trend_val, 'rsi': rsi, 'atr': atr, 'volume': comm['volume']
                    }
                })
            except Exception as e:
                logger.error(f"Error analyzing {comm['name']}: {e}", exc_info=True)
        self.opportunities.sort(key=lambda x: x['score'], reverse=True)

    def generate_report(self):
        print(f"\n📊 DAILY MCX STRATEGY ANALYSIS - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("\n🌍 GLOBAL MARKET CONTEXT:")
        print(f"- USD/INR: {self.market_context['usd_inr']:.2f} | Trend: {self.market_context['usd_trend']} | Volatility: {self.market_context['usd_volatility']:.2f}%")

        for comm in self.commodities:
            if 'global_change_pct' in comm:
                print(f"- Global {comm['name']}: ${self.market_context.get(f'global_{comm['name'].lower()}', 0):.2f} ({comm['global_change_pct']:.2f}%)")

        print("\n📈 MCX MARKET DATA:")
        print(f"- Active Contracts: {len([c for c in self.commodities if c.get('valid')])} Valid")

        print("\n🎯 STRATEGY OPPORTUNITIES (Ranked):")
        top_picks = []

        for i, opp in enumerate(self.opportunities, 1):
            if opp['strategy_type'] == 'Avoid': continue
            print(f"\n{i}. {opp['name']} ({opp['symbol']}) - {opp['strategy_type']} - Score: {opp['score']}/100")
            d = opp['details']
            print(f"   - Trend: {d['trend_dir']} (ADX: {d['adx']:.1f}) | Momentum: {d['momentum_score']:.0f} (RSI: {d['rsi']:.1f})")
            top_picks.append(opp)
            if len(top_picks) >= 6: break

        print("\n🚀 DEPLOYMENT PLAN:")
        deploy_cmds = []
        for pick in top_picks:
            cmd = f"python3 strategies/scripts/{STRATEGY_TEMPLATES.get(pick['strategy_type'], 'mcx_commodity_momentum_strategy.py')} --symbol {pick['symbol']} --underlying {pick['name']}"
            deploy_cmds.append(cmd)
            print(f"- {pick['name']}: {cmd}")

        return deploy_cmds

if __name__ == "__main__":
    analyzer = AdvancedMCXStrategy(symbol="TEST")
    analyzer.fetch_global_context()
    analyzer.fetch_mcx_data()
    analyzer.analyze_commodities()
    analyzer.generate_report()
