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
            print\("Resolved API key from database\."\)
    except ImportError:
        pass
    except Exception as e:
        print\(f"Error fetching API key from DB: \{e\}"\)

if not API_KEY:
    API_KEY = "dummy_key"'''

content = re.sub(pattern, '', content)

content = content.replace('APIClient(api_key=API_KEY, host=HOST)', 'APIClient()')
content = content.replace('OptionChainClient(api_key=API_KEY, host=HOST)', 'OptionChainClient()')

with open('openalgo/strategies/scripts/nifty_smart_trend_oi.py', 'w') as f:
    f.write(content)

print("nifty_smart_trend_oi.py fixed")
