import os, time, json, sys
from kiteconnect import KiteConnect
from packages.storage.database import SessionLocal
from packages.storage.models import AuditLog, AuditActionEnum


def main():
    api_key = os.environ["KITE_API_KEY"]
    access_token = os.environ.get("KITE_ACCESS_TOKEN")
    if not access_token:
        print("no access token set; nothing to revoke")
        return 0
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    try:
        kite.invalidate_access_token(access_token)
        ok = True
        msg = "revoked"
    except Exception as e:
        ok = False
        msg = f"revoke_failed: {e}"
    # audit
    try:
        db = SessionLocal()
        db.add(AuditLog(action=AuditActionEnum.FORCED_DAILY_LOGOUT, details={"ok":ok,"msg":msg,"ts":int(time.time())}))
        db.commit()
    except Exception:
        pass
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())


