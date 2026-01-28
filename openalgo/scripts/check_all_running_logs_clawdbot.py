#!/usr/bin/env python3
"""
Check All Running Strategy Logs using Clawdbot AI
Analyzes logs from all currently running strategies
"""
import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Add services to path
services_path = Path(__file__).parent.parent / 'services'
if str(services_path) not in sys.path:
    sys.path.insert(0, str(services_path))

try:
    from clawdbot_bridge_service import get_bridge_service
    CLAWDBOT_AVAILABLE = True
except ImportError:
    print("⚠️  Warning: Clawdbot bridge service not available")
    print("   Install Clawdbot or check service configuration")
    CLAWDBOT_AVAILABLE = False

CONFIG_FILE = Path(__file__).parent.parent / "strategies" / "strategy_configs.json"
LOG_DIR = Path(__file__).parent.parent / "log" / "strategies"

def load_running_strategies():
    """Load all running strategies from config"""
    if not CONFIG_FILE.exists():
        return []
    
    with open(CONFIG_FILE, 'r') as f:
        configs = json.load(f)
    
    running = []
    for strategy_id, config in configs.items():
        if config.get('is_running'):
            running.append({
                'id': strategy_id,
                'name': config.get('name', strategy_id),
                'file': config.get('file_path', ''),
                'pid': config.get('pid')
            })
    
    return running

def find_strategy_log_file(strategy_id, strategy_name):
    """Find log file for a strategy"""
    if not LOG_DIR.exists():
        return None
    
    # Try multiple patterns
    patterns = [
        f"{strategy_id}_*.log",
        f"{strategy_id}*.log",
        f"*{strategy_id}*.log",
    ]
    
    # Also try by name
    name_parts = strategy_name.lower().replace('_', '*').replace('-', '*')
    patterns.extend([
        f"*{name_parts}*.log",
        f"{name_parts}*.log",
    ])
    
    # Try to match by file path
    for pattern in patterns:
        matches = list(LOG_DIR.glob(pattern))
        if matches:
            # Return most recent
            return max(matches, key=lambda p: p.stat().st_mtime)
    
    # Try to find any recent log file
    all_logs = list(LOG_DIR.glob("*.log"))
    if all_logs:
        # Return most recent
        return max(all_logs, key=lambda p: p.stat().st_mtime)
    
    return None

def extract_log_summary(log_file: Path, max_lines=500) -> dict:
    """Extract key information from log file"""
    summary = {
        "file": str(log_file.name),
        "size": log_file.stat().st_size if log_file.exists() else 0,
        "modified": datetime.fromtimestamp(log_file.stat().st_mtime).isoformat() if log_file.exists() else None,
        "errors": [],
        "warnings": [],
        "signals": [],
        "trades": [],
        "api_errors": defaultdict(int),
        "last_price": None,
        "last_signals": {},
        "recent_lines": []
    }
    
    if not log_file.exists():
        summary["error"] = "Log file not found"
        return summary
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        # Get recent lines
        recent_lines = lines[-max_lines:] if len(lines) > max_lines else lines
        summary["recent_lines"] = [line.strip() for line in recent_lines[-50:]]  # Last 50 lines
        
        for line in recent_lines:
            # Extract errors
            if 'ERROR' in line.upper() or 'Error' in line:
                summary["errors"].append(line.strip())
                # Count API errors
                if 'HTTP' in line or '403' in line or '400' in line or '500' in line:
                    if '500' in line:
                        summary["api_errors"]["500"] += 1
                    elif '400' in line:
                        summary["api_errors"]["400"] += 1
                    elif '403' in line:
                        summary["api_errors"]["403"] += 1
                    elif '429' in line:
                        summary["api_errors"]["429"] += 1
            
            # Extract warnings
            if 'WARNING' in line.upper() or 'Warning' in line:
                summary["warnings"].append(line.strip())
            
            # Extract signals
            if 'BUY:' in line.upper() or 'SELL:' in line.upper() or 'SIGNAL' in line.upper():
                summary["signals"].append(line.strip())
                # Extract signal details
                buy_match = re.search(r'BUY[:\s]+([\d.]+)', line, re.IGNORECASE)
                if buy_match:
                    summary["last_signals"]["BUY"] = float(buy_match.group(1))
                sell_match = re.search(r'SELL[:\s]+([\d.]+)', line, re.IGNORECASE)
                if sell_match:
                    summary["last_signals"]["SELL"] = float(sell_match.group(1))
            
            # Extract price
            price_match = re.search(r'(?:Price|price|PRICE)[:\s]+([\d.]+)', line)
            if price_match:
                summary["last_price"] = float(price_match.group(1))
            
            # Extract trades/orders
            if any(keyword in line.lower() for keyword in ['order', 'trade', 'placed', 'executed', 'filled']):
                summary["trades"].append(line.strip())
    
    except Exception as e:
        summary["error"] = str(e)
    
    return summary

def analyze_with_clawdbot(summary: dict, strategy_name: str) -> dict:
    """Use Clawdbot to analyze log summary"""
    if not CLAWDBOT_AVAILABLE:
        return {"error": "Clawdbot not available"}
    
    try:
        bridge = get_bridge_service()
        
        # Prepare comprehensive analysis prompt
        recent_errors = summary.get('errors', [])[-5:]
        recent_warnings = summary.get('warnings', [])[-5:]
        recent_signals = summary.get('signals', [])[-5:]
        recent_trades = summary.get('trades', [])[-5:]
        recent_lines = summary.get('recent_lines', [])[-20:]
        
        prompt = f"""
Analyze the following trading strategy log for {strategy_name}:

File: {summary.get('file', 'unknown')}
Last Modified: {summary.get('modified', 'N/A')}
File Size: {summary.get('size', 0)} bytes

=== ERROR SUMMARY ===
Total Errors: {len(summary.get('errors', []))}
- HTTP 500 errors: {summary.get('api_errors', {}).get('500', 0)}
- HTTP 400 errors: {summary.get('api_errors', {}).get('400', 0)}
- HTTP 403 errors: {summary.get('api_errors', {}).get('403', 0)}
- HTTP 429 errors: {summary.get('api_errors', {}).get('429', 0)}

Recent Errors:
{chr(10).join(recent_errors) if recent_errors else 'None'}

=== WARNING SUMMARY ===
Total Warnings: {len(summary.get('warnings', []))}
Recent Warnings:
{chr(10).join(recent_warnings) if recent_warnings else 'None'}

=== SIGNAL SUMMARY ===
Total Signals: {len(summary.get('signals', []))}
Last Signals:
- BUY: {summary.get('last_signals', {}).get('BUY', 'N/A')}
- SELL: {summary.get('last_signals', {}).get('SELL', 'N/A')}

Recent Signals:
{chr(10).join(recent_signals) if recent_signals else 'None'}

=== TRADE SUMMARY ===
Total Trades/Orders: {len(summary.get('trades', []))}
Recent Trades:
{chr(10).join(recent_trades) if recent_trades else 'None'}

=== RECENT ACTIVITY (Last 20 lines) ===
{chr(10).join(recent_lines) if recent_lines else 'No recent activity'}

=== ANALYSIS REQUEST ===
Please provide a comprehensive analysis:

1. **Overall Health Status**: HEALTHY / WARNING / CRITICAL
2. **Key Issues**: List any critical problems, errors, or anomalies
3. **Performance Assessment**: Evaluate signal quality, trade execution, and strategy behavior
4. **Risk Assessment**: Identify any risk management concerns
5. **Recommendations**: Specific actionable recommendations to improve strategy performance
6. **Action Items**: Priority list of things to fix or investigate

Format your response as JSON with keys: status, issues, performance, risk, recommendations, actions
"""
        
        # Use async bridge call
        import asyncio
        result = asyncio.run(bridge._send_ws_message("agent.send", {
            "message": prompt,
            "session": f"log-analysis-{strategy_name}"
        }))
        
        # Handle different response formats from Clawdbot
        analysis_result = {}
        if isinstance(result, dict):
            if "response" in result:
                analysis_result = result["response"]
            elif "payload" in result:
                payload = result.get("payload", {})
                if isinstance(payload, dict) and "response" in payload:
                    analysis_result = payload["response"]
                elif isinstance(payload, str):
                    try:
                        analysis_result = json.loads(payload)
                    except:
                        analysis_result = {"raw_response": payload}
            elif "event" in result:
                analysis_result = result.get("payload", {})
            else:
                analysis_result = result
        
        return {
            "analysis": analysis_result,
            "raw_response": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e), "exception": str(e)}

def main():
    print("=" * 80)
    print("  CHECK ALL RUNNING STRATEGY LOGS WITH CLAWDBOT")
    print("=" * 80)
    print()
    
    # Load running strategies
    running_strategies = load_running_strategies()
    
    if not running_strategies:
        print("❌ No running strategies found!")
        return
    
    print(f"📊 Found {len(running_strategies)} running strategies\n")
    
    # Analyze each strategy
    all_results = {}
    
    for strategy in running_strategies:
        strategy_id = strategy['id']
        strategy_name = strategy['name']
        pid = strategy.get('pid')
        
        print(f"{'='*80}")
        print(f"Strategy: {strategy_name}")
        print(f"  ID: {strategy_id}")
        print(f"  PID: {pid}")
        print(f"{'='*80}")
        
        # Find log file
        log_file = find_strategy_log_file(strategy_id, strategy_name)
        
        if not log_file:
            print(f"  ⚠️  No log file found")
            all_results[strategy_name] = {"error": "No log file found"}
            print()
            continue
        
        print(f"  📄 Log: {log_file.name}")
        
        # Extract summary
        print("  📊 Extracting log summary...")
        summary = extract_log_summary(log_file)
        
        print(f"    - Errors: {len(summary.get('errors', []))}")
        print(f"    - Warnings: {len(summary.get('warnings', []))}")
        print(f"    - Signals: {len(summary.get('signals', []))}")
        print(f"    - Trades: {len(summary.get('trades', []))}")
        if summary.get('api_errors'):
            print(f"    - API Errors: {dict(summary['api_errors'])}")
        if summary.get('last_price'):
            print(f"    - Last Price: {summary['last_price']}")
        
        # Analyze with Clawdbot
        if CLAWDBOT_AVAILABLE:
            print("  🤖 Analyzing with Clawdbot AI...")
            analysis = analyze_with_clawdbot(summary, strategy_name)
            
            if "error" in analysis:
                print(f"    ❌ Error: {analysis['error']}")
            else:
                print("    ✅ Analysis complete")
                
                # Display analysis results
                if "analysis" in analysis:
                    analysis_data = analysis["analysis"]
                    if isinstance(analysis_data, dict):
                        if "status" in analysis_data:
                            status = analysis_data["status"]
                            status_emoji = "✅" if status == "HEALTHY" else "⚠️" if status == "WARNING" else "❌"
                            print(f"\n    {status_emoji} Status: {status}")
                        
                        if "issues" in analysis_data:
                            issues = analysis_data["issues"]
                            if issues:
                                print(f"\n    🔍 Issues:")
                                if isinstance(issues, list):
                                    for issue in issues[:3]:
                                        print(f"      - {issue}")
                                elif isinstance(issues, str):
                                    print(f"      - {issues}")
                        
                        if "recommendations" in analysis_data:
                            recs = analysis_data["recommendations"]
                            if recs:
                                print(f"\n    💡 Recommendations:")
                                if isinstance(recs, list):
                                    for rec in recs[:3]:
                                        print(f"      - {rec}")
                                elif isinstance(recs, str):
                                    print(f"      - {recs}")
            
            all_results[strategy_name] = {
                "summary": summary,
                "analysis": analysis
            }
        else:
            all_results[strategy_name] = {
                "summary": summary,
                "analysis": {"error": "Clawdbot not available"}
            }
        
        print()
    
    # Summary
    print("=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    print()
    
    for strategy_name, result in all_results.items():
        summary = result.get("summary", {})
        analysis = result.get("analysis", {})
        
        status = "❓"
        if "analysis" in analysis and isinstance(analysis["analysis"], dict):
            status_val = analysis["analysis"].get("status", "UNKNOWN")
            status = "✅" if status_val == "HEALTHY" else "⚠️" if status_val == "WARNING" else "❌"
        
        error_count = len(summary.get("errors", []))
        warning_count = len(summary.get("warnings", []))
        
        print(f"{status} {strategy_name}")
        print(f"   Errors: {error_count} | Warnings: {warning_count} | Signals: {len(summary.get('signals', []))}")
    
    print()
    print("=" * 80)
    print("✅ Analysis complete!")
    print("=" * 80)

if __name__ == "__main__":
    main()
