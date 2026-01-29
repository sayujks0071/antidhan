#!/usr/bin/env python3
"""
Monitor MCX Strategy Logs using Clawdbot AI
Continuously monitors running MCX strategies and provides AI-powered analysis
"""
import os
import sys
import time
import json
import subprocess
import logging
from pathlib import Path
from datetime import datetime
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MCXLogMonitor")

def get_latest_logs(strategy_pattern="mcx_*.log", lines=50):
    """Get latest log entries from MCX strategies"""
    log_dir = Path(__file__).parent.parent / "log" / "strategies"
    if not log_dir.exists():
        return ""
    
    all_logs = []
    for log_file in sorted(log_dir.glob(strategy_pattern), key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
        try:
            with open(log_file, 'r') as f:
                log_lines = f.readlines()
                recent_lines = log_lines[-lines:] if len(log_lines) > lines else log_lines
                all_logs.append(f"\n=== {log_file.name} ===\n")
                all_logs.extend(recent_lines)
        except Exception as e:
            logger.warning(f"Error reading {log_file}: {e}")
    
    return "".join(all_logs)

def analyze_with_clawdbot(log_content):
    """Use Clawdbot to analyze logs"""
    if not log_content.strip():
        return None
    
    prompt = f"""Analyze these MCX trading strategy logs and provide insights:

{log_content[:5000]}  # Limit to 5000 chars

Please provide:
1. Strategy performance assessment
2. Signal quality analysis (BUY/SELL scores, thresholds)
3. Risk management evaluation
4. Any anomalies or issues detected
5. Recommendations for improvement

Format your response as JSON with keys: assessment, signal_quality, risk_management, anomalies, recommendations"""
    
    try:
        env = dict(os.environ)
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            env["OPENAI_API_KEY"] = openai_key
        
        result = subprocess.run(
            ["clawdbot", "agent", "--message", prompt, "--session-id", "mcx-log-monitor", "--json"],
            capture_output=True, text=True, timeout=30, env=env
        )
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"response": result.stdout.strip()}
        else:
            error_output = result.stderr if result.stderr else result.stdout
            logger.warning(f"Clawdbot analysis failed: {error_output[:200]}")
            return None
    except subprocess.TimeoutExpired:
        logger.warning("Clawdbot analysis timed out")
        return None
    except FileNotFoundError:
        logger.error("Clawdbot CLI not found")
        return None
    except Exception as e:
        logger.error(f"Error calling Clawdbot: {e}")
        return None

def send_clawdbot_alert(message, priority="info"):
    """Send alert via Clawdbot"""
    try:
        alert_message = f"[{priority.upper()}] MCX Monitor: {message}"
        result = subprocess.run(
            ["clawdbot", "message", "--text", alert_message, "--channel", "telegram"],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception as e:
        logger.debug(f"Alert error: {e}")
        return False

def extract_key_metrics(log_content):
    """Extract key metrics from logs"""
    metrics = {
        "signals": [],
        "orders": [],
        "errors": [],
        "regime_changes": []
    }
    
    for line in log_content.split('\n'):
        if "BUY:" in line or "SELL:" in line:
            metrics["signals"].append(line.strip())
        if "Order placed" in line or "Order Placed" in line:
            metrics["orders"].append(line.strip())
        if "ERROR" in line or "Error" in line:
            metrics["errors"].append(line.strip())
        if "Regime:" in line and "→" in line:
            metrics["regime_changes"].append(line.strip())
    
    return metrics

def main():
    """Main monitoring loop"""
    logger.info("🚀 Starting MCX Log Monitor with Clawdbot AI")
    logger.info("   Monitoring all MCX strategies...")
    
    last_analysis_time = 0
    analysis_interval = 300  # Analyze every 5 minutes
    
    while True:
        try:
            ist = pytz.timezone('Asia/Kolkata')
            now = datetime.now(ist)
            current_time = now.time()
            
            # Get latest logs
            log_content = get_latest_logs()
            
            if log_content:
                # Extract metrics
                metrics = extract_key_metrics(log_content)
                
                # Print current status
                print(f"\n{'='*70}")
                print(f"📊 MCX Strategy Monitor - {now.strftime('%Y-%m-%d %H:%M:%S IST')}")
                print(f"{'='*70}")
                
                if metrics["signals"]:
                    print(f"\n📈 Recent Signals ({len(metrics['signals'])}):")
                    for signal in metrics["signals"][-5:]:
                        print(f"   {signal}")
                
                if metrics["orders"]:
                    print(f"\n✅ Recent Orders ({len(metrics['orders'])}):")
                    for order in metrics["orders"][-3:]:
                        print(f"   {order}")
                
                if metrics["errors"]:
                    print(f"\n⚠️  Errors ({len(metrics['errors'])}):")
                    for error in metrics["errors"][-3:]:
                        print(f"   {error}")
                
                if metrics["regime_changes"]:
                    print(f"\n🌐 Regime Changes ({len(metrics['regime_changes'])}):")
                    for change in metrics["regime_changes"][-3:]:
                        print(f"   {change}")
                
                # AI Analysis (every 5 minutes)
                if time.time() - last_analysis_time >= analysis_interval:
                    print(f"\n🤖 Running Clawdbot AI Analysis...")
                    analysis = analyze_with_clawdbot(log_content)
                    
                    if analysis:
                        print(f"\n{'='*70}")
                        print("🤖 Clawdbot AI Analysis:")
                        print(f"{'='*70}")
                        
                        if isinstance(analysis, dict):
                            if "response" in analysis:
                                print(analysis["response"])
                            else:
                                for key, value in analysis.items():
                                    if isinstance(value, str):
                                        print(f"\n{key.upper()}:")
                                        print(f"   {value}")
                                    elif isinstance(value, dict):
                                        print(f"\n{key.upper()}:")
                                        for k, v in value.items():
                                            print(f"   {k}: {v}")
                        else:
                            print(json.dumps(analysis, indent=2))
                        
                        # Send alerts for critical issues
                        if metrics["errors"]:
                            send_clawdbot_alert(f"Errors detected in MCX strategies: {len(metrics['errors'])} errors", "warning")
                    
                    last_analysis_time = time.time()
                
                print(f"\n{'='*70}\n")
            
            # Wait before next check
            time.sleep(30)
            
        except KeyboardInterrupt:
            logger.info("Monitor stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in monitor loop: {e}", exc_info=True)
            time.sleep(60)

if __name__ == "__main__":
    main()
