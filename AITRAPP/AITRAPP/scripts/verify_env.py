#!/usr/bin/env python3
"""Verify environment and connectivity before starting"""
import os
import sys
import socket
from typing import List, Tuple

required_env = [
    "KITE_API_KEY",
    "KITE_API_SECRET", 
    "KITE_ACCESS_TOKEN",
    "DATABASE_URL",
    "REDIS_URL",
    "APP_TIMEZONE"
]

required_ports: List[Tuple[str, int]] = [
    ("postgres", 5432),
    ("redis", 6379),
    ("localhost", 8000)
]


def check_env() -> bool:
    """Check required environment variables"""
    missing = [k for k in required_env if not os.getenv(k)]
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        return False
    print("✅ All required environment variables present")
    return True


def check_ports() -> bool:
    """Check required ports are accessible"""
    all_ok = True
    for host, port in required_ports:
        try:
            s = socket.create_connection((host, port), timeout=2)
            s.close()
            print(f"✅ {host}:{port} accessible")
        except Exception as e:
            print(f"❌ Port check failed: {host}:{port} -> {e}")
            all_ok = False
    return all_ok


def main():
    """Run all checks"""
    print("🔍 Verifying environment and connectivity...\n")
    
    env_ok = check_env()
    ports_ok = check_ports()
    
    if not env_ok or not ports_ok:
        print("\n❌ Verification failed")
        sys.exit(1)
    
    print("\n✅ All checks passed")
    sys.exit(0)


if __name__ == "__main__":
    main()

