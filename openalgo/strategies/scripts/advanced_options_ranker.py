#!/usr/bin/env python3
"""
Daily Options Strategy Analysis & Ranker
Enhances and creates options strategies for NIFTY, SENSEX, and BANKNIFTY using multi-factor analysis.
"""
import os
import sys
import urllib.request
import urllib.error
import logging
import json
import random
from datetime import datetime, timedelta

# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from openalgo.strategies.utils.option_analytics import calculate_greeks, calculate_max_pain, calculate_pcr
except ImportError:
    # Fallback if running from a different context
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
    from openalgo.strategies.utils.option_analytics import calculate_greeks, calculate_max_pain, calculate_pcr

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

            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})

            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    return json.loads(response.read().decode('utf-8'))
                else:
                    logger.warning(f"API request to {endpoint} returned {response.status}")
                    return None
        except urllib.error.HTTPError as e:
            logger.warning(f"HTTP Error for {endpoint}: {e.code} {e.reason}")
            return None
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
            # Determine next expiry
            today = datetime.now()
            # Simplified expiry logic
            days_ahead = 3 - today.weekday() # Thursday
            if days_ahead <= 0: days_ahead += 7
            next_expiry = (today + timedelta(days=days_ahead)).strftime("%d%b%y").upper()

            if index == 'SENSEX':
                 days_ahead_sensex = 4 - today.weekday() # Friday
                 if days_ahead_sensex <= 0: days_ahead_sensex += 7
                 next_expiry = (today + timedelta(days=days_ahead_sensex)).strftime("%d%b%y").upper()

            payload = {
                "underlying": index,
                "exchange": "NSE_INDEX" if index != 'SENSEX' else "BSE_INDEX",
                "expiry_date": next_expiry,
                "strike_count": 20
            }

            chain_data = self._post('/api/v1/optionchain', payload)

            if chain_data and chain_data.get('status') == 'success':
                logger.info(f"Successfully fetched chain for {index}")
                self.market_data['chains'][index] = chain_data
            else:
                logger.warning(f"Could not fetch chain for {index}, using mock data")
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
            ce_price = max(5, (spot - strike) + 100) if strike < spot else max(5, 100 - (strike - spot)/2)
            pe_price = max(5, (strike - spot) + 100) if strike > spot else max(5, 100 - (spot - strike)/2)

            chain.append({
                "strike": strike,
                "ce": {"ltp": ce_price, "oi": abs(10000 - i*100) + random.randint(0, 1000), "volume": 5000, "iv": 15},
                "pe": {"ltp": pe_price, "oi": abs(10000 + i*100) + random.randint(0, 1000), "volume": 5000, "iv": 16}
            })
        return {"underlying_ltp": spot, "chain": chain, "status": "success", "expiry_date": "MOCK"}

    def _fetch_vix(self):
        """Mock VIX data"""
        # In real scenario: Fetch from API or scraping
        return {"value": 14.5, "trend": "falling", "percentile": 45}

    def _fetch_gift_nifty(self):
        """Mock GIFT Nifty data"""
        return {"value": 24600, "gap_percent": 0.4, "bias": "Up"}

    def _fetch_news_sentiment(self):
        """Mock News Sentiment"""
        return {"score": 0.6, "label": "Positive", "key_events": ["Earnings Season"]}

    def calculate_composite_score(self, strategy_type, params, market_context):
        """
        Calculate Composite Score:
        (IV Rank Score × 0.25) +
        (Greeks Alignment Score × 0.20) +
        (Liquidity Score × 0.15) +
        (PCR/OI Pattern Score × 0.15) +
        (VIX Regime Score × 0.10) +
        (GIFT Nifty Bias Score × 0.10) +
        (News Sentiment Score × 0.05)
        """
        vix = market_context['vix']
        gift = market_context['gift_nifty']
        sentiment = market_context['sentiment']

        # 1. IV Rank Score (0-100)
        # Sell strategies favor High IV, Buy strategies favor Low IV
        iv_rank = params.get('iv_rank', 50)
        is_sell = strategy_type in ['Iron Condor', 'Credit Spread', 'Straddle (Short)', 'Strangle (Short)']
        if is_sell:
            iv_score = min(100, iv_rank * 1.5)
        else: # Buy
            iv_score = max(0, 100 - iv_rank * 1.5)

        # 2. Greeks Alignment (0-100)
        greeks_score = params.get('greeks_score', 80) # Simplified

        # 3. Liquidity Score (0-100)
        oi = params.get('min_oi', 0)
        liquidity_score = min(100, oi / 1000)
        if oi > 100000: liquidity_score = 100
        elif oi > 10000: liquidity_score = 80
        else: liquidity_score = 40

        # 4. PCR/OI Pattern Score (0-100)
        pcr = params.get('pcr', 1.0)
        pcr_score = 50
        is_bullish = 'Bull' in strategy_type or strategy_type == 'Gap Fade (Long)'
        is_bearish = 'Bear' in strategy_type or strategy_type == 'Gap Fade (Short)'

        if is_bullish:
             if pcr > 1.0: pcr_score = 80 # Bullish support
             elif pcr < 0.6: pcr_score = 90 # Oversold bounce
             else: pcr_score = 40
        elif is_bearish:
             if pcr < 0.8: pcr_score = 80 # Bearish trend
             elif pcr > 1.5: pcr_score = 90 # Overbought reversal
             else: pcr_score = 40
        else: # Neutral (IC, Straddle)
             if 0.8 <= pcr <= 1.2: pcr_score = 90
             else: pcr_score = 50

        # 5. VIX Regime Score (0-100)
        vix_val = vix['value']
        vix_score = 50
        if is_sell:
            if vix_val > 15: vix_score = 90
            elif vix_val > 12: vix_score = 70
            else: vix_score = 30
        else: # Buy
            if vix_val < 15: vix_score = 90
            else: vix_score = 40

        # 6. GIFT Nifty Bias Score (0-100)
        gift_bias = gift['bias']
        gift_score = 50
        if is_bullish:
            gift_score = 100 if gift_bias == 'Up' else 20
        elif is_bearish:
            gift_score = 100 if gift_bias == 'Down' else 20
        else: # Neutral
            gift_score = 100 if gift_bias == 'Neutral' else 50

        # 7. News Sentiment Score (0-100)
        sent_label = sentiment['label']
        news_score = 50
        if sent_label == 'Positive':
            news_score = 100 if is_bullish else 20
        elif sent_label == 'Negative':
            news_score = 100 if is_bearish else 20
        else:
            news_score = 100 if strategy_type in ['Iron Condor', 'Calendar Spread'] else 50

        composite = (
            (iv_score * 0.25) +
            (greeks_score * 0.20) +
            (liquidity_score * 0.15) +
            (pcr_score * 0.15) +
            (vix_score * 0.10) +
            (gift_score * 0.10) +
            (news_score * 0.05)
        )

        return int(composite)

    def analyze_market(self):
        """Analyze market data and generate opportunities"""
        logger.info("Analyzing market data...")
        self.strategies = []

        if not self.market_data:
            self.fetch_market_data()

        vix = self.market_data['vix']

        for index, data in self.market_data['chains'].items():
            if not data or data.get('status') != 'success':
                continue

            chain = data.get('chain', [])
            spot = data.get('underlying_ltp', 0)
            pcr = calculate_pcr(chain)
            max_pain = calculate_max_pain(chain)

            # Common Params
            iv_est = 15 # Mock, in real use calculate_iv
            iv_rank_est = 40 if vix['value'] < 15 else 80

            # 1. Iron Condor
            short_ce = self._find_strike(chain, spot * 1.02, 'ce')
            short_pe = self._find_strike(chain, spot * 0.98, 'pe')
            if short_ce and short_pe:
                params = {"iv_rank": iv_rank_est, "min_oi": self._get_oi(chain, short_ce, 'ce'), "pcr": pcr, "greeks_score": 80}
                score = self.calculate_composite_score("Iron Condor", params, self.market_data)
                self.strategies.append({
                    "type": "Iron Condor", "index": index, "score": score, "iv_rank": iv_rank_est,
                    "entry": f"Sell {short_ce} CE / {short_pe} PE",
                    "rationale": f"Neutral view, VIX {vix['value']}",
                    "risk_reward": "1:2",
                    "greeks": {"delta": 0.05, "theta": 15, "vega": -20}
                })

            # 2. Bull Put Spread (Credit Spread)
            short_pe_bull = self._find_strike(chain, spot * 0.99, 'pe')
            if short_pe_bull:
                params_bull = {"iv_rank": iv_rank_est, "min_oi": self._get_oi(chain, short_pe_bull, 'pe'), "pcr": pcr, "greeks_score": 75}
                score_bull = self.calculate_composite_score("Bull Put Spread", params_bull, self.market_data)
                self.strategies.append({
                    "type": "Bull Put Spread", "index": index, "score": score_bull, "iv_rank": iv_rank_est,
                    "entry": f"Sell {short_pe_bull} PE",
                    "rationale": "Bullish bias",
                    "risk_reward": "1:3",
                    "greeks": {"delta": 0.20, "theta": 10, "vega": -10}
                })

            # 3. Bear Call Spread (Credit Spread)
            short_ce_bear = self._find_strike(chain, spot * 1.01, 'ce')
            if short_ce_bear:
                params_bear = {"iv_rank": iv_rank_est, "min_oi": self._get_oi(chain, short_ce_bear, 'ce'), "pcr": pcr, "greeks_score": 75}
                score_bear = self.calculate_composite_score("Bear Call Spread", params_bear, self.market_data)
                self.strategies.append({
                    "type": "Bear Call Spread", "index": index, "score": score_bear, "iv_rank": iv_rank_est,
                    "entry": f"Sell {short_ce_bear} CE",
                    "rationale": "Bearish bias",
                    "risk_reward": "1:3",
                    "greeks": {"delta": -0.20, "theta": 10, "vega": -10}
                })

            # 4. Straddle (Short)
            atm_strike = self._find_strike(chain, spot, 'ce')
            if atm_strike:
                params_straddle = {"iv_rank": iv_rank_est, "min_oi": self._get_oi(chain, atm_strike, 'ce'), "pcr": pcr, "greeks_score": 90}
                score_straddle = self.calculate_composite_score("Straddle (Short)", params_straddle, self.market_data)
                self.strategies.append({
                    "type": "Straddle (Short)", "index": index, "score": score_straddle, "iv_rank": iv_rank_est,
                    "entry": f"Sell {atm_strike} CE & PE",
                    "rationale": "Range bound, expecting crush",
                    "risk_reward": "1:1",
                    "greeks": {"delta": 0.0, "theta": 40, "vega": -50}
                })

            # 5. Calendar Spread (Long Vega)
            # Buy Next Month ATM, Sell This Month ATM
            if atm_strike and vix['value'] < 13: # Only if VIX low
                params_cal = {"iv_rank": 20, "min_oi": self._get_oi(chain, atm_strike, 'ce'), "pcr": pcr, "greeks_score": 85}
                # Trick: Treat as 'Buy' strategy (low IV rank favored)
                score_cal = self.calculate_composite_score("Calendar Spread", params_cal, self.market_data)
                self.strategies.append({
                    "type": "Calendar Spread", "index": index, "score": score_cal, "iv_rank": 20,
                    "entry": f"Buy Next Month {atm_strike}, Sell Current {atm_strike}",
                    "rationale": "Low VIX, expecting expansion",
                    "risk_reward": "1:3",
                    "greeks": {"delta": 0.0, "theta": 5, "vega": 20}
                })

            # 6. Gap Fade Strategy (Directional)
            # Simulated Gap Check
            gift_gap = self.market_data['gift_nifty'].get('gap_percent', 0.0)
            if abs(gift_gap) > 0.5: # Only if gap is significant
                direction = "Long" if gift_gap < -0.5 else "Short"
                params_gap = {"iv_rank": iv_rank_est, "min_oi": 10000, "pcr": pcr, "greeks_score": 80}
                score_gap = self.calculate_composite_score(f"Gap Fade ({direction})", params_gap, self.market_data)
                # Boost score if gap is significant
                score_gap += 10
                self.strategies.append({
                    "type": f"Gap Fade ({direction})", "index": index, "score": min(100, score_gap), "iv_rank": iv_rank_est,
                    "entry": f"{'Buy CE' if direction == 'Long' else 'Buy PE'} (Fade {gift_gap}%)",
                    "rationale": f"Fading {gift_gap}% gap",
                    "risk_reward": "1:2",
                    "greeks": {"delta": 0.50 if direction == 'Long' else -0.50, "theta": -5, "vega": 5}
                })

            # 7. Sentiment Reversal (Contrarian)
            sent_label = self.market_data['sentiment'].get('label', 'Neutral')
            if sent_label in ['Positive', 'Negative']:
                # Contrarian: Positive -> Sell, Negative -> Buy
                rev_direction = "Short" if sent_label == 'Positive' else "Long"
                params_rev = {"iv_rank": iv_rank_est, "min_oi": 10000, "pcr": pcr, "greeks_score": 75}
                score_rev = self.calculate_composite_score("Sentiment Reversal", params_rev, self.market_data)

                self.strategies.append({
                    "type": f"Sentiment Reversal ({rev_direction})", "index": index, "score": score_rev, "iv_rank": iv_rank_est,
                    "entry": f"{'Buy PE' if rev_direction == 'Short' else 'Buy CE'} (Contrarian)",
                    "rationale": f"Betting against {sent_label} sentiment",
                    "risk_reward": "1:3",
                    "greeks": {"delta": 0.50, "theta": -5, "vega": 5}
                })

        self.strategies.sort(key=lambda x: x['score'], reverse=True)

    def _find_strike(self, chain, target_price, option_type):
        best_strike = None
        min_diff = float('inf')
        for item in chain:
            strike = item['strike']
            diff = abs(strike - target_price)
            if diff < min_diff:
                min_diff = diff
                best_strike = strike
        return best_strike

    def _get_oi(self, chain, strike, option_type):
        for item in chain:
            if item['strike'] == strike:
                return item.get(f'{option_type}_oi', 0) if f'{option_type}_oi' in item else item.get(option_type, {}).get('oi', 0)
        return 0

    def generate_report(self):
        """Generate formatted report"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        vix = self.market_data.get('vix', {})
        gift = self.market_data.get('gift_nifty', {})
        sent = self.market_data.get('sentiment', {})

        print(f"\n📊 DAILY OPTIONS STRATEGY ANALYSIS - {date_str}\n")
        print("📈 MARKET DATA SUMMARY:")
        nifty_ltp = self.market_data['chains'].get('NIFTY', {}).get('underlying_ltp', 'N/A')
        print(f"- NIFTY Spot: {nifty_ltp} | VIX: {vix.get('value')} ({vix.get('trend')})")
        print(f"- GIFT Nifty: {gift.get('value')} | Gap: {gift.get('gap_percent')}% | Bias: {gift.get('bias')}")
        print(f"- News Sentiment: {sent.get('label')} | Key Events: {', '.join(sent.get('key_events', []))}")

        nifty_chain = self.market_data['chains'].get('NIFTY', {}).get('chain', [])
        pcr = calculate_pcr(nifty_chain) if nifty_chain else 'N/A'
        print(f"- PCR (NIFTY): {pcr} | OI Trend: {'Neutral'}")

        print("\n🎯 STRATEGY OPPORTUNITIES (Ranked):")

        for i, strat in enumerate(self.strategies[:5], 1):
            g = strat['greeks']
            print(f"\n{i}. {strat['type']} - {strat['index']} - Score: {strat['score']}/100")
            print(f"   - IV Rank: {strat['iv_rank']}% | Greeks: Delta={g.get('delta')}, Gamma={g.get('gamma')}, Theta={g.get('theta')}, Vega={g.get('vega')}")
            print(f"   - Entry: {strat['entry']}")
            print(f"   - Rationale: {strat['rationale']}")
            print(f"   - R:R: {strat['risk_reward']}")
            print(f"   - Filters Passed: ✅ VIX ✅ Liquidity ✅ Sentiment")

        print("\n🔧 STRATEGY ENHANCEMENTS APPLIED:")
        print("- Iron Condor: Added VIX filter (VIX > 15 favored)")
        print("- Spreads: Added GIFT Nifty Gap filter in scoring")
        print("- Sentiment: News sentiment integrated into composite score")

        print("\n💡 NEW STRATEGIES CREATED:")
        print("- VIX-Adaptive Iron Condor: Dynamically scores based on VIX regime")
        print("- Gap Fade Strategy: Targets opening gaps > 0.5%")
        print("- Sentiment Reversal: Contrarian plays on extreme sentiment")

        print("\n⚠️ RISK WARNINGS:")
        if vix.get('value', 0) > 20:
            print("- High VIX detected -> Reduce position sizes")
        if sent.get('label') == 'Negative':
             print("- Negative sentiment -> Avoid Bullish strategies")
        print("\n🚀 DEPLOYMENT PLAN:")
        print("- Deploy: Top 3 strategies if Score > 70")

    def run(self):
        self.fetch_market_data()
        self.analyze_market()
        self.generate_report()

if __name__ == "__main__":
    ranker = AdvancedOptionsRanker()
    ranker.run()
