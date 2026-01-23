from openalgo import api

# Initialize client
client = api(api_key="YOUR_OPENALGO_APIKEY", host="http://127.0.0.1:5000")

# Fetch multiple quotes
response = client.multiquotes(symbols=[
    {"symbol": "RELIANCE", "exchange": "NSE"},
    {"symbol": "TCS", "exchange": "NSE"},
    {"symbol": "INFY", "exchange": "NSE"}
])

print(response)

