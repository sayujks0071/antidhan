import os
import sys

# Get the absolute path to the strategies directory
current_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(current_dir)
openalgo_root = os.path.dirname(strategies_dir)

# Add directories to sys.path
if openalgo_root not in sys.path:
    sys.path.insert(0, openalgo_root)

if strategies_dir not in sys.path:
    sys.path.insert(0, strategies_dir)

utils_dir = os.path.join(strategies_dir, "utils")
if utils_dir not in sys.path:
    sys.path.insert(0, utils_dir)

# Import BaseStrategy to make it available to scripts importing from this preamble
from base_strategy import BaseStrategy
