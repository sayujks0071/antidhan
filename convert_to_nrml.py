#!/usr/bin/env python3
"""
Convert bear call spread from MIS (INTRADAY) → CNC (NRML/carry-forward)
Run at 2:50 PM if unrealized MTM < ₹10,234 (not yet at breakeven for day)
After conversion: hold to 02 MAR expiry for full ₹19,744 potential
"""
import requests
from datetime import datetime
import pytz

IST   = pytz.timezone("Asia/Kolkata")
TOKEN = ("eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIj"
         "oxNzcyMDc2MjkwLCJpYXQiOjE3NzE5ODk4OTAsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2"
         "tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTA1MDA5MTM5In0.oG9G45vMBaXQCH7LGB3zE2uXJkpPy54YiI"
         "0-wjt1JXAU6lgwb_VBqbTSDYWCD_QVjM4fEEd8P-ipIJ_huQhSYA")
HEADERS = {
    "access-token":  TOKEN,
    "client-id":     "1105009139",
    "Content-Type":  "application/json"
}

POSITIONS = [
    # sym                              secId    qty  posType
    ("NIFTY-Mar2026-25750-CE",        "54973", 585, "SHORT"),
    ("NIFTY-Mar2026-25850-CE",        "54977", 585, "LONG"),
]

print(f"[{datetime.now(IST).strftime('%H:%M:%S')}] Converting MIS → CNC (carry-forward to 02 MAR expiry)")
print("="*65)

success = 0
for sym, sec_id, qty, pos_type in POSITIONS:
    payload = {
        "dhanClientId":    "1105009139",
        "fromProductType": "INTRADAY",
        "toProductType":   "CNC",
        "exchangeSegment": "NSE_FNO",
        "positionType":    pos_type,
        "securityId":      sec_id,
        "convertQty":      qty,
        "tradingSymbol":   sym
    }
    r = requests.post("https://api.dhan.co/v2/positions/convert",
                      headers=HEADERS, json=payload, timeout=8)
    ok = r.status_code == 200
    print(f"  {'✅' if ok else '❌'} {sym:35s} {pos_type:5s} → {'OK' if ok else r.text[:80]}")
    if ok:
        success += 1

print()
if success == 2:
    print("✅ Both legs converted to CNC. Positions will carry to 02 MAR 2026.")
    print("   Stop ic_monitor.py (MIS monitor no longer needed).")
    print("   Bear spread: Short 25750CE / Long 25850CE, 585 qty")
    print("   Max profit at expiry (NIFTY < 25750): ₹19,744 unrealized → net +₹9,510")
else:
    print(f"⚠️  Only {success}/2 legs converted. Check Dhan app manually.")
