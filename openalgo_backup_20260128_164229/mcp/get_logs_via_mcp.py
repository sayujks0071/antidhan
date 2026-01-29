#!/usr/bin/env python3
"""
Get OpenAlgo log details using MCP tools
This script demonstrates how to use OpenAlgo MCP tools to get logs
"""
import sys
import json
from pathlib import Path

# Add openalgo to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from openalgo import api
except ImportError:
    print("❌ Error: Could not import openalgo. Make sure you're in the openalgo directory.")
    sys.exit(1)

def get_log_details(api_key: str, host: str = "http://127.0.0.1:5001"):
    """Get all log details from OpenAlgo"""
    
    print("=" * 70)
    print("  OPENALGO LOG DETAILS VIA MCP")
    print("=" * 70)
    print()
    
    # Initialize client
    try:
        client = api(api_key=api_key, host=host)
        print(f"✅ Connected to OpenAlgo at {host}")
    except Exception as e:
        print(f"❌ Failed to connect to OpenAlgo: {e}")
        print(f"   Make sure OpenAlgo server is running on {host}")
        return
    
    print()
    
    # 1. Order Book
    print("📋 ORDER BOOK (All Orders)")
    print("-" * 70)
    try:
        orders = client.orderbook()
        if isinstance(orders, dict):
            if orders.get('status') == 'success' and 'data' in orders:
                order_list = orders['data']
                if order_list:
                    print(f"✅ Found {len(order_list)} orders:\n")
                    for i, order in enumerate(order_list[:20], 1):
                        print(f"  [{i}] Order ID: {order.get('orderid', 'N/A')}")
                        print(f"      Symbol: {order.get('symbol', 'N/A')} | Exchange: {order.get('exchange', 'N/A')}")
                        print(f"      Action: {order.get('action', 'N/A')} | Qty: {order.get('quantity', 'N/A')}")
                        print(f"      Status: {order.get('status', 'N/A')} | Price: {order.get('price', 'N/A')}")
                        print()
                else:
                    print("  ℹ️  No orders found")
            else:
                print(f"  ⚠️  {orders.get('message', 'Unknown error')}")
        else:
            print(f"  Response: {json.dumps(orders, indent=2)[:200]}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    print()
    
    # 2. Trade Book
    print("📊 TRADE BOOK (Executed Trades)")
    print("-" * 70)
    try:
        trades = client.tradebook()
        if isinstance(trades, dict):
            if trades.get('status') == 'success' and 'data' in trades:
                trade_list = trades['data']
                if trade_list:
                    print(f"✅ Found {len(trade_list)} trades:\n")
                    for i, trade in enumerate(trade_list[:20], 1):
                        print(f"  [{i}] Order ID: {trade.get('orderid', 'N/A')}")
                        print(f"      Symbol: {trade.get('symbol', 'N/A')} | Exchange: {trade.get('exchange', 'N/A')}")
                        print(f"      Action: {trade.get('action', 'N/A')} | Qty: {trade.get('quantity', 'N/A')}")
                        print(f"      Price: {trade.get('price', 'N/A')} | Time: {trade.get('tradetime', 'N/A')}")
                        print()
                else:
                    print("  ℹ️  No trades found")
            else:
                print(f"  ⚠️  {trades.get('message', 'Unknown error')}")
        else:
            print(f"  Response: {json.dumps(trades, indent=2)[:200]}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    print()
    
    # 3. Position Book
    print("💼 POSITION BOOK (Current Positions)")
    print("-" * 70)
    try:
        positions = client.positionbook()
        if isinstance(positions, dict):
            if positions.get('status') == 'success' and 'data' in positions:
                position_list = positions['data']
                if position_list:
                    print(f"✅ Found {len(position_list)} positions:\n")
                    for i, pos in enumerate(position_list[:20], 1):
                        print(f"  [{i}] Symbol: {pos.get('symbol', 'N/A')} | Exchange: {pos.get('exchange', 'N/A')}")
                        print(f"      Product: {pos.get('product', 'N/A')} | Quantity: {pos.get('quantity', 'N/A')}")
                        print(f"      Avg Price: {pos.get('avgprice', 'N/A')} | LTP: {pos.get('ltp', 'N/A')}")
                        print(f"      P&L: {pos.get('pnl', 'N/A')}")
                        print()
                else:
                    print("  ℹ️  No positions found")
            else:
                print(f"  ⚠️  {positions.get('message', 'Unknown error')}")
        else:
            print(f"  Response: {json.dumps(positions, indent=2)[:200]}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    print()
    
    # 4. Holdings
    print("📦 HOLDINGS (Long-term Investments)")
    print("-" * 70)
    try:
        holdings = client.holdings()
        if isinstance(holdings, dict):
            if holdings.get('status') == 'success' and 'data' in holdings:
                holding_list = holdings['data']
                if holding_list:
                    print(f"✅ Found {len(holding_list)} holdings:\n")
                    for i, holding in enumerate(holding_list[:20], 1):
                        print(f"  [{i}] Symbol: {holding.get('symbol', 'N/A')} | Exchange: {holding.get('exchange', 'N/A')}")
                        print(f"      Quantity: {holding.get('quantity', 'N/A')} | Avg Price: {holding.get('avgprice', 'N/A')}")
                        print(f"      LTP: {holding.get('ltp', 'N/A')} | P&L: {holding.get('pnl', 'N/A')}")
                        print()
                else:
                    print("  ℹ️  No holdings found")
            else:
                print(f"  ⚠️  {holdings.get('message', 'Unknown error')}")
        else:
            print(f"  Response: {json.dumps(holdings, indent=2)[:200]}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    print()
    print("=" * 70)
    print("✅ Log details retrieved successfully!")
    print("=" * 70)

if __name__ == "__main__":
    # Get API key from command line or use default
    if len(sys.argv) > 1:
        api_key = sys.argv[1]
    else:
        # Try to get from strategy_env.json
        try:
            import json
            env_file = Path(__file__).parent.parent / "strategies" / "strategy_env.json"
            if env_file.exists():
                with open(env_file, 'r') as f:
                    data = json.load(f)
                    # Get first API key found
                    for strategy_id, config in data.items():
                        if isinstance(config, dict) and 'OPENALGO_APIKEY' in config:
                            api_key = config['OPENALGO_APIKEY']
                            break
                    else:
                        print("❌ No API key found in strategy_env.json")
                        sys.exit(1)
            else:
                print("❌ Please provide API key as argument or configure strategy_env.json")
                sys.exit(1)
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
    
    # Get host from command line or use default
    host = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:5001"
    
    get_log_details(api_key, host)
