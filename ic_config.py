#!/usr/bin/env python3
"""IC Trading Config — single source of truth. Import, don't copy."""
import os
import sys
from datetime import timedelta

_FALLBACK_KEY = "d524fa12cd71a21a2d8fa3a6be0ddd06b31f996e6d12bc0d60a110ad66939477"
OPENALGO_KEY  = os.environ.get("OPENALGO_API_KEY", _FALLBACK_KEY)
OPENALGO_URL  = "http://127.0.0.1:5002/api/v1"
LOT_SIZE      = 65
SPAN_PER_LOT  = 32_000   # MIS margin per IC spread lot

if OPENALGO_KEY == _FALLBACK_KEY and not os.environ.get("OPENALGO_API_KEY"):
    print("[ic_config] WARNING: using hardcoded key — set OPENALGO_API_KEY env var",
          file=sys.stderr, flush=True)

def get_next_expiry() -> str:
    """Return next NIFTY weekly expiry (Thursday) as DDMMMYY, e.g. '06MAR26'."""
    import pytz
    from datetime import datetime
    IST  = pytz.timezone("Asia/Kolkata")
    now  = datetime.now(IST)
    d    = now.date()
    days = (3 - d.weekday()) % 7           # days to next Thursday (0 if today)
    if days == 0 and (now.hour, now.minute) >= (15, 30):
        days = 7                            # past market close → next week
    return (d + timedelta(days=days)).strftime("%d%b%y").upper()

if __name__ == "__main__":
    print(f"Key: {OPENALGO_KEY[:8]}... | Expiry: {get_next_expiry()}")
