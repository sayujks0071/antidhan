import re
import os

files_to_check = [
    'mcx_crudeoil_trend_strategy.py',
    'mcx_copper_trend_strategy.py',
    'mcx_advanced_strategy.py',
    'mcx_silver_trend_strategy.py',
    'mcx_aluminium_trend_strategy.py'
]

for filename in files_to_check:
    filepath = 'openalgo/strategies/scripts/' + filename
    with open(filepath, 'r') as f:
        content = f.read()

    content = re.sub(r'api_key = args\.api_key or os\.getenv\("OPENALGO_APIKEY"\)', 'api_key = args.api_key', content)
    content = re.sub(r"api_key = os\.getenv\('OPENALGO_APIKEY', args\.api_key\)", "api_key = args.api_key", content)

    with open(filepath, 'w') as f:
        f.write(content)
