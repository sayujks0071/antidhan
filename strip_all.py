import os
import re

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
    filepath = os.path.join('openalgo/strategies/scripts', filename)
    if not os.path.exists(filepath):
        continue

    with open(filepath, 'r') as f:
        content = f.read()

    # Nifty Smart Trend
    if 'nifty_smart_trend_oi' in filename:
        start_marker = "# API Key retrieval"
        end_marker = 'API_KEY = "dummy_key"'
        start_idx = content.find(start_marker)
        end_idx = content.find(end_marker)
        if start_idx != -1 and end_idx != -1:
            content = content[:start_idx] + content[end_idx + len(end_marker):]

        content = content.replace('APIClient(api_key=API_KEY, host=HOST)', 'APIClient()')
        content = content.replace('OptionChainClient(api_key=API_KEY, host=HOST)', 'OptionChainClient()')

    # Global Arbitrage
    if 'mcx_global_arbitrage' in filename:
        content = re.sub(r"API_HOST = os\.getenv\('OPENALGO_HOST', 'http://127\.0\.0\.1:5001'\)\nAPI_KEY = os\.getenv\('OPENALGO_APIKEY', 'demo_key'\)", "", content)
        content = re.sub(r"if args\.port: API_HOST = f\"http://127\.0\.0\.1:\{args\.port\}\"\n\s*elif os\.getenv\('OPENALGO_PORT'\): API_HOST = f\"http://127\.0\.0\.1:\{os\.getenv\('OPENALGO_PORT'\)\}\"\n\n\s*if args\.api_key: API_KEY = args\.api_key\n\s*else: API_KEY = os\.getenv\('OPENALGO_APIKEY', API_KEY\)", "", content)
        content = re.sub(r"api_client = APIClient\(api_key=API_KEY, host=API_HOST\)", "api_client = APIClient()", content)

    # Advanced options ranker
    if 'advanced_options_ranker' in filename:
        content = re.sub(r'self\.api_key = api_key or os\.getenv\("OPENALGO_API_KEY", "dummy_key"\)\n\s*self\.host = host\n\s*self\.client = APIClient\(self\.api_key, host=self\.host\)', 'self.client = APIClient(api_key, host)', content)

    # Delta neutral
    if 'delta_neutral_iron_condor' in filename:
        content = re.sub(r'client = APIClient\(api_key=os\.getenv\("OPENALGO_API_KEY"\), host=f"http://127\.0\.0\.1:\{args\.port\}"\)', 'client = APIClient()', content)
        content = re.sub(r'api_client = APIClient\(API_KEY, HOST\)', 'api_client = APIClient()', content)

    # MCX Advanced Strategy
    if 'mcx_advanced_strategy' in filename:
        content = re.sub(r'# Setup API connections\nAPI_HOST = os\.getenv\(\'OPENALGO_HOST\', f"http://127\.0\.0\.1:\{os\.getenv\(\'OPENALGO_PORT\', \'5000\'\)\}"\)\nAPI_KEY = os\.getenv\(\'OPENALGO_APIKEY\', \'demo_key\'\)\n', '', content)

    with open(filepath, 'w') as f:
        f.write(content)
