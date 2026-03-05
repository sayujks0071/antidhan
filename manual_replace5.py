import re

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

    content = content.replace('self.client = APIClient(api_key=self.api_key, host=self.host) if APIClient else None', 'self.client = APIClient() if APIClient else None')
    content = content.replace('self.client = APIClient(api_key=self.api_key, host=self.api_host)', 'self.client = APIClient()')

    with open(filepath, 'w') as f:
        f.write(content)
