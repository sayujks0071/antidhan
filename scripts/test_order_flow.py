import sys
import os
import json

# Add the openalgo directory to the sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'openalgo')))

def get_db_api_key():
    import sqlite3
    conn = sqlite3.connect('../openalgo/database/openalgo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT api_key FROM users LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return None

def main():
    api_key = get_db_api_key()
    if not api_key:
        print("Could not find api key in DB.")
        sys.exit(1)

    print(f"API key: {api_key}")
    # Now we can just use requests against the running app? Wait, the app isn't running.
    # We can mock the flask test client without bringing up all the dependencies by mocking up app initialization?
    # No, it's easier to use the already-made test script `scripts/simulate_order_flow.py` if it exists!

if __name__ == "__main__":
    main()
