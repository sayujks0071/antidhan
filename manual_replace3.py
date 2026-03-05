import re
import os

files_to_check = [
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

for filename in files_to_check:
    filepath = 'openalgo/strategies/scripts/' + filename
    with open(filepath, 'r') as f:
        content = f.read()

    # Nifty smart trend
    if 'nifty_smart_trend_oi' in filename:
        content = content.replace('self.client = OptionChainClient(api_key=API_KEY, host=HOST)', 'self.client = OptionChainClient()')
        content = content.replace('self.api_client = APIClient(api_key=API_KEY, host=HOST)', 'self.api_client = APIClient()')

    # Trend strategies
    if 'trend' in filename and 'mcx' in filename:
        content = re.sub(r"if args\.api_key:\s*api_key = args\.api_key\n\s*else:\s*api_key = os\.getenv\('OPENALGO_APIKEY', 'demo_key'\)\n\n\s*if args\.port:\s*host = f\"http://127\.0\.0\.1:\{args\.port\}\"\n\s*else:\s*host = os\.getenv\('OPENALGO_HOST', f\"http://127\.0\.0\.1:\{os\.getenv\('OPENALGO_PORT', '5000'\)\}\"\)\n\n\s*strategy = [A-Za-z0-9_]+\(\n\s*symbol=SYMBOL,\n\s*quantity=args\.qty,\n\s*api_key=api_key,\n\s*host=host", lambda m: m.group(0).replace('api_key=api_key', 'api_key=args.api_key').replace('host=host', 'host=f"http://127.0.0.1:{args.port}" if args.port else None').replace(re.search(r'if args\.api_key:.*?\n\n', m.group(0), re.DOTALL).group(0), ''), content)

    # mcx global arbitrage
    if 'mcx_global_arbitrage_strategy' in filename:
        content = re.sub(r'api_client = APIClient\(api_key=API_KEY, host=API_HOST\)', 'api_client = APIClient()', content)

    with open(filepath, 'w') as f:
        f.write(content)
