import sys
import os
import sqlite3
import logging

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_table(db_path, table_name):
    """
    Connects to the database and clears the specified table if it exists.
    """
    if not os.path.exists(db_path):
        logger.warning(f"Database {db_path} not found. Skipping cleanup of {table_name}.")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}';")
        if not cursor.fetchone():
            logger.warning(f"Table {table_name} not found in {db_path}.")
            conn.close()
            return

        # Clear table
        cursor.execute(f"DELETE FROM {table_name};")
        conn.commit()

        # Verify
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        count = cursor.fetchone()[0]
        if count == 0:
            logger.info(f"Successfully cleared {table_name} in {db_path}.")
        else:
            logger.error(f"Failed to clear {table_name} in {db_path}. Remaining rows: {count}")

        conn.close()
    except Exception as e:
        logger.error(f"Error cleaning {table_name} in {db_path}: {e}")

def main():
    logger.info("Starting database cleanup...")

    # Paths (assuming relative to repo root if run from there, or use repo_root)
    # Based on .sample.env
    db_dir = os.path.join(repo_root, "db")
    openalgo_db = os.path.join(db_dir, "openalgo.db")
    latency_db = os.path.join(db_dir, "latency.db")
    logs_db = os.path.join(db_dir, "logs.db")

    # Clean order_latency table (in latency.db or openalgo.db)
    clean_table(openalgo_db, "order_latency")
    clean_table(latency_db, "order_latency")

    # Clean traffic_logs table (in logs.db or openalgo.db)
    # User said "traffic" table, but code says "traffic_logs".
    # I'll try both just in case.
    clean_table(openalgo_db, "traffic")
    clean_table(openalgo_db, "traffic_logs")
    clean_table(logs_db, "traffic")
    clean_table(logs_db, "traffic_logs")

    logger.info("Database cleanup complete.")

if __name__ == "__main__":
    main()
