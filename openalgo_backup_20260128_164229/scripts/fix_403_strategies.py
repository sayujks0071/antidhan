#!/usr/bin/env python3
"""
Fix 403 errors for strategies by setting API key
"""
import json
import os
from pathlib import Path

API_KEY = "5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163"
CONFIG_FILE = Path(__file__).parent.parent / "strategies" / "strategy_configs.json"
ENV_FILE = Path(__file__).parent.parent / "strategies" / "strategy_env.json"

# Strategy IDs that need API key
STRATEGY_IDS = [
    "mcx_global_arbitrage_strategy_20260128110030",
    "natural_gas_clawdbot_strategy_20260128110030",
    "crude_oil_enhanced_strategy_20260128110030"
]

def set_api_keys():
    """Set API keys for strategies in strategy_env.json"""
    # Load existing env file
    if ENV_FILE.exists():
        with open(ENV_FILE, 'r') as f:
            env_data = json.load(f)
    else:
        env_data = {}
    
    # Set API key for each strategy
    for strategy_id in STRATEGY_IDS:
        if strategy_id not in env_data:
            env_data[strategy_id] = {}
        env_data[strategy_id]['OPENALGO_APIKEY'] = API_KEY
        print(f"✅ Set API key for: {strategy_id}")
    
    # Save updated env file
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ENV_FILE, 'w') as f:
        json.dump(env_data, f, indent=2)
    
    print(f"\n✅ API keys configured for {len(STRATEGY_IDS)} strategies")
    print(f"📁 Saved to: {ENV_FILE}")
    print("\n⚠️  Note: Restart the strategies for the API key to take effect")
    print("   Go to: http://127.0.0.1:5001/python")
    print("   Click 'Stop' then 'Start' on each strategy")

if __name__ == "__main__":
    print("=" * 60)
    print("  Fix 403 Errors - Set API Keys")
    print("=" * 60)
    print()
    set_api_keys()
