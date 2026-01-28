#!/usr/bin/env python3
"""
Live Trading Monitor using Clawdbot AI
Monitors MCX strategies in real-time and provides AI-powered insights
"""
import os
import sys
import time
import json
import re
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import pytz

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ClawdbotMonitor")

# Debug logging setup
DEBUG_LOG_PATH = Path(__file__).parent.parent.parent / ".cursor" / "debug.log"

def debug_log(hypothesis_id, location, message, data=None):
    """Write debug log entry"""
    try:
        log_entry = {
            "sessionId": "clawdbot-monitor-debug",
            "runId": "run1",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000)
        }
        with open(DEBUG_LOG_PATH, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception:
        pass  # Silently fail if logging fails

# Add services to path
services_path = Path(__file__).parent.parent / 'services'
if str(services_path) not in sys.path:
    sys.path.insert(0, str(services_path))

try:
    # #region agent log
    debug_log("H1", "monitor_live_trading_clawdbot.py:21", "Testing Clawdbot availability", {"step": "import_check"})
    # #endregion
    from clawdbot_bridge_service import get_bridge_service
    # #region agent log
    debug_log("H1", "monitor_live_trading_clawdbot.py:24", "Bridge service imported successfully")
    # #endregion
    # Test connection
    bridge = get_bridge_service()
    # #region agent log
    debug_log("H1", "monitor_live_trading_clawdbot.py:27", "Bridge service obtained", {"enabled": bridge.enabled, "gateway_url": bridge.gateway_url})
    # #endregion
    if bridge.enabled:
        # Try to check if gateway is reachable
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        # #region agent log
        debug_log("H2", "monitor_live_trading_clawdbot.py:32", "Testing socket connection to gateway", {"host": "127.0.0.1", "port": 18789})
        # #endregion
        result = sock.connect_ex(('127.0.0.1', 18789))
        sock.close()
        # #region agent log
        debug_log("H2", "monitor_live_trading_clawdbot.py:36", "Socket connection test result", {"result": result, "available": result == 0})
        # #endregion
        CLAWDBOT_AVAILABLE = (result == 0)
    else:
        # #region agent log
        debug_log("H1", "monitor_live_trading_clawdbot.py:39", "Bridge service disabled")
        # #endregion
        CLAWDBOT_AVAILABLE = False
except (ImportError, Exception) as e:
    # #region agent log
    debug_log("H1", "monitor_live_trading_clawdbot.py:42", "Exception during Clawdbot availability check", {"error": str(e), "type": type(e).__name__})
    # #endregion
    CLAWDBOT_AVAILABLE = False

# Strategy log directory
LOG_DIR = Path(__file__).parent.parent / "log" / "strategies"

def get_latest_mcx_logs():
    """Get the latest log files for each MCX strategy"""
    mcx_logs = {}
    for log_file in sorted(LOG_DIR.glob("*mcx*.log"), key=lambda x: x.stat().st_mtime, reverse=True):
        strategy_name = log_file.stem.split('_')[0:3]  # Extract strategy name
        strategy_key = '_'.join(strategy_name)
        if strategy_key not in mcx_logs:
            mcx_logs[strategy_key] = log_file
    return mcx_logs

def extract_latest_signals(log_file, lines_to_read=50):
    """Extract latest signals and key information from log file"""
    signals = {
        'price': None,
        'buy_signal': None,
        'sell_signal': None,
        'rsi': None,
        'adx': None,
        'atr': None,
        'regime': None,
        'last_update': None,
        'errors': [],
        'warnings': []
    }
    
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
            recent_lines = lines[-lines_to_read:] if len(lines) > lines_to_read else lines
            
        for line in recent_lines:
            # Extract price
            price_match = re.search(r'Price:\s*([\d.]+)', line)
            if price_match:
                signals['price'] = float(price_match.group(1))
                signals['last_update'] = line.split(' - ')[0] if ' - ' in line else None
            
            # Extract BUY signal
            buy_match = re.search(r'BUY:\s*([\d.]+)', line)
            if buy_match:
                signals['buy_signal'] = float(buy_match.group(1))
            
            # Extract SELL signal
            sell_match = re.search(r'SELL:\s*([\d.]+)', line)
            if sell_match:
                signals['sell_signal'] = float(sell_match.group(1))
            
            # Extract RSI
            rsi_match = re.search(r'RSI:\s*([\d.]+)', line)
            if rsi_match:
                signals['rsi'] = float(rsi_match.group(1))
            
            # Extract ADX
            adx_match = re.search(r'ADX:\s*([\d.]+)', line)
            if adx_match:
                signals['adx'] = float(adx_match.group(1))
            
            # Extract ATR
            atr_match = re.search(r'ATR:\s*([\d.]+)', line)
            if atr_match:
                signals['atr'] = float(adx_match.group(1))
            
            # Extract regime
            regime_match = re.search(r'Regime:\s*(\w+)', line)
            if regime_match:
                signals['regime'] = regime_match.group(1)
            
            # Extract errors
            if 'ERROR' in line:
                signals['errors'].append(line.strip())
            
            # Extract warnings
            if 'WARNING' in line:
                signals['warnings'].append(line.strip())
    
    except Exception as e:
        signals['error'] = str(e)
    
    return signals

def analyze_with_clawdbot(strategy_name, signals, symbol="GOLDM05FEB26FUT"):
    """Use Clawdbot CLI to analyze trading signals"""
    if not CLAWDBOT_AVAILABLE:
        return None
    
    try:
        import subprocess
        
        # Prepare analysis prompt
        prompt = f"""Analyze the live trading signals for {strategy_name} trading {symbol}:

Current Price: {signals.get('price', 'N/A')}
BUY Signal: {signals.get('buy_signal', 'N/A')}/100
SELL Signal: {signals.get('sell_signal', 'N/A')}/100
RSI: {signals.get('rsi', 'N/A')}
ADX: {signals.get('adx', 'N/A')}
ATR: {signals.get('atr', 'N/A')}
Market Regime: {signals.get('regime', 'N/A')}

Recent Errors: {len(signals.get('errors', []))}
Recent Warnings: {len(signals.get('warnings', []))}

Provide:
1. Signal strength assessment (STRONG/MODERATE/WEAK)
2. Trading recommendation (BUY/SELL/HOLD)
3. Risk level (LOW/MEDIUM/HIGH)
4. Key insights
5. Action items

Format as JSON with keys: signal_strength, recommendation, risk_level, insights, actions"""
        
        # Try using Clawdbot CLI via gateway (requires API key configured)
        # Pass through environment variables including API keys
        env = dict(os.environ)
        
        # Ensure OPENAI_API_KEY is available (from environment or .env file)
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            env["OPENAI_API_KEY"] = openai_key
            logger.debug("Using OPENAI_API_KEY from environment")
        
        # Also check for ANTHROPIC_API_KEY
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            env["ANTHROPIC_API_KEY"] = anthropic_key
            logger.debug("Using ANTHROPIC_API_KEY from environment")
        
        result = subprocess.run(
            [
                "clawdbot", "agent",
                "--message", prompt,
                "--session-id", "live-trading-monitor",
                "--json"
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env  # Pass through environment variables including API keys
        )
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                response = json.loads(result.stdout)
                logger.info("Clawdbot AI analysis successful")
                return response
            except json.JSONDecodeError:
                # If not JSON, return the text output
                logger.info("Clawdbot returned non-JSON response")
                return {"response": result.stdout.strip()}
        else:
            # Check error details
            error_output = result.stderr if result.stderr else result.stdout
            if "API key" in error_output or "auth" in error_output.lower() or "No API key" in error_output:
                logger.warning("Clawdbot requires API key configuration. Skipping AI analysis.")
                logger.debug(f"Error details: {error_output[:200]}")
                return {"error": "API key not configured", "message": "Configure OPENAI_API_KEY or ANTHROPIC_API_KEY"}
            else:
                # Return error details for debugging
                error_msg = error_output[:200] if error_output else "Unknown error"
                logger.warning(f"Clawdbot CLI error: {error_msg}")
                return {"error": error_msg}
                
    except subprocess.TimeoutExpired:
        return {"error": "Clawdbot CLI timeout"}
    except FileNotFoundError:
        return {"error": "Clawdbot CLI not found in PATH"}
    except Exception as e:
        return {"error": str(e)}

def send_clawdbot_alert(message, priority="info"):
    """Send alert via Clawdbot CLI"""
    if not CLAWDBOT_AVAILABLE:
        print(f"[{priority.upper()}] {message}")
        return False
    
    try:
        import subprocess
        
        # Use Clawdbot CLI to send message
        # Priority can be included in the message
        alert_message = f"[{priority.upper()}] {message}"
        
        result = subprocess.run(
            [
                "clawdbot", "message",
                "--text", alert_message,
                "--channel", "telegram"  # or "whatsapp" based on config
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        return result.returncode == 0
    except Exception as e:
        print(f"Alert error: {e}")
        return False

def monitor_live_trading():
    """Main monitoring loop"""
    # #region agent log
    debug_log("H3", "monitor_live_trading_clawdbot.py:179", "Monitor function started", {"clawdbot_available": CLAWDBOT_AVAILABLE})
    # #endregion
    print("=" * 70)
    print("MCX Live Trading Monitor with Clawdbot AI")
    print("=" * 70)
    print(f"Started at: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S IST')}")
    sys.stdout.flush()  # Force flush output
    print()
    
    if not CLAWDBOT_AVAILABLE:
        # #region agent log
        debug_log("H3", "monitor_live_trading_clawdbot.py:188", "Clawdbot not available, continuing in basic mode")
        # #endregion
        print("⚠️  Clawdbot not available - monitoring without AI analysis")
        print("   (Basic monitoring will continue)")
        print()
        sys.stdout.flush()
    
    last_signals = {}
    alert_cooldown = {}  # Track when we last sent alerts
    
    try:
        loop_count = 0
        while True:
            loop_count += 1
            # #region agent log
            debug_log("H4", "monitor_live_trading_clawdbot.py:199", "Monitoring loop iteration", {"loop_count": loop_count})
            # #endregion
            ist_now = datetime.now(pytz.timezone('Asia/Kolkata'))
            print(f"\n[{ist_now.strftime('%H:%M:%S IST')}] Monitoring MCX Strategies...")
            sys.stdout.flush()
            
            # #region agent log
            debug_log("H4", "monitor_live_trading_clawdbot.py:204", "Getting MCX logs")
            # #endregion
            mcx_logs = get_latest_mcx_logs()
            # #region agent log
            debug_log("H4", "monitor_live_trading_clawdbot.py:206", "MCX logs retrieved", {"count": len(mcx_logs)})
            # #endregion
            
            if not mcx_logs:
                # #region agent log
                debug_log("H4", "monitor_live_trading_clawdbot.py:209", "No MCX log files found")
                # #endregion
                print("  No MCX log files found")
                sys.stdout.flush()
                time.sleep(60)
                continue
            
            current_signals = {}
            summary = []
            
            # #region agent log
            debug_log("H4", "monitor_live_trading_clawdbot.py:218", "Processing strategies", {"strategy_count": len(mcx_logs)})
            # #endregion
            for strategy_key, log_file in mcx_logs.items():
                # #region agent log
                debug_log("H4", "monitor_live_trading_clawdbot.py:221", "Extracting signals", {"strategy_key": strategy_key, "log_file": str(log_file)})
                # #endregion
                signals = extract_latest_signals(log_file)
                # #region agent log
                debug_log("H4", "monitor_live_trading_clawdbot.py:224", "Signals extracted", {"has_price": signals.get('price') is not None, "has_buy": signals.get('buy_signal') is not None})
                # #endregion
                current_signals[strategy_key] = signals
                
                strategy_name = log_file.stem.split('_')[0:3]
                strategy_display = ' '.join(strategy_name).title()
                
                # Display current status
                status_line = f"  {strategy_display}:"
                if signals.get('price'):
                    status_line += f" Price ₹{signals['price']:,.0f}"
                if signals.get('buy_signal') is not None:
                    status_line += f" | BUY: {signals['buy_signal']:.1f}/100"
                if signals.get('sell_signal') is not None:
                    status_line += f" | SELL: {signals['sell_signal']:.1f}/100"
                if signals.get('regime'):
                    status_line += f" | Regime: {signals['regime']}"
                
                print(status_line)
                sys.stdout.flush()
                
                # Check for significant changes
                if strategy_key in last_signals:
                    # #region agent log
                    debug_log("H5", "monitor_live_trading_clawdbot.py:234", "Checking signal changes", {"strategy_key": strategy_key})
                    # #endregion
                    last = last_signals[strategy_key]
                    
                    # Alert on strong signals (handle None values)
                    current_buy = signals.get('buy_signal') or 0
                    last_buy = last.get('buy_signal') or 0
                    current_sell = signals.get('sell_signal') or 0
                    last_sell = last.get('sell_signal') or 0
                    
                    if current_buy >= 75 and last_buy < 75:
                        alert_msg = f"🚀 {strategy_display}: Strong BUY signal detected! Signal: {current_buy:.1f}/100, Price: ₹{signals.get('price', 0):,.0f}"
                        print(f"    ⚠️  {alert_msg}")
                        send_clawdbot_alert(alert_msg, "high")
                    
                    if current_sell >= 75 and last_sell < 75:
                        alert_msg = f"📉 {strategy_display}: Strong SELL signal detected! Signal: {current_sell:.1f}/100, Price: ₹{signals.get('price', 0):,.0f}"
                        print(f"    ⚠️  {alert_msg}")
                        send_clawdbot_alert(alert_msg, "high")
                    
                    # Alert on errors
                    if len(signals.get('errors', [])) > len(last.get('errors', [])):
                        new_errors = len(signals.get('errors', [])) - len(last.get('errors', []))
                        alert_msg = f"⚠️  {strategy_display}: {new_errors} new error(s) detected"
                        print(f"    ⚠️  {alert_msg}")
                        send_clawdbot_alert(alert_msg, "warning")
                
                # AI Analysis (every 5 minutes) - only if Clawdbot is available
                if CLAWDBOT_AVAILABLE and (strategy_key not in alert_cooldown or (time.time() - alert_cooldown.get(strategy_key, 0) > 300)):
                    # #region agent log
                    debug_log("H6", "monitor_live_trading_clawdbot.py:260", "Attempting Clawdbot AI analysis", {"strategy_key": strategy_key})
                    # #endregion
                    try:
                        analysis = analyze_with_clawdbot(strategy_display, signals)
                        # #region agent log
                        debug_log("H6", "monitor_live_trading_clawdbot.py:264", "AI analysis result", {"has_analysis": analysis is not None, "has_error": analysis and 'error' in analysis if analysis else False})
                        # #endregion
                        if analysis and 'error' not in analysis:
                            print(f"    🤖 AI Analysis: {json.dumps(analysis, indent=2)}")
                            sys.stdout.flush()
                            alert_cooldown[strategy_key] = time.time()
                    except Exception as e:
                        # #region agent log
                        debug_log("H6", "monitor_live_trading_clawdbot.py:270", "Exception during AI analysis", {"error": str(e)})
                        # #endregion
                        pass
            
            last_signals = current_signals
            # #region agent log
            debug_log("H4", "monitor_live_trading_clawdbot.py:275", "Loop iteration complete, sleeping", {"loop_count": loop_count})
            # #endregion
            
            # Wait before next check
            time.sleep(60)  # Check every minute
            
    except KeyboardInterrupt:
        # #region agent log
        debug_log("H3", "monitor_live_trading_clawdbot.py:281", "Keyboard interrupt received")
        # #endregion
        print("\n\nMonitoring stopped by user")
        sys.stdout.flush()
    except Exception as e:
        # #region agent log
        debug_log("H3", "monitor_live_trading_clawdbot.py:285", "Exception in monitoring loop", {"error": str(e), "type": type(e).__name__})
        # #endregion
        print(f"\n\nError in monitoring: {e}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()

if __name__ == "__main__":
    monitor_live_trading()
