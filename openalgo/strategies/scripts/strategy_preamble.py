import os
import sys

# Ensure openalgo root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(current_dir) # openalgo/strategies
openalgo_root = os.path.dirname(strategies_dir) # openalgo

if openalgo_root not in sys.path:
    sys.path.insert(0, openalgo_root)

# Also add strategies/utils so we can import base_strategy
utils_dir = os.path.join(strategies_dir, 'utils')
if utils_dir not in sys.path:
    sys.path.insert(0, utils_dir)

# Import BaseStrategy so it can be re-exported
try:
    from base_strategy import BaseStrategy
except ImportError:
    try:
        from openalgo.strategies.utils.base_strategy import BaseStrategy
    except ImportError:
        print("Error: Could not import BaseStrategy. Check paths.")
        raise
