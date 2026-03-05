import re

files = [
    'advanced_options_ranker.py',
    'delta_neutral_iron_condor_nifty.py',
    'mcx_advanced_strategy.py',
    'mcx_global_arbitrage_strategy.py'
]

for filename in files:
    with open('openalgo/strategies/scripts/' + filename, 'r') as f:
        content = f.read()

    # mcx_advanced_strategy
    content = re.sub(r'''# Setup API connections
API_HOST = os\.getenv\('OPENALGO_HOST', f"http://127\.0\.0\.1:\{os\.getenv\('OPENALGO_PORT', '5000'\)\}"\)
API_KEY = os\.getenv\('OPENALGO_APIKEY', 'demo_key'\)''', '', content)

    # advanced_options_ranker
    content = re.sub(r'''        self\.api_key = api_key or os\.getenv\("OPENALGO_API_KEY", "dummy_key"\)
        self\.host = host
        self\.client = APIClient\(self\.api_key, host=self\.host\)''', '        self.client = APIClient(api_key, host)', content)

    # delta neutral iron condor
    content = re.sub(r'client = APIClient\(api_key=os\.getenv\("OPENALGO_API_KEY"\), host=f"http://127\.0\.0\.1:\{args\.port\}"\)', 'client = APIClient(host=f"http://127.0.0.1:{args.port}" if args.port else None)', content)

    # mcx_global_arbitrage
    content = re.sub(r'''API_HOST = os\.getenv\('OPENALGO_HOST', 'http://127\.0\.0\.1:5001'\)
API_KEY = os\.getenv\('OPENALGO_APIKEY', 'demo_key'\)''', '', content)
    content = re.sub(r'''    if args\.port: API_HOST = f"http://127\.0\.0\.1:\{args\.port\}"
    elif os\.getenv\('OPENALGO_PORT'\): API_HOST = f"http://127\.0\.0\.1:\{os\.getenv\('OPENALGO_PORT'\)\}"

    if args\.api_key: API_KEY = args\.api_key
    else: API_KEY = os\.getenv\('OPENALGO_APIKEY', API_KEY\)''', '', content)
    content = re.sub(r'api_client = APIClient\(api_key=API_KEY, host=API_HOST\)', 'api_client = APIClient(api_key=args.api_key if hasattr(args, "api_key") else None, host=f"http://127.0.0.1:{args.port}" if hasattr(args, "port") and args.port else None)', content)

    with open('openalgo/strategies/scripts/' + filename, 'w') as f:
        f.write(content)

print("Others fixed")
