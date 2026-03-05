import os
import re

scripts_dir = 'openalgo/strategies/scripts'

files_to_fix = [
    'nifty_smart_trend_oi.py',
    'mcx_global_arbitrage_strategy.py',
    'mcx_crudeoil_trend_strategy.py',
    'advanced_options_ranker.py',
    'mcx_copper_trend_strategy.py',
    'mcx_advanced_strategy.py',
    'mcx_silver_trend_strategy.py',
    'delta_neutral_iron_condor_nifty.py',
    'mcx_aluminium_trend_strategy.py'
]

for filename in files_to_fix:
    filepath = os.path.join(scripts_dir, filename)
    if not os.path.exists(filepath):
        continue

    with open(filepath, 'r') as f:
        content = f.read()

    # Pattern to remove explicit API key fetching from database and os.getenv assignments

    # 1. Remove blocks like:
    # API_KEY = os.getenv("OPENALGO_APIKEY")
    # if not API_KEY:
    #     try:
    #         from database.auth_db import get_first_available_api_key
    #         API_KEY = get_first_available_api_key()
    # ...
    content = re.sub(
        r'(# API Key retrieval\n)?API_KEY = os\.getenv\("OPENALGO_APIKEY"\)\s*\nHOST = os\.getenv\("OPENALGO_HOST", "http://127\.0\.0\.1:5000"\)\s*\nif not API_KEY:\s*\n\s*try:\s*\n\s*from database\.auth_db import get_first_available_api_key\s*\n\s*API_KEY = get_first_available_api_key\(\)\s*\n\s*if API_KEY:\s*\n\s*print\("Resolved API key from database\."\)\s*\n\s*except ImportError:\s*\n\s*pass\s*\n\s*except Exception as e:\s*\n\s*print\(f"Error fetching API key from DB: {e}"\)\s*\nif not API_KEY:\s*\n\s*API_KEY = "dummy_key"',
        '',
        content,
        flags=re.DOTALL
    )

    # 2. Refactor APIClient/OptionChainClient calls to drop kwargs if they are using redundant vars
    content = re.sub(r'APIClient\(api_key=API_KEY,\s*host=HOST\)', 'APIClient()', content)
    content = re.sub(r'OptionChainClient\(api_key=API_KEY,\s*host=HOST\)', 'OptionChainClient()', content)

    content = re.sub(r'APIClient\(api_key=API_KEY,\s*host=API_HOST\)', 'APIClient()', content)
    content = re.sub(r'APIClient\(api_key=API_KEY,\s*host=f"http://127.0.0.1:\{os.getenv\(\'OPENALGO_PORT\', \'5000\'\)\}"\)', 'APIClient()', content)

    # Advanced Options Ranker
    content = re.sub(r'self\.api_key = api_key or os\.getenv\("OPENALGO_API_KEY", "dummy_key"\)\n\s*self\.host = host\n\s*self\.client = APIClient\(self\.api_key, host=self\.host\)', 'self.client = APIClient(api_key, host)', content)

    # Delta neutral Iron Condor
    content = re.sub(r'client = APIClient\(api_key=os\.getenv\("OPENALGO_API_KEY"\), host=f"http://127\.0\.0\.1:\{args\.port\}"\)', 'client = APIClient(host=f"http://127.0.0.1:{args.port}" if args.port else None)', content)

    # MCX Global Arbitrage Strategy
    content = re.sub(r'API_HOST = os\.getenv\(\'OPENALGO_HOST\', \'http://127\.0\.0\.1:5001\'\)\nAPI_KEY = os\.getenv\(\'OPENALGO_APIKEY\', \'demo_key\'\)', '', content)
    content = re.sub(r'if args\.port: API_HOST = f"http://127\.0\.0\.1:\{args\.port\}"\n\s*elif os\.getenv\(\'OPENALGO_PORT\'\): API_HOST = f"http://127\.0\.0\.1:\{os\.getenv\(\'OPENALGO_PORT\'\)\}"\n\s*if args\.api_key: API_KEY = args\.api_key\n\s*else: API_KEY = os\.getenv\(\'OPENALGO_APIKEY\', API_KEY\)', '', content)
    content = re.sub(r'api_client = APIClient\(api_key=API_KEY,\s*host=API_HOST\)', 'api_client = APIClient(api_key=args.api_key, host=f"http://127.0.0.1:{args.port}" if args.port else None)', content)

    # Trend strategies
    content = re.sub(r'if args\.api_key:\s*api_key = args\.api_key\n\s*else:\s*api_key = os\.getenv\(\'OPENALGO_APIKEY\', \'demo_key\'\)\n\n\s*if args\.port:\s*host = f"http://127\.0\.0\.1:\{args\.port\}"\n\s*else:\s*host = os\.getenv\(\'OPENALGO_HOST\', f"http://127\.0\.0\.1:\{os\.getenv\(\'OPENALGO_PORT\', \'5000\'\)\}"\)\n\n\s*strategy = [a-zA-Z0-9_]+\(\n\s*symbol=SYMBOL,\n\s*quantity=args\.qty,\n\s*api_key=api_key,\n\s*host=host', lambda m: m.group(0).replace('api_key=api_key', 'api_key=args.api_key').replace('host=host', 'host=f"http://127.0.0.1:{args.port}" if args.port else None').replace(re.search(r'if args\.api_key:.*?\n\n', m.group(0), re.DOTALL).group(0), ''), content)

    with open(filepath, 'w') as f:
        f.write(content)

print("Redundant code stripped")
