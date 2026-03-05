import re
import os

files = []
for root, _, filenames in os.walk('openalgo/strategies/scripts/'):
    for filename in filenames:
        if filename.endswith('.py'):
            files.append(os.path.join(root, filename))

for file in files:
    with open(file, 'r') as f:
        content = f.read()
        if 'OPENALGO_APIKEY' in content or 'OPENALGO_API_KEY' in content or 'get_first_available_api_key' in content or 'APIClient' in content:
            print(f"File: {file} contains redundant auth/api code")
