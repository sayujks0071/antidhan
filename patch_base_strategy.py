import re

with open('openalgo/strategies/utils/base_strategy.py', 'r') as f:
    content = f.read()

# Replace _resolve_api_key and _resolve_host
resolve_api_key_pattern = r'def _resolve_api_key\(self, api_key\):.*?def _resolve_host\(self, host\):.*?def _get_symtoken'

replacement = '''def _resolve_api_key(self, api_key):
        """
        Resolve API key from arguments, env variables, or DB.
        """
        if api_key:
            return api_key

        try:
            from trading_utils import get_api_credentials
            ak, _ = get_api_credentials()
            if ak:
                return ak
        except ImportError:
            pass

        key = os.getenv('OPENALGO_APIKEY') or os.getenv('OPENALGO_API_KEY')
        if key:
            return key

        return "dummy_key"

    def _resolve_host(self, host):
        """
        Resolve API host from arguments or env variables.
        """
        if host:
            return host.rstrip('/')

        try:
            from trading_utils import get_api_credentials
            _, h = get_api_credentials()
            if h:
                return h.rstrip('/')
        except ImportError:
            pass

        env_host = os.getenv('OPENALGO_HOST')
        if env_host:
            return env_host.rstrip('/')

        port = os.getenv('OPENALGO_PORT', '5000')
        return f"http://127.0.0.1:{port}"

    def _get_symtoken'''

content = re.sub(resolve_api_key_pattern, replacement, content, flags=re.DOTALL)

with open('openalgo/strategies/utils/base_strategy.py', 'w') as f:
    f.write(content)

print("BaseStrategy patched")
