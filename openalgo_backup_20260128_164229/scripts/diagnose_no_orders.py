#!/usr/bin/env python3
"""
Diagnose why strategies aren't placing orders
Analyzes logs to identify which entry conditions are failing
"""
import re
from pathlib import Path
from collections import defaultdict

LOG_DIR = Path(__file__).parent.parent / "log" / "strategies"

def analyze_entry_conditions(log_file):
    """Analyze entry conditions from log file"""
    if not log_file.exists():
        return None
    
    conditions_analysis = {
        "total_checks": 0,
        "conditions_met": defaultdict(int),
        "conditions_failed": defaultdict(int),
        "orders_placed": 0,
        "recent_conditions": []
    }
    
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    for line in lines[-500:]:  # Last 500 lines
        # Check for entry conditions log
        if "Entry Conditions" in line:
            conditions_analysis["total_checks"] += 1
            
            # Extract condition statuses
            conditions = {}
            if "Multi-TF Consensus: ✅" in line:
                conditions["Multi-TF Consensus"] = True
            elif "Multi-TF Consensus: ❌" in line:
                conditions["Multi-TF Consensus"] = False
            
            if "RSI Momentum: ✅" in line:
                conditions["RSI Momentum"] = True
            elif "RSI Momentum: ❌" in line:
                conditions["RSI Momentum"] = False
            
            if "MACD Bullish: ✅" in line:
                conditions["MACD Bullish"] = True
            elif "MACD Bullish: ❌" in line:
                conditions["MACD Bullish"] = False
            
            if "ADX Trend: ✅" in line:
                conditions["ADX Trend"] = True
            elif "ADX Trend: ❌" in line:
                conditions["ADX Trend"] = False
            
            if "Above VWAP: ✅" in line:
                conditions["Above VWAP"] = True
            elif "Above VWAP: ❌" in line:
                conditions["Above VWAP"] = False
            
            if "Volume Confirmation: ✅" in line:
                conditions["Volume Confirmation"] = True
            elif "Volume Confirmation: ❌" in line:
                conditions["Volume Confirmation"] = False
            
            # Track which conditions pass/fail
            for cond, status in conditions.items():
                if status:
                    conditions_analysis["conditions_met"][cond] += 1
                else:
                    conditions_analysis["conditions_failed"][cond] += 1
            
            # Store recent conditions
            if len(conditions_analysis["recent_conditions"]) < 5:
                conditions_analysis["recent_conditions"].append(conditions)
        
        # Check for orders placed
        if "order placed" in line.lower() or "Entry order placed" in line:
            conditions_analysis["orders_placed"] += 1
    
    return conditions_analysis

def main():
    print("=" * 80)
    print("  DIAGNOSE: Why No Orders Are Being Placed")
    print("=" * 80)
    print()
    
    # Find strategy log files
    log_files = list(LOG_DIR.glob("*multi_timeframe*.log")) + \
                list(LOG_DIR.glob("*mcx_advanced_momentum*.log"))
    
    if not log_files:
        print("❌ No relevant log files found")
        return
    
    # Analyze each log file
    for log_file in sorted(log_files, key=lambda x: x.stat().st_mtime, reverse=True)[:3]:
        print(f"📄 Analyzing: {log_file.name}")
        print("-" * 80)
        
        analysis = analyze_entry_conditions(log_file)
        
        if not analysis:
            print("  ⚠️  Could not analyze log file")
            continue
        
        print(f"  Total Entry Condition Checks: {analysis['total_checks']}")
        print(f"  Orders Placed: {analysis['orders_placed']}")
        print()
        
        if analysis['total_checks'] > 0:
            print("  Condition Success Rate:")
            all_conditions = set(list(analysis['conditions_met'].keys()) + 
                                list(analysis['conditions_failed'].keys()))
            
            for cond in sorted(all_conditions):
                met = analysis['conditions_met'].get(cond, 0)
                failed = analysis['conditions_failed'].get(cond, 0)
                total = met + failed
                if total > 0:
                    success_rate = (met / total) * 100
                    status = "✅" if success_rate > 80 else "⚠️" if success_rate > 50 else "❌"
                    print(f"    {status} {cond}: {success_rate:.1f}% ({met}/{total})")
            
            print()
            print("  Most Common Failures:")
            failures = sorted(analysis['conditions_failed'].items(), 
                            key=lambda x: x[1], reverse=True)
            for cond, count in failures[:3]:
                print(f"    ❌ {cond}: Failed {count} times")
        
        print()
    
    print("=" * 80)
    print("  RECOMMENDATIONS")
    print("=" * 80)
    print()
    print("1. If MACD Bullish is consistently failing:")
    print("   - Consider relaxing MACD condition (accept weak bullish)")
    print("   - Or make MACD optional (use OR instead of AND)")
    print()
    print("2. If Volume Confirmation is consistently failing:")
    print("   - Lower volume threshold from 1.2x to 1.0x")
    print("   - Or make volume optional for trending markets")
    print()
    print("3. If multiple conditions are failing:")
    print("   - Switch to signal scoring system (4/6 conditions instead of all)")
    print("   - Or relax entry requirements based on market regime")
    print()
    print("4. Check if strategies are in paper trading mode:")
    print("   - Verify order placement API calls are being made")
    print("   - Check broker connectivity and authentication")
    print()

if __name__ == "__main__":
    main()
