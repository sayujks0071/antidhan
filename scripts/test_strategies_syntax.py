import sys
from unittest.mock import MagicMock
import os

# Mock dependencies
sys.modules['pandas'] = MagicMock()
sys.modules['numpy'] = MagicMock()
sys.modules['httpx'] = MagicMock()
sys.modules['pytz'] = MagicMock()
sys.modules['flask'] = MagicMock()
sys.modules['flask_sqlalchemy'] = MagicMock()
sys.modules['sqlalchemy'] = MagicMock()
sys.modules['cachetools'] = MagicMock()
sys.modules['argon2'] = MagicMock()
sys.modules['cryptography'] = MagicMock()
sys.modules['h2'] = MagicMock()
sys.modules['requests'] = MagicMock()
sys.modules['dotenv'] = MagicMock()
sys.modules['utils'] = MagicMock()

import importlib.util

def check_syntax(filepath):
    print(f"Checking syntax of {filepath}...")
    try:
        spec = importlib.util.spec_from_file_location("strategy", filepath)
        module = importlib.util.module_from_spec(spec)
        sys.modules["strategy"] = module
        spec.loader.exec_module(module)
        print("Syntax OK.")
        return True
    except Exception as e:
        print(f"Syntax Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    filepath = "openalgo/strategies/scripts/gap_fade_strategy.py"
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    if check_syntax(filepath):
        sys.exit(0)
    else:
        sys.exit(1)
