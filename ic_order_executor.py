#!/usr/bin/env python3
"""
Atomic IC wave executor with fill verification.
CLI: python3 ic_order_executor.py --wave 1 [--expiry 06MAR26] [--lots 12]
Outputs JSON: {"ok": true/false, "reason": "...", "lots": 12, ...}
"""
import time
import json
import requests
import sys
import argparse
from ic_config import OPENALGO_KEY, OPENALGO_URL, LOT_SIZE, SPAN_PER_LOT, get_next_expiry

N8N_WEBHOOK = "https://sayujks20417.app.n8n.cloud/webhook/ic-trading-alert"

def _post(ep, payload, key, timeout=8):
    try:
        r = requests.post(f"{OPENALGO_URL}/{ep}",
                          json={**payload, "apikey": key}, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def check_sell_margin(n_lots, key=OPENALGO_KEY):
    """Returns (ok, available, required). Required = n_lots × SPAN × 2 (both legs)."""
    data     = _post("funds", {}, key).get("data", {})
    avail    = float(data.get("availablecash", 0) or 0)
    required = n_lots * SPAN_PER_LOT * 2
    return (avail >= required), avail, required

def verify_fill(symbol, action, qty_min, key=OPENALGO_KEY, timeout=45):
    """
    Poll tradebook every 5s for up to timeout seconds.
    Returns (confirmed: bool, filled_qty: int, avg_price: float).
    Matches on symbol+action+qty (no timestamp filter — reliable enough for intraday).
    """
    sym_n    = symbol.upper().replace(" ", "").replace("-", "")
    deadline = time.time() + timeout
    while time.time() < deadline:
        trades = _post("tradebook", {}, key, timeout=8).get("data", []) or []
        for t in trades:
            if (str(t.get("symbol","")).upper().replace(" ","").replace("-","") == sym_n
                    and str(t.get("action","")).upper() == action
                    and int(t.get("quantity", 0)) >= qty_min):
                return True, int(t["quantity"]), float(t.get("average_price", 0))
        time.sleep(5)
    return False, 0, 0.0

def _place(sym, action, qty, strategy, key):
    return _post("placeorder", {
        "strategy": strategy, "symbol": sym, "action": action,
        "exchange": "NFO", "pricetype": "MARKET", "product": "MIS",
        "quantity": str(qty)
    }, key)

def _notify(event, data):
    try:
        requests.post(N8N_WEBHOOK, json={"event": event, **data}, timeout=4)
    except Exception:
        pass

def place_wave_atomic(wave_num, atm, qty, expiry, key=OPENALGO_KEY):
    """
    SELL CE → verify → SELL PE → verify → BUY CE → BUY PE.
    If any SELL fails: compensate (buy back confirmed SELLs) → return failure.
    BUY hedges only placed after BOTH SELLs confirmed.
    """
    tag   = f"IC_WAVE{wave_num}"
    s_ce  = f"NIFTY{expiry}{atm+100}CE"
    l_ce  = f"NIFTY{expiry}{atm+200}CE"
    s_pe  = f"NIFTY{expiry}{atm-100}PE"
    l_pe  = f"NIFTY{expiry}{atm-200}PE"
    res   = {"ok": False, "wave_num": wave_num, "qty": qty,
             "short_ce": atm+100, "short_pe": atm-100,
             "long_ce": atm+200, "long_pe": atm-200,
             "ce_avg": 0.0, "pe_avg": 0.0, "reason": ""}

    # LEG 1 — SELL CE short
    r1 = _place(s_ce, "SELL", qty, tag, key)
    if r1.get("status") != "success":
        res["reason"] = f"CE SELL OpenAlgo rejected: {r1}"; return res
    ok, fq, fa = verify_fill(s_ce, "SELL", qty, key, timeout=45)
    if not ok:
        res["reason"] = "CE SELL not in tradebook after 45s (Dhan RMS silent reject)"
        _notify("WAVE_SELL_FAIL", {"wave": wave_num, "leg": "CE", "reason": res["reason"]})
        return res
    res["ce_avg"] = fa

    # LEG 2 — SELL PE short
    time.sleep(0.5)
    r2 = _place(s_pe, "SELL", qty, tag, key)
    if r2.get("status") != "success":
        _place(s_ce, "BUY", qty, f"{tag}_COMP", key)   # compensate CE
        comp_ok, _, _ = verify_fill(s_ce, "BUY", qty, key, timeout=30)
        if not comp_ok:
            _notify("COMP_FAIL", {
                "wave": wave_num, "leg": "CE",
                "reason": "Compensation BUY for CE short NOT confirmed — OPEN SHORT POSITION"
            })
        res["reason"] = f"PE SELL OpenAlgo rejected (CE comp {'ok' if comp_ok else 'FAILED — CHECK NOW'}): {r2}"; return res
    ok, fq, fa = verify_fill(s_pe, "SELL", qty, key, timeout=45)
    if not ok:
        _place(s_ce, "BUY", qty, f"{tag}_COMP", key)   # compensate CE
        comp_ok, _, _ = verify_fill(s_ce, "BUY", qty, key, timeout=30)
        if not comp_ok:
            _notify("COMP_FAIL", {
                "wave": wave_num, "leg": "CE",
                "reason": "Compensation BUY for CE short NOT confirmed — OPEN SHORT POSITION"
            })
        res["reason"] = "PE SELL not in tradebook after 45s (CE comp " + ("ok" if comp_ok else "FAILED — CHECK NOW") + ")"
        _notify("WAVE_SELL_FAIL", {"wave": wave_num, "leg": "PE", "reason": res["reason"]})
        return res
    res["pe_avg"] = fa

    # LEGS 3+4 — BUY hedges (only after both SELLs confirmed)
    time.sleep(0.5)
    _place(l_ce, "BUY", qty, tag, key)
    time.sleep(0.5)
    _place(l_pe, "BUY", qty, tag, key)

    # Verify hedge fills (non-fatal: alert operator but don't abort — shorts already confirmed)
    ce_h_ok, _, _ = verify_fill(l_ce, "BUY", qty, key, timeout=30)
    pe_h_ok, _, _ = verify_fill(l_pe, "BUY", qty, key, timeout=30)
    if not ce_h_ok or not pe_h_ok:
        _notify("HEDGE_FILL_WARN", {
            "wave": wave_num,
            "ce_hedge": ce_h_ok, "pe_hedge": pe_h_ok,
            "reason": "BUY hedge not confirmed in tradebook — check positionbook NOW"
        })

    res["ok"] = True
    res["ce_hedge_ok"] = ce_h_ok
    res["pe_hedge_ok"] = pe_h_ok
    res["reason"] = (f"SELL fills confirmed; hedges CE={'✅' if ce_h_ok else '⚠️'} "
                     f"PE={'✅' if pe_h_ok else '⚠️'}")
    return res

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--wave",   type=int, required=True)
    p.add_argument("--expiry", type=str, default=None)
    p.add_argument("--lots",   type=int, default=None)
    args = p.parse_args()

    expiry = args.expiry or get_next_expiry()
    key    = OPENALGO_KEY

    # Fetch ATM
    oc = _post("optionchain", {"underlying": "NIFTY", "exchange": "NSE_INDEX",
                               "expiry_date": expiry, "strike_count": 4}, key)
    atm   = int(oc.get("atm_strike", 0) or 0)
    nifty = float(oc.get("underlying_ltp", 0) or 0)
    if atm == 0:
        print(json.dumps({"ok": False, "reason": "ATM=0 — market not open"})); sys.exit(1)

    # Lots sizing
    if args.lots:
        lots = args.lots
    else:
        data  = _post("funds", {}, key).get("data", {})
        avail = float(data.get("availablecash", 0) or 0)
        wf    = {1: 1.0, 2: 0.65, 3: 0.40}.get(args.wave, 1.0)
        lots  = max(4, min(40, int(avail * 0.78 / SPAN_PER_LOT * wf)))

    # Margin pre-check
    ok_m, avail, req = check_sell_margin(lots, key)
    if not ok_m:
        print(json.dumps({"ok": False, "reason": f"Insufficient margin: avail={avail:.0f} req={req:.0f}"}))
        sys.exit(1)

    result = place_wave_atomic(args.wave, atm, lots * LOT_SIZE, expiry, key)
    result.update({"lots": lots, "expiry": expiry, "nifty": nifty})
    print(json.dumps(result))
    sys.exit(0 if result["ok"] else 1)
