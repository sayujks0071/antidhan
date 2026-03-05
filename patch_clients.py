import re

with open('openalgo/strategies/utils/trading_utils.py', 'r') as f:
    content = f.read()

# Patch APIClient
api_client_pattern = r'class APIClient:\n(.*?)(def __init__\(self, api_key, host="http://127\.0\.0\.1:5000"\):)'
match = re.search(api_client_pattern, content, re.DOTALL)
if match:
    new_init = '''def __init__(self, api_key=None, host=None):
        default_api_key, default_host = get_api_credentials()
        self.api_key = api_key or default_api_key
        self.host = (host or default_host).rstrip("/")'''
    content = content.replace('def __init__(self, api_key, host="http://127.0.0.1:5000"):\n        self.api_key = api_key\n        self.host = host.rstrip("/")', new_init)

with open('openalgo/strategies/utils/trading_utils.py', 'w') as f:
    f.write(content)


with open('openalgo/strategies/utils/optionchain_utils.py', 'r') as f:
    content = f.read()

# Patch OptionChainClient
oc_client_pattern = r'class OptionChainClient:\n(.*?)(def __init__\(self, api_key, host="http://127\.0\.0\.1:5000"\):)'
match = re.search(oc_client_pattern, content, re.DOTALL)
if match:
    new_init = '''def __init__(self, api_key=None, host=None):
        try:
            from trading_utils import get_api_credentials
            default_api_key, default_host = get_api_credentials()
        except ImportError:
            import os
            default_api_key = os.getenv("OPENALGO_APIKEY") or os.getenv("OPENALGO_API_KEY")
            default_host = os.getenv("OPENALGO_HOST") or f"http://127.0.0.1:{os.getenv('OPENALGO_PORT', '5000')}"

        self.api_key = api_key or default_api_key
        self.host = (host or default_host).rstrip('/')'''
    content = content.replace("def __init__(self, api_key, host=\"http://127.0.0.1:5000\"):\n        self.api_key = api_key\n        self.host = host.rstrip('/')", new_init)

with open('openalgo/strategies/utils/optionchain_utils.py', 'w') as f:
    f.write(content)

print("Clients patched")
