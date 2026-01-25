#!/usr/bin/env python3
"""
Daily Options Strategy Analysis & Ranker
Enhances and creates options strategies for NIFTY, SENSEX, and BANKNIFTY using multi-factor analysis.
"""
import os
import sys
import requests
import logging
from datetime import datetime, timedelta

# Configuration
API_HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5002')  # Dhan API on 5002
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'options_ranker.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("AdvancedOptionsRanker")

class AdvancedOptionsRanker:
    def __init__(self, host=API_HOST, api_key=API_KEY):
        self.host = host
        self.api_key = api_key
        self.market_data = {}
        self.strategies = []

    def _post(self, endpoint, payload):
        """Helper to make POST requests to OpenAlgo API"""
        url = f"{self.host}{endpoint}"
        try:
            # Add API key to payload if not present
            if 'apikey' not in payload:
                payload['apikey'] = self.api_key

            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"API request failed for {endpoint}: {e}")
            return None

    def fetch_market_data(self):
        """Fetch all necessary market data"""
        logger.info("Fetching market data...")

        # 1. Fetch Options Chains for Indices
        indices = ['NIFTY', 'BANKNIFTY', 'SENSEX']
        self.market_data['chains'] = {}

        for index in indices:
            logger.info(f"Fetching option chain for {index}")
            # Mocking parameters for now - in real scenario, determine next expiry
            next_expiry = (datetime.now() + timedelta(days=5)).strftime("%d%b%y").upper()

            payload = {
                "underlying": index,
                "exchange": "NSE_INDEX" if index != 'SENSEX' else "BSE_INDEX",
                "expiry_date": next_expiry,
                "strike_count": 20
            }

            chain_data = self._post('/api/v1/optionchain', payload)
            if chain_data and chain_data.get('status') == 'success':
                self.market_data['chains'][index] = chain_data
            else:
                logger.warning(f"Could not fetch chain for {index}, using mock data for analysis demonstration")
                self.market_data['chains'][index] = self._generate_mock_chain(index)

        # 2. Fetch/Mock External Data
        self.market_data['vix'] = self._fetch_vix()
        self.market_data['gift_nifty'] = self._fetch_gift_nifty()
        self.market_data['sentiment'] = self._fetch_news_sentiment()

    def _generate_mock_chain(self, index):
        """Generate mock option chain if API is unavailable"""
        spot = 24500 if index == 'NIFTY' else 52000 if index == 'BANKNIFTY' else 80000
        chain = []
        for i in range(-10, 11):
            strike = spot + (i * 50)
            chain.append({
                "strike": strike,
                "ce": {"ltp": max(10, 200 - i*10), "oi": abs(10000 - i*100), "volume": 5000},
                "pe": {"ltp": max(10, 200 + i*10), "oi": abs(10000 + i*100), "volume": 5000}
            })
        return {"underlying_ltp": spot, "chain": chain, "status": "success"}

    def _fetch_vix(self):
        """Mock VIX data"""
        # In real implementation, scrape NSE or use API
        return {"value": 14.5, "trend": "falling", "percentile": 45}

    def _fetch_gift_nifty(self):
        """Mock GIFT Nifty data"""
        return {"value": 24600, "gap_percent": 0.4, "bias": "Up"}

    def _fetch_news_sentiment(self):
        """Mock News Sentiment"""
        return {"score": 0.6, "label": "Positive", "key_events": ["Earnings Season"]}

    def get_greeks(self, index, strike, option_type):
        """
        Calculate or fetch Greeks.
        In a real scenario, this would call /api/v1/optiongreeks or use a library.
        For now, returns mock values to demonstrate report format.
        """
        return {"delta": 0.25, "gamma": 0.002, "theta": -15, "vega": 8, "iv": 18}

    def analyze_market(self):
        """Analyze market data and generate opportunities"""
        logger.info("Analyzing market data...")
        self.strategies = []

        vix = self.market_data['vix']
        sentiment = self.market_data['sentiment']
        gift = self.market_data['gift_nifty']

        for index, data in self.market_data['chains'].items():
            if not data: continue

            spot = data.get('underlying_ltp', 0)

            # --- Scoring Logic ---
            # Formula: (IV Rank * 0.25) + (Greeks * 0.20) + (Liquidity * 0.15) + (PCR * 0.15) + (VIX * 0.10) + (GIFT * 0.10) + (News * 0.05)
            # We mock the sub-scores here as we don't have full data streams

            # 1. Iron Condor (Neutral)
            iv_rank_score = 70 if 12 < vix['value'] < 20 else 40
            greeks_score = 80 # Assuming decent theta/gamma profile
            liquidity_score = 90
            pcr_score = 60
            vix_regime_score = 90 if 12 < vix['value'] < 25 else 40
            gift_score = 50 # Neutral
            news_score = 80 if sentiment['label'] == 'Neutral' else 50

            composite_score = (
                (iv_rank_score * 0.25) +
                (greeks_score * 0.20) +
                (liquidity_score * 0.15) +
                (pcr_score * 0.15) +
                (vix_regime_score * 0.10) +
                (gift_score * 0.10) +
                (news_score * 0.05)
            )

            self.strategies.append({
                "type": "Iron Condor",
                "index": index,
                "score": int(composite_score),
                "rationale": f"VIX {vix['value']} optimal, High Liquidity",
                "risk_reward": "1:2",
                "details": f"Sell {int(spot*1.02)} CE / {int(spot*0.98)} PE",
                "iv_rank": 45,
                "greeks": self.get_greeks(index, spot, 'CE')
            })

            # 2. Bull Put Spread (Bullish)
            # Adjust scores based on bias
            gift_score = 90 if gift['bias'] == 'Up' else 30
            news_score = 90 if sentiment['label'] == 'Positive' else 40

            composite_score_bull = (
                (iv_rank_score * 0.25) +
                (greeks_score * 0.20) +
                (liquidity_score * 0.15) +
                (pcr_score * 0.15) +
                (vix_regime_score * 0.10) +
                (gift_score * 0.10) +
                (news_score * 0.05)
            )

            self.strategies.append({
                "type": "Bull Put Spread",
                "index": index,
                "score": int(composite_score_bull),
                "rationale": "Bullish Bias from GIFT and Sentiment",
                "risk_reward": "1:3",
                "details": f"Sell {int(spot*0.99)} PE, Buy {int(spot*0.98)} PE",
                "iv_rank": 40,
                "greeks": self.get_greeks(index, spot, 'PE')
            })

        # Sort strategies by score
        self.strategies.sort(key=lambda x: x['score'], reverse=True)

    def generate_report(self):
        """Generate the report in the requested format"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        vix = self.market_data['vix']
        gift = self.market_data['gift_nifty']
        sent = self.market_data['sentiment']

        report = []
        report.append(f"📊 DAILY OPTIONS STRATEGY ANALYSIS - {date_str}")
        report.append("")
        report.append("📈 MARKET DATA SUMMARY:")
        report.append(f"- NIFTY Spot: {self.market_data['chains'].get('NIFTY', {}).get('underlying_ltp', 'N/A')} | VIX: {vix['value']} ({vix['trend']})")
        report.append(f"- GIFT Nifty: {gift['value']} | Gap: {gift['gap_percent']}% | Bias: {gift['bias']}")
        report.append(f"- News Sentiment: {sent['label']} | Key Events: {', '.join(sent['key_events'])}")
        report.append("")
        report.append("🎯 STRATEGY OPPORTUNITIES (Ranked):")

        for i, strat in enumerate(self.strategies[:5], 1):
            g = strat['greeks']
            report.append("")
            report.append(f"{i}. {strat['type']} - {strat['index']} - Score: {strat['score']}/100")
            report.append(f"   - IV Rank: {strat['iv_rank']}% | Greeks: Delta={g['delta']}, Gamma={g['gamma']}, Theta={g['theta']}, Vega={g['vega']}")
            report.append(f"   - Entry: {strat['details']}")
            report.append(f"   - Rationale: {strat['rationale']}")
            report.append(f"   - R:R: {strat['risk_reward']}")

        report.append("")
        report.append("🔧 STRATEGY ENHANCEMENTS APPLIED:")
        report.append("- Iron Condor: Added VIX filter (VIX > 12 preferred)")
        report.append("- Bull Spreads: Added GIFT Nifty Gap filter")

        report.append("")
        report.append("⚠️ RISK WARNINGS:")
        if vix['value'] > 20:
            report.append("- High VIX detected -> Reduce position sizes")
        if sent['label'] == 'Negative':
             report.append("- Negative sentiment -> Avoid Bullish strategies")

        report_text = "\n".join(report)
        print(report_text)

        # Also save to file
        with open(os.path.join(LOG_DIR, f"strategy_report_{date_str}.txt"), "w") as f:
            f.write(report_text)

    def run(self):
        self.fetch_market_data()
        self.analyze_market()
        self.generate_report()

if __name__ == "__main__":
    ranker = AdvancedOptionsRanker()
    ranker.run()
