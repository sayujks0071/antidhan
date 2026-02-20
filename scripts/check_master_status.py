import sys
import os

# Add repo root to path
sys.path.insert(0, os.getcwd())

try:
    # Ensure openalgo package can be found
    if os.path.join(os.getcwd(), 'openalgo') not in sys.path:
        sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

    from openalgo.database.master_contract_status_db import get_status
    brokers = ["dhan", "kite", "zerodha", "angelone"]
    total = 0
    found_any = False
    for b in brokers:
        status = get_status(b)
        # print(f"Broker: {b}, Status: {status.get('status')}, Symbols: {status.get('total_symbols')}")
        try:
            count = int(status.get('total_symbols', 0))
            if count > 0:
                found_any = True
            total += count
        except:
            pass

    # If total is 0, maybe check if a master csv exists as fallback?
    # But for now just print what DB says.
    print(f"TOTAL_SYMBOLS={total}")

except ImportError as e:
    print(f"Error importing DB: {e}")
    # Fallback
    print("TOTAL_SYMBOLS=0")
except Exception as e:
    print(f"Error: {e}")
    print("TOTAL_SYMBOLS=0")
