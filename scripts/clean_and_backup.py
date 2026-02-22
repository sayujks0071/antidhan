import os
import shutil
import sqlite3
import datetime

# Define paths relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))

# Database paths
OPENALGO_DB_PATH = os.path.join(REPO_ROOT, 'openalgo', 'db', 'openalgo.db')
LATENCY_DB_PATH = os.path.join(REPO_ROOT, 'openalgo', 'db', 'latency.db')
LOGS_DB_PATH = os.path.join(REPO_ROOT, 'openalgo', 'db', 'logs.db')
BACKUP_DIR = os.path.join(REPO_ROOT, 'db', 'backups')

def backup_database():
    if not os.path.exists(OPENALGO_DB_PATH):
        print(f"Warning: Database file not found at {OPENALGO_DB_PATH}. Skipping backup.")
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"openalgo_backup_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    try:
        shutil.copy2(OPENALGO_DB_PATH, backup_path)
        print(f"Backup created successfully: {backup_path}")
    except Exception as e:
        print(f"Error creating backup: {e}")

def clear_and_vacuum(db_path, table_name):
    if not os.path.exists(db_path):
        print(f"Database file not found at {db_path}. Skipping clearing {table_name}.")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute(f"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if cursor.fetchone()[0] == 0:
            print(f"Table {table_name} does not exist in {db_path}. Skipping.")
            conn.close()
            return

        print(f"Clearing table {table_name} in {db_path}...")
        cursor.execute(f"DELETE FROM {table_name}")
        conn.commit()

        print(f"Vacuuming {db_path} to reclaim space...")
        cursor.execute("VACUUM")
        conn.commit()

        print(f"Successfully cleaned and vacuumed {db_path}.")
        conn.close()
    except Exception as e:
        print(f"Error maintaining {table_name} in {db_path}: {e}")

if __name__ == "__main__":
    print(f"Starting database maintenance from {REPO_ROOT}...")
    backup_database()

    # Clear tables in their respective databases
    # Note: Default config uses separate DBs for latency and logs
    clear_and_vacuum(LATENCY_DB_PATH, "order_latency")
    clear_and_vacuum(LOGS_DB_PATH, "traffic_logs")

    # Also check openalgo.db for these tables (in case of single-db setup)
    clear_and_vacuum(OPENALGO_DB_PATH, "order_latency")
    clear_and_vacuum(OPENALGO_DB_PATH, "traffic_logs")

    print("Database maintenance complete.")
