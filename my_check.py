import re

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

    print(f"--- {filename} ---")
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'OPENALGO_APIKEY' in line or 'OPENALGO_API_KEY' in line or 'get_first_available_api_key' in line:
            print(f"{i}: {line.strip()}")
