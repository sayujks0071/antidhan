import sys
import os

# Add repo root to path
sys.path.insert(0, os.getcwd())

# Ensure db directory exists
os.makedirs("db", exist_ok=True)

try:
    from openalgo.database.master_contract_status_db import get_status, engine, MasterContractStatus
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=engine)
    session = Session()

    statuses = session.query(MasterContractStatus).all()
    total = 0
    print("--- Master Contract Status ---")
    if not statuses:
        print("No master contract records found.")

    for s in statuses:
        print(f"Broker: {s.broker}, Status: {s.status}, Symbols: {s.total_symbols}")
        if s.status == 'success':
            try:
                total += int(s.total_symbols)
            except: pass
    print(f"TOTAL_SYNCED={total}")
except Exception as e:
    print(f"Error checking master contracts: {e}")
finally:
    try:
        session.close()
    except:
        pass
