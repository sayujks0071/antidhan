import os
import sys
import json
from datetime import datetime
from sqlalchemy import create_engine, text
import pandas as pd

# Add openalgo to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.getcwd(), 'openalgo', '.env'))
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL")

def main():
    print("Starting Market Hours Audit...")

    db_url = DATABASE_URL
    if not db_url:
        # Try to find sqlite file in various locations
        possible_paths = [
            os.path.join(os.getcwd(), 'openalgo', 'algo.db'),
            os.path.join(os.getcwd(), 'algo.db'),
            os.path.join(os.getcwd(), 'instance', 'algo.db'),
            os.path.join(os.getcwd(), 'openalgo', 'instance', 'algo.db')
        ]

        for path in possible_paths:
            if os.path.exists(path):
                print(f"Found database at {path}")
                db_url = f"sqlite:///{path}"
                break

        if not db_url:
            print("DATABASE_URL not set and algo.db not found.")
            print("Cannot perform Latency Audit or Slippage Check on live data.")
            return

    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            # Check if table exists
            try:
                # For SQLite
                query = text("SELECT name FROM sqlite_master WHERE type='table' AND name='order_logs'")
                result = conn.execute(query)
                if not result.fetchone():
                    print("Table 'order_logs' does not exist.")
                    return
            except Exception:
                # Might be postgres or other DB where this query fails
                pass

            query = text("SELECT * FROM order_logs WHERE api_type = 'placesmartorder' ORDER BY created_at DESC LIMIT 100")
            try:
                df = pd.read_sql(query, conn)
            except Exception as e:
                print(f"Error querying order_logs: {e}")
                return

            if df.empty:
                print("No 'placesmartorder' logs found.")
                return

            print(f"Found {len(df)} orders.")

            errors = 0

            for _, row in df.iterrows():
                try:
                    res_str = row['response_data']
                    if isinstance(res_str, str):
                        res = json.loads(res_str)
                    else:
                        res = res_str # Already dict?

                    # Check for errors
                    if isinstance(res, dict):
                        if res.get('status') == 'error' or res.get('status') == 'failed':
                            errors += 1
                            print(f"Order Error (ID: {row.get('id')}): {res.get('message')}")
                except Exception as e:
                    pass

            print(f"Total Errors in last {len(df)} orders: {errors}")

            if errors == 0:
                print("No API errors found in logs.")

            print("Latency Audit: Cannot calculate precise latency from DB logs (missing request timestamp).")
            print("Slippage Check: Cannot calculate slippage (missing trade execution data).")

    except Exception as e:
        print(f"Error connecting to database: {e}")

if __name__ == "__main__":
    main()
