import re

with open('openalgo/strategies/scripts/nifty_smart_trend_oi.py', 'r') as f:
    content = f.read()

pattern = r'''# API Key retrieval
API_KEY = os\.getenv\("OPENALGO_APIKEY"\)
HOST = os\.getenv\("OPENALGO_HOST", "http://127\.0\.0\.1:5000"\)

if not API_KEY:
    try:
        from database\.auth_db import get_first_available_api_key
        API_KEY = get_first_available_api_key\(\)
        if API_KEY:
            print\("Successfully retrieved API Key from database\.", flush=True\)
    except Exception as e:
        print\(f"Warning: Could not retrieve API key from database: \{e\}", flush=True\)

if not API_KEY:
    print\("CRITICAL: API Key must be set in OPENALGO_APIKEY environment variable", flush=True\)'''

content = re.sub(pattern, '', content)

content = content.replace('OptionChainClient(api_key=API_KEY, host=HOST)', 'OptionChainClient()')
content = content.replace('APIClient(api_key=API_KEY, host=HOST)', 'APIClient()')

with open('openalgo/strategies/scripts/nifty_smart_trend_oi.py', 'w') as f:
    f.write(content)
