import re

with open('openalgo/strategies/utils/trading_utils.py', 'r') as f:
    content = f.read()

get_api_code = """
def get_api_credentials():
    \"\"\"
    Centralized function to resolve API key and Host.
    Tries environment variables first, then database fallback for API key.
    \"\"\"
    # 1. Try environment variables
    api_key = os.getenv('OPENALGO_APIKEY') or os.getenv('OPENALGO_API_KEY')

    # 2. Try database fallback
    if not api_key:
        try:
            # Need to add openalgo root to path to import database.auth_db
            import sys
            current_dir = os.path.dirname(os.path.abspath(__file__))
            strategies_dir = os.path.dirname(current_dir)
            openalgo_root = os.path.dirname(strategies_dir)
            if openalgo_root not in sys.path:
                sys.path.insert(0, openalgo_root)

            from database.auth_db import get_first_available_api_key
            api_key = get_first_available_api_key()
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to fetch API key from DB fallback: {e}")

    # Resolve Host
    host = os.getenv('OPENALGO_HOST')
    if not host:
        port = os.getenv('OPENALGO_PORT', '5000')
        host = f"http://127.0.0.1:{port}"

    return api_key, host

"""

if 'def get_api_credentials' not in content:
    content = content.replace('def normalize_symbol(symbol):', get_api_code + '\ndef normalize_symbol(symbol):')
    with open('openalgo/strategies/utils/trading_utils.py', 'w') as f:
        f.write(content)
    print("Added get_api_credentials to trading_utils.py")
else:
    print("get_api_credentials already exists")
