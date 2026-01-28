#!/usr/bin/env python3
"""Start MCX strategies directly as subprocesses"""
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import pytz

# Add parent directory to path to import OpenAlgo utilities
sys.path.insert(0, str(Path(__file__).parent.parent))

def get_ist_time():
    """Get current IST time"""
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist)

def main():
    # Read strategy configs
    config_path = Path(__file__).parent.parent / "strategies" / "strategy_configs.json"
    env_path = Path(__file__).parent.parent / "strategies" / "strategy_env.json"
    
    with open(config_path) as f:
        configs = json.load(f)
    
    with open(env_path) as f:
        env_configs = json.load(f)
    
    # Find MCX strategies that need to be started (prioritize key strategies)
    key_mcx_strategies = ["mcx_elite_strategy", "mcx_neural_strategy", "mcx_quantum_strategy", "mcx_advanced_momentum_strategy", "mcx_ai_enhanced_strategy", "mcx_clawdbot_strategy", "crude_oil_clawdbot_strategy"]
    mcx_strategies_to_start = []
    for strategy_id, config in configs.items():
        if "mcx" in strategy_id.lower() and config.get("name") in key_mcx_strategies:
            # Force restart to pick up fixes
            mcx_strategies_to_start.append((strategy_id, config))
    
    if not mcx_strategies_to_start:
        print("All MCX strategies are already running!")
        return
    
    print(f"\nFound {len(mcx_strategies_to_start)} MCX strategies to start:")
    for strategy_id, config in mcx_strategies_to_start:
        print(f"  - {config.get('name', strategy_id)} ({strategy_id})")
    
    # Start each strategy
    print("\nStarting strategies...")
    for strategy_id, config in mcx_strategies_to_start:
        name = config.get('name', strategy_id)
        file_path = Path(config['file_path'])
        
        if not file_path.exists():
            print(f"  ✗ {name}: File not found: {file_path}")
            continue
        
        print(f"\nStarting {name}...")
        
        # Get environment variables for this strategy
        env_vars = os.environ.copy()
        if strategy_id in env_configs:
            for key, value in env_configs[strategy_id].items():
                env_vars[key] = str(value)
        
        # Create log file
        logs_dir = Path(__file__).parent.parent / "log" / "strategies"
        logs_dir.mkdir(parents=True, exist_ok=True)
        ist_now = get_ist_time()
        log_file = logs_dir / f"{strategy_id}_{ist_now.strftime('%Y%m%d_%H%M%S')}_IST.log"
        
        try:
            # Start the process
            with open(log_file, 'w') as log_f:
                process = subprocess.Popen(
                    [sys.executable, '-u', str(file_path)],
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    env=env_vars,
                    cwd=str(file_path.parent.parent)
                )
            
            # Update config
            config['is_running'] = True
            config['pid'] = process.pid
            config['last_started'] = ist_now.isoformat()
            
            print(f"  ✓ Started with PID {process.pid}")
            print(f"  Log file: {log_file}")
            
        except Exception as e:
            print(f"  ✗ Failed to start: {e}")
    
    # Save updated configs
    with open(config_path, 'w') as f:
        json.dump(configs, f, indent=2)
    
    print("\nDone!")

if __name__ == "__main__":
    import os
    main()
