import os
import shutil
import sqlite3
import datetime
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    # Determine directories
    script_dir = Path(__file__).resolve().parent
    openalgo_dir = script_dir.parent
    repo_root = openalgo_dir.parent

    # Potential DB directories
    db_dirs = [
        openalgo_dir / 'db',        # openalgo/db
        repo_root / 'db'            # root/db
    ]

    backup_root = openalgo_dir / 'db' / 'backups'

    # Ensure backup directory exists
    if not os.path.exists(backup_root):
        os.makedirs(backup_root)
        logger.info(f"Created backup directory: {backup_root}")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # DB files to process
    dbs = {
        'openalgo.db': None,  # No table to clear
        'latency.db': 'order_latency',
        'logs.db': 'traffic_logs'
    }

    processed_files = set()

    for db_dir in db_dirs:
        if not db_dir.exists():
            continue

        logger.info(f"Scanning directory: {db_dir}")

        for db_name, table_to_clear in dbs.items():
            db_path = db_dir / db_name

            # Skip if already processed (though likely distinct files)
            # Actually, treat them as distinct.

            if db_path.exists():
                # Backup
                # Use dir name in backup filename to distinguish
                dir_suffix = db_dir.name if db_dir.name != 'db' else ('root' if db_dir == repo_root / 'db' else 'openalgo')
                backup_filename = f"{os.path.splitext(db_name)[0]}_{dir_suffix}_{timestamp}.db"
                backup_path = backup_root / backup_filename

                try:
                    shutil.copy2(db_path, backup_path)
                    logger.info(f"Backed up {db_path} to {backup_path}")
                except Exception as e:
                    logger.error(f"Failed to backup {db_name}: {e}")

                # Clear table if specified
                if table_to_clear:
                    try:
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()

                        # Check if table exists
                        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_to_clear}';")
                        if cursor.fetchone():
                            cursor.execute(f"DELETE FROM {table_to_clear};")
                            conn.commit()
                            logger.info(f"Cleared table '{table_to_clear}' in {db_path}")
                        else:
                            logger.warning(f"Table '{table_to_clear}' not found in {db_path}, skipping clear.")

                        conn.close()
                    except Exception as e:
                        logger.error(f"Failed to clear table in {db_path}: {e}")
            else:
                logger.debug(f"{db_name} does not exist in {db_dir}")

if __name__ == "__main__":
    main()
