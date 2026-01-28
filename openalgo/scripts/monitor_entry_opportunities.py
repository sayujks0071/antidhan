#!/usr/bin/env python3
"""
Monitor All Running Strategies for Entry Opportunities
Continuously monitors MCX strategy logs and identifies potential entry signals
Uses Clawdbot AI for entry opportunity analysis
"""
import os
import sys
import time
import json
import subprocess
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta
import pytz
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent.parent / 'log' / 'entry_opportunities_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("EntryOpportunitiesMonitor")

# Configuration
CHECK_INTERVAL = 30  # Check every 30 seconds
ANALYSIS_INTERVAL = 180  # AI analysis every 3 minutes
ALERT_INTERVAL = 300  # Alert summary every 5 minutes

class EntryOpportunityMonitor:
    def __init__(self):
        self.ist = pytz.timezone('Asia/Kolkata')
        self.entry_signals = defaultdict(list)  # symbol -> list of signals
        self.last_analysis_time = 0
        self.last_alert_time = 0
        self.strategy_logs = {}
        
        logger.info("=" * 70)
        logger.info("Entry Opportunities Monitor Started")
        logger.info("=" * 70)
        logger.info(f"Check Interval: {CHECK_INTERVAL}s")
        logger.info(f"AI Analysis Interval: {ANALYSIS_INTERVAL}s")
        logger.info("=" * 70)
    
    def get_running_strategies(self):
        """Get list of running MCX strategies"""
        try:
            config_file = Path(__file__).parent.parent / 'strategies' / 'strategy_configs.json'
            with open(config_file, 'r') as f:
                configs = json.load(f)
            
            running_strategies = []
            for key, config in configs.items():
                if config.get('is_running') and 'mcx' in key.lower():
                    running_strategies.append({
                        'name': config.get('name', key),
                        'key': key,
                        'pid': config.get('pid'),
                        'file_path': config.get('file_path', '')
                    })
            
            return running_strategies
        except Exception as e:
            logger.error(f"Error loading strategy configs: {e}")
            return []
    
    def get_strategy_logs(self, strategy_name, lines=100):
        """Get latest log entries for a strategy"""
        log_dir = Path(__file__).parent.parent / "log" / "strategies"
        if not log_dir.exists():
            return ""
        
        # Try to find log file matching strategy name
        log_patterns = [
            f"{strategy_name}*.log",
            f"mcx_*.log",
            "*.log"
        ]
        
        all_logs = []
        for pattern in log_patterns:
            for log_file in sorted(log_dir.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)[:3]:
                try:
                    with open(log_file, 'r') as f:
                        log_lines = f.readlines()
                        recent_lines = log_lines[-lines:] if len(log_lines) > lines else log_lines
                        all_logs.append(f"\n=== {log_file.name} ===\n")
                        all_logs.extend(recent_lines)
                except Exception as e:
                    logger.debug(f"Error reading {log_file}: {e}")
        
        return "".join(all_logs)
    
    def extract_entry_signals(self, log_content, strategy_name):
        """Extract entry signals from logs"""
        signals = []
        
        # Patterns to look for
        patterns = [
            r'(BUY|SELL)\s+Signal\s+Generated',
            r'(BUY|SELL):\s+Signal',
            r'Signal:\s+(BUY|SELL)',
            r'Entry\s+Signal:\s+(BUY|SELL)',
            r'✅\s+(BUY|SELL)\s+Signal',
            r'Placing\s+order:\s+(BUY|SELL)',
            r'Signal\s+score.*(BUY|SELL)',
        ]
        
        for line in log_content.split('\n'):
            for pattern in patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    action = match.group(1).upper()
                    
                    # Extract symbol if present
                    symbol_match = re.search(r'([A-Z]+M?\d+[A-Z]+\d+FUT)', line)
                    symbol = symbol_match.group(1) if symbol_match else "UNKNOWN"
                    
                    # Extract price if present
                    price_match = re.search(r'₹?([\d,]+\.?\d*)', line)
                    price = price_match.group(1).replace(',', '') if price_match else None
                    
                    # Extract score/confidence if present
                    score_match = re.search(r'score[:\s]+(\d+\.?\d*)', line, re.IGNORECASE)
                    score = float(score_match.group(1)) if score_match else None
                    
                    signals.append({
                        'action': action,
                        'symbol': symbol,
                        'price': float(price) if price else None,
                        'score': score,
                        'strategy': strategy_name,
                        'timestamp': datetime.now(self.ist).isoformat(),
                        'line': line.strip()
                    })
        
        return signals
    
    def extract_technical_data(self, log_content):
        """Extract technical indicators from logs"""
        tech_data = {}
        
        # Look for RSI, MACD, ADX, EMA, etc.
        patterns = {
            'rsi': r'RSI[:\s]+(\d+\.?\d*)',
            'macd': r'MACD[:\s]+([-]?\d+\.?\d*)',
            'adx': r'ADX[:\s]+(\d+\.?\d*)',
            'ema': r'EMA[:\s]+(\d+\.?\d*)',
            'price': r'Price[:\s]+₹?([\d,]+\.?\d*)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, log_content, re.IGNORECASE)
            if match:
                try:
                    tech_data[key] = float(match.group(1).replace(',', ''))
                except:
                    pass
        
        return tech_data
    
    def analyze_with_clawdbot(self, signals, technical_data):
        """Use Clawdbot to analyze entry opportunities"""
        if not signals:
            return None
        
        # Prepare summary for Clawdbot
        signal_summary = []
        for signal in signals[-10:]:  # Last 10 signals
            signal_summary.append(
                f"{signal['action']} {signal['symbol']} "
                f"(Score: {signal.get('score', 'N/A')}, Strategy: {signal['strategy']})"
            )
        
        prompt = f"""Analyze these MCX trading entry signals and provide recommendations:

Signals Detected:
{chr(10).join(signal_summary)}

Technical Data:
{json.dumps(technical_data, indent=2) if technical_data else 'No technical data available'}

Please provide:
1. Best entry opportunities (ranked by quality)
2. Risk assessment for each signal
3. Recommended position sizing
4. Entry timing (immediate vs wait)
5. Stop loss and take profit levels

Format as JSON with: opportunities (array), risk_assessment, recommendations"""
        
        try:
            env = dict(os.environ)
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                return None
            env["OPENAI_API_KEY"] = openai_key
            
            result = subprocess.run(
                ["clawdbot", "agent", "--message", prompt, "--session-id", "entry-opportunities", "--json"],
                capture_output=True,
                text=True,
                timeout=45,
                env=env
            )
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    return {"response": result.stdout.strip()}
            else:
                error_output = result.stderr if result.stderr else result.stdout
                logger.debug(f"Clawdbot analysis: {error_output[:200]}")
                return None
        except subprocess.TimeoutExpired:
            logger.warning("Clawdbot analysis timed out")
            return None
        except FileNotFoundError:
            logger.debug("Clawdbot CLI not found")
            return None
        except Exception as e:
            logger.debug(f"Error calling Clawdbot: {e}")
            return None
    
    def send_clawdbot_alert(self, message, priority="info"):
        """Send alert via Clawdbot"""
        try:
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                return False
            
            alert_message = f"[{priority.upper()}] Entry Monitor: {message}"
            result = subprocess.run(
                ["clawdbot", "message", "--text", alert_message],
                capture_output=True,
                text=True,
                timeout=10,
                env=dict(os.environ, OPENAI_API_KEY=openai_key)
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"Alert error: {e}")
            return False
    
    def display_opportunities(self, signals_by_symbol, analysis=None):
        """Display entry opportunities in a formatted way"""
        now = datetime.now(self.ist)
        
        print("\n" + "=" * 70)
        print(f"📊 Entry Opportunities Monitor - {now.strftime('%Y-%m-%d %H:%M:%S IST')}")
        print("=" * 70)
        
        if not signals_by_symbol:
            print("\n⏸️  No entry signals detected in recent logs")
            print("   Monitoring strategies for new opportunities...")
        else:
            print(f"\n🎯 Entry Signals Detected: {sum(len(s) for s in signals_by_symbol.values())} total")
            print("-" * 70)
            
            for symbol, signals in signals_by_symbol.items():
                if not signals:
                    continue
                
                # Group by action
                buy_signals = [s for s in signals if s['action'] == 'BUY']
                sell_signals = [s for s in signals if s['action'] == 'SELL']
                
                print(f"\n📈 {symbol}:")
                
                if buy_signals:
                    latest_buy = buy_signals[-1]
                    print(f"   🟢 BUY Signal:")
                    print(f"      Strategy: {latest_buy['strategy']}")
                    if latest_buy.get('score'):
                        print(f"      Score: {latest_buy['score']}")
                    if latest_buy.get('price'):
                        print(f"      Price: ₹{latest_buy['price']:,.2f}")
                    print(f"      Count: {len(buy_signals)} signal(s)")
                
                if sell_signals:
                    latest_sell = sell_signals[-1]
                    print(f"   🔴 SELL Signal:")
                    print(f"      Strategy: {latest_sell['strategy']}")
                    if latest_sell.get('score'):
                        print(f"      Score: {latest_sell['score']}")
                    if latest_sell.get('price'):
                        print(f"      Price: ₹{latest_sell['price']:,.2f}")
                    print(f"      Count: {len(sell_signals)} signal(s)")
        
        if analysis:
            print("\n" + "-" * 70)
            print("🤖 Clawdbot AI Analysis:")
            print("-" * 70)
            
            if isinstance(analysis, dict):
                if "opportunities" in analysis:
                    print("\nTop Entry Opportunities:")
                    for i, opp in enumerate(analysis["opportunities"][:5], 1):
                        print(f"   {i}. {opp}")
                elif "response" in analysis:
                    print(analysis["response"])
                else:
                    for key, value in analysis.items():
                        if isinstance(value, (list, dict)):
                            print(f"\n{key.upper()}:")
                            print(json.dumps(value, indent=2))
                        else:
                            print(f"{key.upper()}: {value}")
            else:
                print(str(analysis))
        
        print("\n" + "=" * 70)
    
    def run(self):
        """Main monitoring loop"""
        logger.info("🚀 Starting entry opportunities monitoring...")
        
        while True:
            try:
                now = datetime.now(self.ist)
                current_time = time.time()
                
                # Get running strategies
                strategies = self.get_running_strategies()
                
                if not strategies:
                    logger.warning("No running MCX strategies found")
                    time.sleep(CHECK_INTERVAL)
                    continue
                
                # Collect signals from all strategies
                all_signals = []
                signals_by_symbol = defaultdict(list)
                all_technical_data = {}
                
                for strategy in strategies:
                    strategy_name = strategy['name']
                    log_content = self.get_strategy_logs(strategy_name, lines=50)
                    
                    if log_content:
                        # Extract signals
                        signals = self.extract_entry_signals(log_content, strategy_name)
                        all_signals.extend(signals)
                        
                        # Group by symbol
                        for signal in signals:
                            if signal['symbol'] != 'UNKNOWN':
                                signals_by_symbol[signal['symbol']].append(signal)
                        
                        # Extract technical data
                        tech_data = self.extract_technical_data(log_content)
                        if tech_data:
                            all_technical_data[strategy_name] = tech_data
                
                # Display opportunities
                self.display_opportunities(signals_by_symbol)
                
                # AI Analysis (every ANALYSIS_INTERVAL)
                analysis = None
                if current_time - self.last_analysis_time >= ANALYSIS_INTERVAL:
                    if all_signals:
                        logger.info("🤖 Running Clawdbot AI analysis...")
                        analysis = self.analyze_with_clawdbot(all_signals, all_technical_data)
                        if analysis:
                            self.display_opportunities(signals_by_symbol, analysis)
                    
                    self.last_analysis_time = current_time
                
                # Send alerts for high-quality signals (every ALERT_INTERVAL)
                if current_time - self.last_alert_time >= ALERT_INTERVAL:
                    high_quality_signals = [
                        s for s in all_signals
                        if s.get('score') and s.get('score', 0) >= 60
                    ]
                    
                    if high_quality_signals:
                        alert_msg = f"High-quality entry signals detected:\n"
                        for signal in high_quality_signals[-5:]:
                            alert_msg += f"{signal['action']} {signal['symbol']} (Score: {signal['score']}, Strategy: {signal['strategy']})\n"
                        self.send_clawdbot_alert(alert_msg, priority="info")
                    
                    self.last_alert_time = current_time
                
                # Wait before next check
                time.sleep(CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("🛑 Monitor stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)
                time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor = EntryOpportunityMonitor()
    monitor.run()
