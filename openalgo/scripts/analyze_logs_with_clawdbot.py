#!/usr/bin/env python3
"""
Analyze MCX Trading Logs with Clawdbot AI
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
    print("Warning: Clawdbot bridge service not available")
    CLAWDBOT_AVAILABLE = False

def extract_log_summary(log_file: Path) -> dict:
    """Extract key information from log file"""
    summary = {
        "file": str(log_file.name),
        "errors": [],
        "warnings": [],
        "signals": [],
        "trades": [],
        "api_errors": defaultdict(int),
        "last_price": None,
        "last_signals": {}
    }
    
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
            
        for line in lines[-200:]:  # Last 200 lines
            # Extract errors
            if 'ERROR' in line:
                summary["errors"].append(line.strip())
                # Count API errors
                if 'HTTP' in line:
                    if '500' in line:
                        summary["api_errors"]["500"] += 1
                    elif '400' in line:
                        summary["api_errors"]["400"] += 1
                    elif '403' in line:
                        summary["api_errors"]["403"] += 1
            
            # Extract warnings
            if 'WARNING' in line:
                summary["warnings"].append(line.strip())
            
            # Extract signals
            if 'BUY:' in line or 'SELL:' in line:
                summary["signals"].append(line.strip())
                # Extract signal details
                if 'BUY:' in line:
                    buy_match = re.search(r'BUY:\s*([\d.]+)', line)
                    if buy_match:
                        summary["last_signals"]["BUY"] = float(buy_match.group(1))
                if 'SELL:' in line:
                    sell_match = re.search(r'SELL:\s*([\d.]+)', line)
                    if sell_match:
                        summary["last_signals"]["SELL"] = float(sell_match.group(1))
            
            # Extract price
            price_match = re.search(r'Price:\s*([\d.]+)', line)
            if price_match:
                summary["last_price"] = float(price_match.group(1))
            
            # Extract trades/orders
            if 'order' in line.lower() or 'trade' in line.lower():
                if 'placed' in line.lower() or 'executed' in line.lower():
                    summary["trades"].append(line.strip())
    
    except Exception as e:
        summary["error"] = str(e)
    
    return summary

def analyze_with_clawdbot(summary: dict, symbol: str = "GOLD05FEB26FUT") -> dict:
    """Use Clawdbot to analyze log summary"""
    if not CLAWDBOT_AVAILABLE:
        return {"error": "Clawdbot not available"}
    
    try:
        bridge = get_bridge_service()
        
        # Prepare analysis prompt
        prompt = f"""
        Analyze the following MCX trading strategy log summary for {symbol}:
        
        File: {summary.get('file', 'unknown')}
        
        Recent Errors: {len(summary.get('errors', []))}
        - HTTP 500 errors: {summary.get('api_errors', {}).get('500', 0)}
        - HTTP 400 errors: {summary.get('api_errors', {}).get('400', 0)}
        - HTTP 403 errors: {summary.get('api_errors', {}).get('403', 0)}
        
        Recent Warnings: {len(summary.get('warnings', []))}
        
        Last Signals:
        - BUY: {summary.get('last_signals', {}).get('BUY', 'N/A')}
        - SELL: {summary.get('last_signals', {}).get('SELL', 'N/A')}
        
        Last Price: {summary.get('last_price', 'N/A')}
        
        Recent Errors (sample):
        {chr(10).join(summary.get('errors', [])[-5:])}
        
        Please provide:
        1. Overall health status (HEALTHY/WARNING/CRITICAL)
        2. Key issues identified
        3. Recommendations for improvement
        4. Signal quality assessment
        5. Action items
        
        Format as JSON with keys: status, issues, recommendations, signal_quality, actions
        """
        
        # Use async bridge call
        import asyncio
        result = asyncio.run(bridge._send_ws_message("agent.send", {
            "message": prompt,
            "session": "log-analysis"
        }))
        
        # Handle different response formats from Clawdbot
        analysis_result = {}
        if isinstance(result, dict):
            # Check for different possible response structures
            if "response" in result:
                analysis_result = result["response"]
            elif "payload" in result:
                # Handle event-based responses
                payload = result.get("payload", {})
                if isinstance(payload, dict) and "response" in payload:
                    analysis_result = payload["response"]
                elif isinstance(payload, str):
                    # Try to parse JSON string
                    try:
                        analysis_result = json.loads(payload)
                    except:
                        analysis_result = {"raw_response": payload}
            elif "event" in result:
                # Event-based response, extract payload
                analysis_result = result.get("payload", {})
            else:
                # Use the entire result if it looks like analysis
                analysis_result = result
        
        return {
            "analysis": analysis_result,
            "raw_response": result,  # Include raw for debugging
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}

def main():
    print("=" * 70)
    print("MCX Trading Logs Analysis with Clawdbot")
    print("=" * 70)
    
    # Find MCX log files
    log_dir = Path(__file__).parent.parent / "log" / "strategies"
    mcx_logs = list(log_dir.glob("*mcx*.log"))
    
    if not mcx_logs:
        print("No MCX log files found!")
        return
    
    print(f"\nFound {len(mcx_logs)} MCX log file(s):\n")
    
    all_summaries = {}
    for log_file in sorted(mcx_logs, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
        print(f"Analyzing: {log_file.name}")
        summary = extract_log_summary(log_file)
        all_summaries[log_file.name] = summary
        
        # Print quick summary
        print(f"  - Errors: {len(summary.get('errors', []))}")
        print(f"  - Warnings: {len(summary.get('warnings', []))}")
        print(f"  - Signals: {len(summary.get('signals', []))}")
        print(f"  - API Errors: {dict(summary.get('api_errors', {}))}")
        if summary.get('last_price'):
            print(f"  - Last Price: {summary['last_price']}")
        if summary.get('last_signals'):
            print(f"  - Last Signals: {summary['last_signals']}")
        print()
    
    # Analyze with Clawdbot
    if CLAWDBOT_AVAILABLE:
        print("\n" + "=" * 70)
        print("Clawdbot AI Analysis")
        print("=" * 70)
        
        # Get most recent log
        latest_log = sorted(mcx_logs, key=lambda x: x.stat().st_mtime, reverse=True)[0]
        latest_summary = all_summaries[latest_log.name]
        
        print(f"\nAnalyzing latest log: {latest_log.name}")
        analysis = analyze_with_clawdbot(latest_summary)
        
        if "error" in analysis:
            print(f"Error: {analysis['error']}")
        else:
            print("\nAI Analysis Results:")
            print(json.dumps(analysis, indent=2))
    else:
        print("\nClawdbot not available. Install and configure Clawdbot to enable AI analysis.")
    
    # Print detailed summary
    print("\n" + "=" * 70)
    print("Detailed Summary")
    print("=" * 70)
    
    for log_name, summary in all_summaries.items():
        print(f"\n{log_name}:")
        print(f"  Total Errors: {len(summary.get('errors', []))}")
        print(f"  Total Warnings: {len(summary.get('warnings', []))}")
        print(f"  Total Signals: {len(summary.get('signals', []))}")
        
        if summary.get('api_errors'):
            print(f"  API Error Breakdown:")
            for code, count in summary['api_errors'].items():
                print(f"    HTTP {code}: {count}")
        
        if summary.get('last_signals'):
            print(f"  Latest Signals:")
            for signal_type, value in summary['last_signals'].items():
                print(f"    {signal_type}: {value}")
        
        if summary.get('errors'):
            print(f"  Recent Errors (last 3):")
            for error in summary['errors'][-3:]:
                print(f"    - {error[:100]}")

if __name__ == "__main__":
    main()
