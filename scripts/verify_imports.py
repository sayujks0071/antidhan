import sys
import os

# Add repo root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(current_dir)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
    sys.path.insert(0, os.path.join(repo_root, "openalgo"))

try:
    print("Importing trading_utils...")
    from strategies.utils import trading_utils
    print("trading_utils imported successfully.")

    print("Checking refactored functions...")
    assert hasattr(trading_utils, 'calculate_supertrend')
    assert hasattr(trading_utils, 'calculate_macd')
    assert hasattr(trading_utils, 'calculate_sma')
    print("Refactored functions present.")

    print("Importing nse_rsi_macd_strategy...")
    from strategies.scripts import nse_rsi_macd_strategy
    print("nse_rsi_macd_strategy imported successfully.")

    print("Importing supertrend_vwap_strategy...")
    from strategies.scripts import supertrend_vwap_strategy
    print("supertrend_vwap_strategy imported successfully.")

except Exception as e:
    print(f"Import failed: {e}")
    sys.exit(1)
