with open('openalgo/strategies/utils/base_strategy.py', 'r') as f:
    content = f.read()

start_idx = content.find('    def _resolve_api_key(self, api_key):')
end_idx = content.find('    def setup_logging(self, log_file=None):')

if start_idx != -1 and end_idx != -1:
    new_methods = '''    def _resolve_api_key(self, api_key):
        """Resolve API Key from multiple sources."""
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
        """Resolve API Host."""
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

'''
    content = content[:start_idx] + new_methods + content[end_idx:]
    with open('openalgo/strategies/utils/base_strategy.py', 'w') as f:
        f.write(content)
    print("Patched BaseStrategy correctly")
else:
    print("Could not find boundaries")
