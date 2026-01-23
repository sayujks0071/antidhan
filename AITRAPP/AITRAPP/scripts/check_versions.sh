#!/usr/bin/env bash
# Quick version check script
set -euo pipefail

echo "📋 Dependency Versions"
echo "===================="
echo ""

if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✅ Using virtual environment"
else
    echo "⚠️  No virtual environment found - using system Python"
fi
echo ""

python - <<'PY'
import sys
try:
    import fastapi, uvicorn, sqlalchemy, alembic, redis, pandas, kiteconnect, prometheus_client, pydantic
    
    versions = {
        "fastapi": fastapi.__version__,
        "uvicorn": uvicorn.__version__,
        "sqlalchemy": sqlalchemy.__version__,
        "alembic": alembic.__version__,
        "redis": redis.__version__,
        "pandas": pandas.__version__,
        "kiteconnect": kiteconnect.__version__,
        "prometheus_client": prometheus_client.__version__,
        "pydantic": pydantic.__version__,
    }
    
    print("Installed versions:")
    for pkg, ver in sorted(versions.items()):
        print(f"  {pkg:20s} {ver}")
    
    print("\n✅ All core dependencies available")
    
except ImportError as e:
    print(f"❌ Missing dependency: {e}")
    print("\n💡 Install with: pip install -r requirements.txt")
    sys.exit(1)
PY

