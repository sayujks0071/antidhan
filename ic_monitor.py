#!/usr/bin/env python3
"""
NIFTY Iron Condor Live Monitor v3 — Dynamic Session + Rolling + Metrics
Overhaul after 24-FEB-2026: fully adaptive IC detection, sizing, exits, and rolls.

Key improvements (v2):
  - Dynamic IC structure detection from positionbook (no hardcoded strikes)
  - compute_wave_lots(): margin + VIX + gap-based sizing
  - check_dynamic_exit(): 5 exit conditions (premium%, proximity, trailing, VIX, SL tighten)
  - close_all_ic(): uses actual position symbols — no leg_map, no hardcoded strikes
  - OpenAlgo only for positions (no direct Dhan calls) — DNS failures do not affect monitor
  - PID file guard against duplicate monitor processes
  - 60s intervals day / 30s intervals gamma hour (2-3:10 PM)
  - SELL legs placed first in wave entries — prevents RMS rejection

New in v3:
  - roll_side(): NIFTY in 80–60pt zone + <40% captured → roll to ATM±150 instead of closing
  - compute_session_metrics(): auto-logs pnl, pct_captured, MAE, rolls to trade_history.jsonl
  - MAE tracking: state["mae"] = lowest MTM seen (most adverse excursion)
  - ROLL_ZONE = 80: new exit condition (wider than GAMMA_ZONE_PARTIAL=60)
  - 5 new state keys: ce_rolled, pe_rolled, mae, adjustments, regime_at_entry
"""
import time
import requests
import sys
import os
import signal
import re
from datetime import datetime
import pytz

# ─── PERSISTENT HTTP SESSION (connection reuse to localhost:5002) ─────────────
_http = requests.Session()
_http.headers.update({"Content-Type": "application/json"})

# ─── IC CONFIG (single source of truth) ──────────────────────────────────────
sys.path.insert(0, "/Users/mac/openalgo")
from ic_config import (OPENALGO_KEY as _IC_KEY, OPENALGO_URL as _IC_URL,
                       LOT_SIZE as _IC_LOT, SPAN_PER_LOT as _IC_SPAN,
                       get_next_expiry as _get_expiry)

# ─── CORE CONFIG ─────────────────────────────────────────────────────────────
IST            = pytz.timezone("Asia/Kolkata")
OPENALGO_URL   = _IC_URL    # from ic_config — single source of truth
OPENALGO_KEY   = _IC_KEY    # from ic_config — never hardcode here again
ACCESS_TOKEN   = (
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIj"
    "oxNzcyMDc2MjkwLCJpYXQiOjE3NzE5ODk4OTAsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2"
    "tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTA1MDA5MTM5In0.oG9G45vMBaXQCH7LGB3zE2uXJkpPy54YiI"
    "0-wjt1JXAU6lgwb_VBqbTSDYWCD_QVjM4fEEd8P-ipIJ_huQhSYA"
)
DHAN_CLIENT_ID = "1105009139"
DHAN_HEADERS   = {"access-token": ACCESS_TOKEN, "client-id": DHAN_CLIENT_ID}
LOG_FILE         = "/Users/mac/openalgo/ic_monitor.log"
PID_FILE         = "/tmp/ic_monitor.pid"
N8N_WEBHOOK_URL  = "https://sayujks20417.app.n8n.cloud/webhook/ic-trading-alert"

# ─── SESSION SCHEDULE ────────────────────────────────────────────────────────
HARD_CLOSE_TIME    = (15, 10)   # 3:10 PM — non-negotiable
PRE_CLOSE_TIME     = (15,  0)   # 3:00 PM — close if MTM > 0
AFTERNOON_CE_CLOSE = (14, 30)   # 2:30 PM — close CE gamma risk if MTM > ₹10K
WAVE2_TIME         = (11, 30)
WAVE3_TIME         = (14,  0)
WAVE2_MIN_MTM      = 0          # skip Wave 2 if session MTM < 0
WAVE3_MIN_MTM      = 20_000     # skip Wave 3 if session MTM < ₹20K

# ─── DYNAMIC SIZING CONFIG ───────────────────────────────────────────────────
SPAN_PER_SPREAD_LOT = _IC_SPAN   # from ic_config — single source of truth
LOT_SIZE            = _IC_LOT    # from ic_config — single source of truth
MAX_LOTS_HARD_CAP   = 40        # absolute cap on lots per wave
MIN_LOTS            = 4         # minimum viable IC size

# ─── DYNAMIC EXIT CONFIG ─────────────────────────────────────────────────────
PREMIUM_CLOSE_PCT    = 0.80     # ≥80% of entry premium captured → close all
PREMIUM_CLOSE_AFTER  = 0.60     # ≥60% AND time ≥ 2:00 PM → close all
PREMIUM_CLOSE_PROX   = 0.50     # ≥50% AND NIFTY within 50pt of short strike → close all
ROLL_ZONE            = 80       # NIFTY within 80pt of short + pct_captured<40% → roll side
GAMMA_ZONE_PARTIAL   = 60       # NIFTY within 60pt of short strike → close that side
GAMMA_ZONE_FULL      = 30       # NIFTY within 30pt of short strike → emergency close all
TRAIL_LOCK_THRESHOLD = 15_000   # trailing lock activates when peak_mtm > ₹15K
TRAIL_LOCK_PCT       = 0.65     # protect 65% of peak MTM (floor = peak × 0.65)
VIX_SPIKE_TRIGGER    = 0.15     # VIX rises 15%+ intraday → close all (IV explosion)
MAX_DAILY_LOSS       = -29_000  # absolute daily loss floor

# ─── STATE MACHINE ───────────────────────────────────────────────────────────
state = {
    "ic": {},               # populated by detect_ic_from_positions() at startup
    "peak_mtm": 0.0,        # highest MTM seen this session
    "entry_premium": 0.0,   # net credit received (updates after each wave)
    "pct_captured": 0.0,    # mtm / entry_premium
    "wave2_done": False,
    "wave3_done": False,
    "ce_closed": False,
    "pe_closed": False,
    "closed": False,
    "vix_entry": 0.0,       # India VIX at session start
    "current_vix": 0.0,     # latest VIX reading
    "nifty_entry": 0.0,     # NIFTY at Wave 1 entry
    "entry_time": None,
    "alerts_sent": set(),   # dedup: log each alert key only once
    "expiry": _get_expiry(),   # auto-computed from ic_config — no manual weekly update needed
    # ── v3 additions ─────────────────────────────────────────────────────────
    "ce_rolled": False,     # True after CE side has been rolled once this session
    "pe_rolled": False,     # True after PE side has been rolled once this session
    "mae": 0.0,             # Most Adverse Excursion: lowest MTM seen (≤0)
    "adjustments": 0,       # Count of rolls executed this session
    "regime_at_entry": "",  # Market regime at IC entry (set by ic_pre_entry.py or auto)
    "start_ts": None,       # time.time() at session start (for duration calc)
    "last_exit_reason": "", # reason stored before every break (for metrics log)
    # ── n8n notification cache (updated each monitor loop iteration) ──────────
    "last_nifty": 0.0,
    "last_mtm":   0.0,
    "last_dce":   0,
    # ── infrastructure health tracking ────────────────────────────────────────
    "consec_failures": 0,   # consecutive iterations where get_positions() returned {}
    "infra_retry_count": 0, # times consec_failures has reset (Fix A — retry instead of abort)
}


# ─── LOGGING ─────────────────────────────────────────────────────────────────
def log(msg, level="INFO"):
    now  = datetime.now(IST).strftime("%H:%M:%S")
    line = f"[{now}] {level:8s} | {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def alert_once(key, msg, level="WARN"):
    """Log a message only once per session (dedup by key)."""
    if key not in state["alerts_sent"]:
        log(msg, level)
        state["alerts_sent"].add(key)


# ─── STATE PERSISTENCE (G7 — survive monitor restarts) ───────────────────────
_STATE_FILE = "/Users/mac/openalgo/ic_state.json"


def save_wave_state():
    """Persist wave entry flags so a monitor restart doesn't duplicate or skip waves."""
    import json as _j
    try:
        rec = {
            "date":        datetime.now(IST).strftime("%Y-%m-%d"),
            "wave2_done":  state.get("wave2_done", False),
            "wave3_done":  state.get("wave3_done", False),
            "ce_closed":   state.get("ce_closed", False),
            "pe_closed":   state.get("pe_closed", False),
            "ce_rolled":   state.get("ce_rolled", False),
            "pe_rolled":   state.get("pe_rolled", False),
            "closed":      state.get("closed", False),
            "adjustments": state.get("adjustments", 0),
        }
        with open(_STATE_FILE, "w") as f:
            _j.dump(rec, f)
    except Exception as e:
        log(f"save_wave_state error: {e}", "WARN")


def load_wave_state():
    """On restart, reload today's wave flags to prevent duplicate or skipped wave entries."""
    import json as _j
    today = datetime.now(IST).strftime("%Y-%m-%d")
    try:
        with open(_STATE_FILE) as f:
            rec = _j.load(f)
        if rec.get("date") == today:
            for k in ("wave2_done", "wave3_done", "ce_closed", "pe_closed",
                      "ce_rolled", "pe_rolled", "closed", "adjustments"):
                if k in rec:
                    state[k] = rec[k]
            log(f"State restored from disk: wave2={state['wave2_done']} "
                f"wave3={state['wave3_done']} closed={state['closed']}", "INIT")
            return True
    except FileNotFoundError:
        pass
    except Exception as e:
        log(f"load_wave_state error: {e}", "WARN")
    return False


def notify_n8n(event: str, extra: dict = None):
    """
    Fire-and-forget webhook to n8n for real-time trading alerts.
    Called on key events: EXIT, ROLL_CE, ROLL_PE, PROFIT_TARGET, HARD_STOP, SESSION_START, MONITOR.
    Non-blocking (timeout=4s); failure is logged but NEVER crashes the monitor.
    """
    try:
        payload = {
            "event":        event,
            "nifty":        round(state.get("last_nifty", 0), 1),
            "mtm":          f"{state.get('last_mtm', 0):+.0f}",
            "pct_captured": f"{state.get('pct_captured', 0)*100:.1f}",
            "reason":       state.get("last_exit_reason", ""),
            "time":         datetime.now(IST).strftime("%H:%M IST"),
            "dce":          state.get("last_dce", 0),
            "peak_mtm":     f"{state.get('peak_mtm', 0):+.0f}",
            "ce_rolled":    state.get("ce_rolled", False),
            "pe_rolled":    state.get("pe_rolled", False),
        }
        if extra:
            payload.update(extra)
        _http.post(N8N_WEBHOOK_URL, json=payload, timeout=4)
    except Exception:
        pass   # never crash the monitor for notification failures


# ─── TIME HELPERS ─────────────────────────────────────────────────────────────
def ist_now():
    return datetime.now(IST)


def ist_hm():
    n = ist_now()
    return (n.hour, n.minute)


# ─── SYMBOL HELPERS ──────────────────────────────────────────────────────────
def normalize_sym(sym):
    """Uppercase + strip hyphens/spaces — handles both OA and Dhan formats."""
    return sym.upper().replace("-", "").replace(" ", "")


def extract_strike(sym):
    """Extract numeric strike price from option symbol.

    OpenAlgo format:  NIFTY05MAR2625500CE → strips NIFTY + month + CE/PE → '052625500' → last 5 = 25500
    Dhan format:      NIFTY-Mar2026-25500-CE → after normalize same path → 25500

    The year digits (e.g. '26') immediately precede the strike, so we strip prefix/suffix
    and take the last 4 or 5 digits which represent the strike price.
    """
    s = normalize_sym(sym)
    # Remove NIFTY prefix
    s = s.replace("NIFTY", "")
    # Remove month abbreviations (leaves day + year + strike digits)
    for mo in ("JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"):
        s = s.replace(mo, "")
    # Remove CE/PE suffix
    if s.endswith("CE"):
        s = s[:-2]
    elif s.endswith("PE"):
        s = s[:-2]
    # Remaining string is pure digits: DDYY + STRIKE, e.g. "052625500"
    # Strike is last 5 digits (NIFTY 20K–30K range), fallback last 4
    for n in (5, 4):
        if len(s) >= n:
            candidate = s[-n:]
            if candidate.isdigit():
                v = int(candidate)
                if 15000 <= v <= 35000:
                    return v
    return 0


def extract_expiry_from_sym(sym):
    """Extract DDMMMYY expiry string from OpenAlgo symbol.
    NIFTY05MAR2625500CE → 05MAR26
    Returns None if not detected (e.g. Dhan format).
    """
    s = normalize_sym(sym).replace("NIFTY", "")
    m = re.match(r'^(\d{2}[A-Z]{3}\d{2})', s)
    return m.group(1) if m else None


def get_opt_type(sym):
    """Return 'CE', 'PE', or '' from symbol."""
    s = normalize_sym(sym)
    if s.endswith("CE"):
        return "CE"
    if s.endswith("PE"):
        return "PE"
    return ""


def is_option_sym(sym):
    t = get_opt_type(sym)
    return t in ("CE", "PE")


# ─── INFRASTRUCTURE HEALTH CHECK ─────────────────────────────────────────────
INFRA_FAIL_LIMIT = 5   # consecutive OpenAlgo failures before monitor exits


def check_infrastructure():
    """Fail-fast check before monitor loop starts.
    Tests OpenAlgo on 127.0.0.1:5002 — exits immediately if down.
    Does NOT call api.dhan.co (DNS failures are not our problem to retry).
    """
    log("Pre-flight: checking OpenAlgo health at 127.0.0.1:5002 ...", "INIT")
    try:
        r = _http.post(
            f"{OPENALGO_URL}/funds",
            json={"apikey": OPENALGO_KEY},
            timeout=5
        )
        if r.status_code == 200:
            log("Pre-flight: OpenAlgo OK", "INIT")
            return True
        else:
            log(f"Pre-flight: OpenAlgo returned HTTP {r.status_code}", "ERROR")
    except requests.exceptions.ConnectionError:
        log("Pre-flight: OpenAlgo is DOWN — port 5002 not reachable", "ERROR")
    except requests.exceptions.Timeout:
        log("Pre-flight: OpenAlgo timed out (>5s) — server overloaded or frozen", "ERROR")
    except Exception as e:
        log(f"Pre-flight: OpenAlgo check failed: {e}", "ERROR")

    notify_n8n("INFRA_DOWN", {"detail": "OpenAlgo 5002 unreachable at monitor startup"})
    log("ABORTING: Fix OpenAlgo first, then restart ic_monitor.py", "ERROR")
    return False


# ─── API HELPERS ─────────────────────────────────────────────────────────────
def api_post(endpoint, data, timeout=8):
    try:
        r = _http.post(
            f"{OPENALGO_URL}/{endpoint}",
            json={**data, "apikey": OPENALGO_KEY},
            timeout=timeout
        )
        return r.json()
    except Exception as e:
        log(f"API error [{endpoint}]: {e}", "ERROR")
        return {}



def get_positions():
    """Fetch live positions via OpenAlgo positionbook (localhost only — no direct Dhan calls).
    Returns dict: {symbol: {qty, avg, ltp, mtm, sym}}
    Returns {} on failure — caller handles empty dict gracefully.
    """
    try:
        r    = _http.post(f"{OPENALGO_URL}/positionbook",
                          json={"apikey": OPENALGO_KEY}, timeout=8)
        data = r.json().get("data", [])
        if data is not None:
            pos = {}
            for p in data:
                sym = p.get("symbol", "")
                qty = int(p.get("quantity", 0))
                avg = float(p.get("average_price", 0) or 0)
                ltp = float(p.get("ltp", 0) or 0)
                mtm = (ltp - avg) * qty if ltp > 0 else float(p.get("pnl", 0) or 0)
                pos[sym] = {"qty": qty, "avg": avg, "ltp": ltp, "mtm": mtm, "sym": sym}
            return pos
    except Exception as e:
        log(f"OpenAlgo positionbook error: {e}", "ERROR")
    return {}


def enrich_ltps_from_quotes(positions):
    """Fetch live LTP via quotes API for any option position where ltp==0.

    Root cause fix (25-FEB-2026): OpenAlgo positionbook and Dhan positions API
    both return lastTradedPrice=0 for option positions. Without real LTPs,
    MTM=0 always → pct_captured=0 → ROLL_ZONE fires perpetually.

    This function queries /api/v1/quotes for each zero-LTP option position
    and patches p["ltp"] + recalculates p["mtm"] in-place.
    At 2-4 open legs × ~50ms each = <200ms overhead per loop iteration.
    """
    updated = 0
    for sym, p in positions.items():
        if p["qty"] == 0:
            continue
        if not is_option_sym(sym):
            continue
        if p.get("ltp", 0) > 0:
            continue   # already have a valid LTP — skip
        try:
            r   = api_post("quotes", {"symbol": sym, "exchange": "NFO"}, timeout=4)
            ltp = float(r.get("data", {}).get("ltp", 0) or 0)
            if ltp > 0:
                p["ltp"] = ltp
                # (ltp - avg) × qty: short qty<0 so loss when ltp rises
                p["mtm"] = (ltp - p["avg"]) * p["qty"]
                updated += 1
        except Exception as e:
            log(f"LTP enrich error [{sym}]: {e}", "WARN")
    return updated


_nifty_cache = 0.0   # last-known NIFTY — returned when optionchain times out
_vix_cache   = 0.0   # last-known VIX


def get_nifty_and_vix():
    """Fetch NIFTY LTP and India VIX via OpenAlgo option chain.
    Returns (nifty_ltp: float, vix: float).
    On timeout/failure, returns last-known cached values (never 0.0 after first success).
    """
    global _nifty_cache, _vix_cache
    expiry = state["expiry"]

    try:
        r = api_post("optionchain", {
            "underlying": "NIFTY", "exchange": "NSE_INDEX",
            "expiry_date": expiry, "strike_count": 4
        }, timeout=5)
        v = float(r.get("underlying_ltp", 0) or 0)
        if v > 0:
            _nifty_cache = v
    except Exception as e:
        log(f"NIFTY LTP error (using cached {_nifty_cache:.0f}): {e}", "WARN")

    try:
        rv = api_post("optionchain", {
            "underlying": "INDIAVIX", "exchange": "NSE_INDEX",
            "expiry_date": expiry, "strike_count": 1
        }, timeout=5)
        v = float(rv.get("underlying_ltp", 0) or 0)
        if v > 0:
            _vix_cache = v
    except Exception:
        pass   # VIX optional

    return _nifty_cache, _vix_cache


def get_available_margin():
    """Fetch available cash from OpenAlgo funds endpoint."""
    try:
        r = api_post("funds", {})
        return float(r.get("data", {}).get("availablecash", 0) or 0)
    except Exception as e:
        log(f"Funds error: {e}", "WARN")
        return 0.0


def place_order(symbol, action, qty, strategy="IC_MONITOR"):
    """Place a market order via OpenAlgo."""
    resp = api_post("placeorder", {
        "strategy": strategy, "symbol": symbol, "action": action,
        "exchange": "NFO", "pricetype": "MARKET",
        "product": "MIS", "quantity": str(qty)
    })
    ok  = resp.get("status") == "success"
    oid = resp.get("orderid", "?")
    log(
        f"ORDER: {action} {symbol} {qty} → {'✅ ' + oid if ok else '❌ ' + str(resp)}",
        "TRADE" if ok else "ERROR"
    )
    return ok


def verify_sell_fill(symbol: str, qty: int, timeout: int = 30) -> bool:
    """
    Poll OpenAlgo tradebook every 5s to confirm a SELL fill.
    Returns True if a SELL trade for symbol with qty >= qty is found within timeout.
    Uses 127.0.0.1:5002 only — no direct Dhan calls. (Fix C — F2/F3)
    """
    sym_n    = symbol.upper().replace(" ", "").replace("-", "")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            trades = api_post("tradebook", {}).get("data", []) or []
            for t in trades:
                if (str(t.get("symbol","")).upper().replace(" ","").replace("-","") == sym_n
                        and str(t.get("action","")).upper() == "SELL"
                        and int(t.get("quantity", 0)) >= qty):
                    return True
        except Exception as e:
            log(f"verify_sell_fill error [{symbol}]: {e}", "WARN")
        time.sleep(5)
    return False


# ─── DYNAMIC IC DETECTION ─────────────────────────────────────────────────────
def detect_ic_from_positions(positions):
    """Scan positionbook and auto-build IC structure dict from actual fills.
    Works for any IC — no hardcoded strikes or lot sizes.
    Returns IC dict, or None if no open IC detected.
    """
    shorts = []
    longs  = []

    for sym, p in positions.items():
        if p["qty"] == 0:
            continue
        if not is_option_sym(sym):
            continue
        strike   = extract_strike(sym)
        opt_type = get_opt_type(sym)
        if strike == 0:
            continue

        rec = {
            "sym":    sym,
            "qty":    p["qty"],
            "avg":    p["avg"],
            "ltp":    p["ltp"],
            "strike": strike,
            "type":   opt_type,
        }
        if p["qty"] < 0:
            rec["sl_price"] = p["avg"] * 2.0   # initial 2x SL
            shorts.append(rec)
        else:
            longs.append(rec)

    if not shorts:
        return None   # no shorts = no IC

    # Net credit received: sum(short_premium) - sum(long_premium)
    entry_premium = (
        sum(abs(s["qty"]) * s["avg"] for s in shorts) -
        sum(l["qty"] * l["avg"] for l in longs)
    )

    # Identify key strikes and barriers
    pe_shorts = [s for s in shorts if s["type"] == "PE"]
    ce_shorts = [s for s in shorts if s["type"] == "CE"]
    pe_longs  = [l for l in longs  if l["type"] == "PE"]
    ce_longs  = [l for l in longs  if l["type"] == "CE"]

    short_pe = min((s["strike"] for s in pe_shorts), default=0)
    short_ce = max((s["strike"] for s in ce_shorts), default=0)
    long_pe  = min((l["strike"] for l in pe_longs),  default=0)
    long_ce  = max((l["strike"] for l in ce_longs),  default=0)

    # Auto-detect expiry from first short's symbol (OpenAlgo format)
    for s in shorts:
        exp = extract_expiry_from_sym(s["sym"])
        if exp:
            state["expiry"] = exp
            break

    ic = {
        "shorts":              shorts,
        "longs":               longs,
        "pe_shorts":           pe_shorts,
        "ce_shorts":           ce_shorts,
        "pe_longs":            pe_longs,
        "ce_longs":            ce_longs,
        "entry_premium":       max(entry_premium, 1.0),  # avoid zero-division
        "short_pe_strike":     short_pe,
        "short_ce_strike":     short_ce,
        "nifty_lower_barrier": (long_pe - 50) if long_pe > 0 else 0,
        "nifty_upper_barrier": (long_ce + 50) if long_ce > 0 else 0,
    }
    return ic


# ─── DYNAMIC POSITION SIZING ─────────────────────────────────────────────────
def compute_wave_lots(wave_num, avail_margin, vix=14.0, gap_pct=0.0, session_mtm=0):
    """Compute recommended lot count for a given wave.

    Factors:
      - Available margin (78% utilisation rule)
      - VIX: ×0.5 if >20 (dangerous), ×0.75 if 16-20, ×1.0 if ≤16
      - Gap at open: ×0.70 if >1.5%, ×0.85 if 0.75-1.5%, ×1.0
      - Wave factor: W1=100%, W2=65%, W3=40% (successive waves smaller)

    Returns clamped int in [MIN_LOTS, MAX_LOTS_HARD_CAP].
    """
    if avail_margin <= 0:
        return MIN_LOTS

    base = int(avail_margin * 0.78 / SPAN_PER_SPREAD_LOT)

    vix_f  = 0.5  if vix       > 20   else (0.75 if vix       > 16   else 1.0)
    gap_f  = 0.70 if abs(gap_pct) > 1.5 else (0.85 if abs(gap_pct) > 0.75 else 1.0)
    wave_f = {1: 1.0, 2: 0.65, 3: 0.40}.get(wave_num, 0.40)

    lots = int(base * vix_f * gap_f * wave_f)
    return max(MIN_LOTS, min(MAX_LOTS_HARD_CAP, lots))


# ─── DYNAMIC EXIT CONDITIONS ─────────────────────────────────────────────────
def check_dynamic_exit(ic, positions, nifty, mtm, now):
    """Evaluate all 5 dynamic exit conditions.

    Returns (should_exit: bool, side: 'ALL'|'CE'|'PE', reason: str)
    side='ALL' → close full IC; side='CE'/'PE' → close that side only.
    """
    if not ic or state["closed"]:
        return False, "", ""

    hm           = (now.hour, now.minute)
    entry_prem   = ic.get("entry_premium", 1.0)
    pct_captured = mtm / entry_prem if entry_prem > 0 else 0.0
    short_pe     = ic.get("short_pe_strike", 0)
    short_ce     = ic.get("short_ce_strike", 0)
    peak         = state["peak_mtm"]

    state["pct_captured"] = pct_captured   # expose to status log

    # ── Condition 1: Premium capture milestones ──────────────────────────────
    if pct_captured >= PREMIUM_CLOSE_PCT:
        return True, "ALL", f"Premium captured {pct_captured:.1%} ≥ {PREMIUM_CLOSE_PCT:.0%}"

    if pct_captured >= PREMIUM_CLOSE_AFTER and hm >= (14, 0):
        return True, "ALL", f"Premium {pct_captured:.1%} ≥ {PREMIUM_CLOSE_AFTER:.0%} after 2PM"

    if pct_captured >= PREMIUM_CLOSE_PROX and nifty > 0:
        if short_pe and abs(nifty - short_pe) < 50:
            return True, "ALL", (
                f"Premium {pct_captured:.1%} + NIFTY {nifty:.0f} near short PE {short_pe}")
        if short_ce and abs(nifty - short_ce) < 50:
            return True, "ALL", (
                f"Premium {pct_captured:.1%} + NIFTY {nifty:.0f} near short CE {short_ce}")

    # ── Condition 1.5: Roll zone — side threatened but not yet at gamma ─────
    # Only roll if pct_captured < 40% (still early enough to benefit from roll)
    # and the side has NOT been rolled already this session (roll once per side)
    # Grace period: skip roll check for first 15 min (avoids false trigger at session open
    # when MTM=0 because LTPs haven't settled and NIFTY may be naturally close to short)
    _session_age_min = (time.time() - state["start_ts"]) / 60 if state.get("start_ts") else 999
    if nifty > 0 and _session_age_min >= 15:
        if short_ce > 0 and not state["ce_closed"] and not state["ce_rolled"]:
            dist_ce = short_ce - nifty
            if ROLL_ZONE >= dist_ce > GAMMA_ZONE_PARTIAL and pct_captured < 0.40:
                return True, "ROLL_CE", (
                    f"Roll CE: dist={dist_ce:.0f}pt capt={pct_captured:.1%} "
                    f"NIFTY={nifty:.0f} shortCE={short_ce}")
        if short_pe > 0 and not state["pe_closed"] and not state["pe_rolled"]:
            dist_pe = nifty - short_pe
            if ROLL_ZONE >= dist_pe > GAMMA_ZONE_PARTIAL and pct_captured < 0.40:
                return True, "ROLL_PE", (
                    f"Roll PE: dist={dist_pe:.0f}pt capt={pct_captured:.1%} "
                    f"NIFTY={nifty:.0f} shortPE={short_pe}")

    # ── Condition 2: Gamma danger zone ───────────────────────────────────────
    if nifty > 0:
        if short_ce > 0 and not state["ce_closed"]:
            dist_ce = short_ce - nifty
            if dist_ce <= GAMMA_ZONE_FULL:
                return True, "ALL", (
                    f"NIFTY {nifty:.0f} within {dist_ce:.0f}pt of short CE {short_ce} — EMERGENCY")
            if dist_ce <= GAMMA_ZONE_PARTIAL:
                return True, "CE", (
                    f"NIFTY {nifty:.0f} within {dist_ce:.0f}pt of short CE {short_ce} — close CE")

        if short_pe > 0 and not state["pe_closed"]:
            dist_pe = nifty - short_pe
            if dist_pe <= GAMMA_ZONE_FULL:
                return True, "ALL", (
                    f"NIFTY {nifty:.0f} within {dist_pe:.0f}pt of short PE {short_pe} — EMERGENCY")
            if dist_pe <= GAMMA_ZONE_PARTIAL:
                return True, "PE", (
                    f"NIFTY {nifty:.0f} within {dist_pe:.0f}pt of short PE {short_pe} — close PE")

    # ── Condition 3: Trailing profit lock ────────────────────────────────────
    if peak >= TRAIL_LOCK_THRESHOLD:
        floor = peak * TRAIL_LOCK_PCT
        if mtm < floor:
            return True, "ALL", (
                f"Trail lock: MTM {mtm:+,.0f} < floor {floor:,.0f} (peak={peak:,.0f})")

    # ── Condition 4: Per-leg SL with adaptive tightening ────────────────────
    for s in ic.get("shorts", []):
        ltp = s.get("ltp", 0)
        # Fresh LTP from current positions if stale
        if ltp <= 0:
            for sym, p in positions.items():
                if normalize_sym(sym) == normalize_sym(s["sym"]):
                    ltp = p["ltp"]
                    s["ltp"] = ltp
                    break
        if ltp <= 0:
            continue

        # Adaptive SL multiplier: tighten as we capture more premium
        sl_mult = 2.0
        if pct_captured >= 0.60:
            sl_mult = 1.5
        if hm >= (14, 0):
            sl_mult = 1.3

        sl_price = s["avg"] * sl_mult
        if ltp >= sl_price:
            return True, "ALL", (
                f"Short {s['sym'][-12:]} LTP {ltp:.2f} ≥ SL {sl_price:.2f} "
                f"({sl_mult}x avg {s['avg']:.2f})")

    # ── Condition 5: India VIX spike (IV explosion = IC killer) ─────────────
    vix_e = state.get("vix_entry", 0)
    vix_c = state.get("current_vix", 0)
    if vix_e > 0 and vix_c > 0:
        vix_rise = (vix_c - vix_e) / vix_e
        if vix_rise >= VIX_SPIKE_TRIGGER:
            return True, "ALL", (
                f"VIX spike: {vix_c:.2f} vs entry {vix_e:.2f} (+{vix_rise:.1%})")

    # ── Max daily loss ────────────────────────────────────────────────────────
    if mtm < MAX_DAILY_LOSS:
        return True, "ALL", f"Max daily loss {mtm:+,.0f} < limit {MAX_DAILY_LOSS:,}"

    return False, "", ""


# ─── CLOSE FUNCTIONS ─────────────────────────────────────────────────────────
def close_all_ic(positions, reason="MANUAL"):
    """Close all open IC option positions using actual symbols from positionbook.
    No hardcoded strikes — reverses every non-zero CE/PE position.
    """
    log(f"🔴 CLOSING ALL IC POSITIONS — {reason}", "TRADE")
    closed = 0
    tag = f"IC_CLOSE_{reason[:20].replace(' ', '_')}"

    for sym, p in positions.items():
        if p["qty"] == 0:
            continue
        if not is_option_sym(sym):
            continue   # skip equity/futures
        action = "BUY" if p["qty"] < 0 else "SELL"
        if place_order(sym, action, abs(p["qty"]), tag):
            closed += 1
        time.sleep(0.5)

    state["closed"] = True
    log(f"Close complete: {closed} legs exited", "TRADE")
    save_wave_state()   # persist — G7
    return closed


def safe_close_all(positions, reason, allow_continue_until=None):
    """
    Close all IC positions, then verify positionbook is flat. (Fix B — F4)
    If residual positions remain AND we are before allow_continue_until:
      → reset state["closed"]=False, update state["ic"], return False (don't break)
    Otherwise → compute_session_metrics + return True (break)
    """
    close_all_ic(positions, reason)
    time.sleep(3)

    fresh    = get_positions()
    residual = {s: p for s, p in fresh.items()
                if p["qty"] != 0 and is_option_sym(s)}

    if not residual:
        log("Post-close verify: positionbook flat. ✅", "TRADE")
        return True   # all clear — caller should break

    hm = ist_hm()
    if allow_continue_until and hm >= allow_continue_until:
        log(f"Post-close verify: {len(residual)} residual legs but past "
            f"{allow_continue_until[0]}:{allow_continue_until[1]:02d} — accepting.", "WARN")
        return True

    # Residual positions exist and we still have time — continue monitoring
    log(f"⚠️ Post-close: {len(residual)} positions remain — continuing monitor.", "WARN")
    for sym, p in residual.items():
        log(f"   Residual: {sym} qty={p['qty']}", "WARN")
    state["closed"] = False
    new_ic = detect_ic_from_positions(fresh)
    if new_ic:
        state["ic"] = new_ic
    notify_n8n("RESIDUAL_POSITIONS", {"count": len(residual), "reason": reason})
    return False   # caller must NOT break


def close_side(positions, side, reason="GAMMA_MGMT"):
    """Close only CE or PE side of the IC (partial close)."""
    log(f"🟡 CLOSING {side} SIDE — {reason}", "TRADE")
    closed = 0
    tag = f"IC_{side}_CLOSE"

    for sym, p in positions.items():
        if p["qty"] == 0:
            continue
        if not normalize_sym(sym).endswith(side):
            continue
        action = "BUY" if p["qty"] < 0 else "SELL"
        if place_order(sym, action, abs(p["qty"]), tag):
            closed += 1
        time.sleep(0.4)

    if side == "CE":
        state["ce_closed"] = True
    elif side == "PE":
        state["pe_closed"] = True

    log(f"{side} close complete: {closed} legs exited", "TRADE")
    return closed


# ─── ROLL ADJUSTMENT ─────────────────────────────────────────────────────────
def roll_side(positions, side, nifty, reason="ROLL"):
    """Roll a threatened IC side to wider strikes (ATM±150/±250).

    Called when NIFTY enters 60–80pt zone AND pct_captured < 40%.
    Steps:
      1. Close current CE/PE side (buy back short, sell back long) via close_side()
      2. Re-enter at ATM±150 short / ATM±250 long at 75% of original qty
      3. Mark state ce_rolled / pe_rolled (only 1 roll per side per session)
    """
    log(f"🔄 ROLLING {side} SIDE — {reason}", "ROLL")

    # Step 1: Close existing side
    close_side(positions, side, f"ROLL_CLOSE_{side}")

    time.sleep(1.5)   # let fills settle

    # Step 2: Compute new strikes from current NIFTY ATM
    atm_now      = round(nifty / 50) * 50
    expiry       = state["expiry"]
    suffix       = side   # "CE" or "PE"
    sign         = 1 if side == "CE" else -1
    short_offset = 150 * sign
    long_offset  = 250 * sign
    new_short    = atm_now + short_offset
    new_long     = atm_now + long_offset

    # 75% of original qty (round to lot boundary)
    orig_qty = 0
    for sym, p in positions.items():
        if p["qty"] < 0 and normalize_sym(sym).endswith(side):
            orig_qty = abs(p["qty"])
            break
    if orig_qty == 0:
        orig_qty = 780   # safe fallback

    qty_roll = max(LOT_SIZE, int(orig_qty * 0.75 / LOT_SIZE) * LOT_SIZE)

    short_sym = f"NIFTY{expiry}{new_short}{suffix}"
    long_sym  = f"NIFTY{expiry}{new_long}{suffix}"

    log(f"   Re-entering: SELL {short_sym} + BUY {long_sym} | qty={qty_roll}", "ROLL")

    # Step 3: Place new legs (SELL short first, then BUY long)
    ok_short = place_order(short_sym, "SELL", qty_roll, "IC_ROLL")
    time.sleep(0.8)
    ok_long  = place_order(long_sym,  "BUY",  qty_roll, "IC_ROLL")

    if ok_short:
        log(f"✅ Roll {side} complete: short={new_short} long={new_long} qty={qty_roll}", "ROLL")
    else:
        log(f"⚠️  Roll {side} short fill failed — check positions manually", "ROLL")

    return ok_short


def compute_session_metrics(final_mtm):
    """Compute and append session summary to trade_history.jsonl.

    Called automatically before every clean session exit (break).
    Records: pnl, pct_captured, MAE, duration_min, regime, rolls, exit_reason.
    """
    import json as _json

    ep  = state["ic"].get("entry_premium", 1.0) if state.get("ic") else 1.0
    pct = state.get("pct_captured", 0.0)

    start_ts = state.get("start_ts")
    duration = round((time.time() - start_ts) / 60, 1) if start_ts else 0.0

    record = {
        "date":             datetime.now(IST).strftime("%Y-%m-%d"),
        "strategy":         "NIFTY_IC_v3",
        "expiry":           state.get("expiry", ""),
        "pnl":              round(final_mtm, 2),
        "entry_premium":    round(ep, 2),
        "pct_captured":     round(pct, 4),
        "mae":              round(state.get("mae", 0.0), 2),
        "peak_mtm":         round(state.get("peak_mtm", 0.0), 2),
        "duration_min":     duration,
        "vix_entry":        state.get("vix_entry", 0.0),
        "regime_at_entry":  state.get("regime_at_entry", ""),
        "ce_rolled":        state.get("ce_rolled", False),
        "pe_rolled":        state.get("pe_rolled", False),
        "adjustments":      state.get("adjustments", 0),
        "exit_reason":      state.get("last_exit_reason", ""),
    }

    path = "/Users/mac/.openclaw/workspace/memory/trading/trade_history.jsonl"
    try:
        with open(path, "a") as f:
            f.write(_json.dumps(record) + "\n")
        log(
            f"METRICS: pnl={final_mtm:+.0f} capt={pct:.1%} "
            f"mae={record['mae']:+.0f} rolls={record['adjustments']} "
            f"dur={duration}min",
            "METRICS"
        )
    except Exception as e:
        log(f"Metrics write error: {e}", "WARN")


# ─── DYNAMIC WAVE ENTRY ───────────────────────────────────────────────────────
def enter_wave(wave_num, nifty, avail_margin, vix=14.0, session_mtm=0):
    """Place a new IC wave with dynamically sized lots.

    Strike structure: ATM±100 shorts, ATM±200 longs (consistent across waves).
    Order sequence: SELL CE → SELL PE → BUY CE → BUY PE (RMS fix: shorts first).
    Returns True if short legs filled successfully.
    """
    # Gate checks
    if wave_num == 2 and session_mtm < WAVE2_MIN_MTM:
        log(f"Wave {wave_num} gate failed: MTM {session_mtm:+,.0f} < {WAVE2_MIN_MTM}", "WAVE")
        return False
    if wave_num == 3 and session_mtm < WAVE3_MIN_MTM:
        log(f"Wave {wave_num} gate failed: MTM {session_mtm:+,.0f} < {WAVE3_MIN_MTM:,}", "WAVE")
        return False

    lots   = compute_wave_lots(wave_num, avail_margin, vix, 0.0, session_mtm)
    qty    = lots * LOT_SIZE
    atm    = round(nifty / 50) * 50
    expiry = state["expiry"]

    short_ce = f"NIFTY{expiry}{int(atm + 100)}CE"
    long_ce  = f"NIFTY{expiry}{int(atm + 200)}CE"
    short_pe = f"NIFTY{expiry}{int(atm - 100)}PE"
    long_pe  = f"NIFTY{expiry}{int(atm - 200)}PE"

    log(f"🟢 WAVE {wave_num}: NIFTY={nifty:.0f} ATM={atm} lots={lots} qty={qty}", "WAVE")
    log(f"   SELL {short_ce} + SELL {short_pe} | BUY {long_ce} + BUY {long_pe}", "WAVE")
    log(f"   Margin estimate: ₹{lots * SPAN_PER_SPREAD_LOT:,.0f}", "WAVE")

    # LEG 1: SELL CE short — verify fill before placing anything else (Fix C — F2/F3)
    ok1 = place_order(short_ce, "SELL", qty, f"IC_WAVE{wave_num}")
    if not ok1 or not verify_sell_fill(short_ce, qty, timeout=30):
        log(f"Wave {wave_num} ABORTED: CE SELL not confirmed in tradebook", "ERROR")
        notify_n8n("WAVE_FAIL", {"wave": wave_num, "reason": "CE SELL unconfirmed (Dhan RMS reject)"})
        return False

    # LEG 2: SELL PE short — verify; compensate CE if failed
    time.sleep(0.5)
    ok2 = place_order(short_pe, "SELL", qty, f"IC_WAVE{wave_num}")
    if not ok2 or not verify_sell_fill(short_pe, qty, timeout=30):
        log(f"Wave {wave_num} ABORTED: PE SELL unconfirmed — buying back CE short", "ERROR")
        place_order(short_ce, "BUY", qty, f"IC_WAVE{wave_num}_COMP")
        notify_n8n("WAVE_FAIL", {"wave": wave_num, "reason": "PE SELL unconfirmed — CE compensated"})
        return False

    # LEGS 3+4: BUY hedges — only placed after both SELLs confirmed in tradebook
    time.sleep(0.5)
    ok3 = place_order(long_ce, "BUY", qty, f"IC_WAVE{wave_num}")
    time.sleep(0.5)
    ok4 = place_order(long_pe, "BUY", qty, f"IC_WAVE{wave_num}")

    log(f"Wave {wave_num} fills: CE_short=✅ PE_short=✅ CE_long={ok3} PE_long={ok4}", "WAVE")
    return True


# ─── TOTAL MTM ────────────────────────────────────────────────────────────────
def total_mtm_all(positions):
    """Sum MTM across all open CE/PE positions."""
    return sum(
        p["mtm"] for p in positions.values()
        if p["qty"] != 0 and is_option_sym(p["sym"])
    )


# ─── MONITOR LOOP ─────────────────────────────────────────────────────────────
def monitor_loop():
    # ── Infrastructure pre-flight check ──────────────────────────────────────
    if not check_infrastructure():
        sys.exit(1)

    # ── PID guard: exit if another instance is running ──────────────────────
    if os.path.exists(PID_FILE):
        try:
            old_pid = int(open(PID_FILE).read().strip())
            if old_pid != os.getpid():
                try:
                    os.kill(old_pid, 0)   # check if process is alive
                    log(f"⚠️  Another monitor already running (PID {old_pid}). "
                        f"Kill it first: kill {old_pid}", "WARN")
                    sys.exit(1)
                except OSError:
                    pass  # old process is dead — OK to proceed
        except (ValueError, FileNotFoundError):
            pass

    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    log("=" * 70, "START")
    log("🚀 IC MONITOR v3 STARTED — Dynamic IC Session + Rolling + Metrics", "START")
    log(f"   Hard Close: {HARD_CLOSE_TIME[0]}:{HARD_CLOSE_TIME[1]:02d} IST | "
        f"Max Loss: ₹{abs(MAX_DAILY_LOSS):,}", "START")
    log(f"   Trail Lock: {TRAIL_LOCK_PCT:.0%} of peak (activates at ₹{TRAIL_LOCK_THRESHOLD:,})", "START")
    log(f"   Premium exits: {PREMIUM_CLOSE_PCT:.0%} full | "
        f"{PREMIUM_CLOSE_AFTER:.0%}+2PM | {PREMIUM_CLOSE_PROX:.0%}+proximity", "START")
    log(f"   Gamma zone: partial={GAMMA_ZONE_PARTIAL}pt / emergency={GAMMA_ZONE_FULL}pt", "START")
    log(f"   Roll zone: {ROLL_ZONE}pt (triggers roll if pct_captured<40%)", "START")
    log("=" * 70, "START")

    # ── Scan open positions for IC structure ─────────────────────────────────
    log("Scanning positionbook for IC structure...", "INIT")
    positions  = get_positions()
    open_count = sum(1 for p in positions.values() if p["qty"] != 0 and is_option_sym(p["sym"]))

    if open_count == 0:
        log("⚠️  No open option positions found. Start monitor AFTER Wave 1 fills.", "WARN")
        log("   Exiting cleanly.", "WARN")
        try:
            os.remove(PID_FILE)
        except FileNotFoundError:
            pass
        return

    ic = detect_ic_from_positions(positions)
    if ic is None:
        log("⚠️  Could not detect IC structure from positions. Check positionbook.", "WARN")
        try:
            os.remove(PID_FILE)
        except FileNotFoundError:
            pass
        return

    state["ic"]            = ic
    state["entry_premium"] = ic["entry_premium"]
    state["entry_time"]    = ist_now()
    state["start_ts"]      = time.time()   # for duration calculation in metrics
    load_wave_state()   # restore today's wave flags if monitor was restarted — G7

    log(f"IC DETECTED: {len(ic['shorts'])} shorts + {len(ic['longs'])} longs", "INIT")
    log(f"  Short PE: {ic['short_pe_strike']} | Short CE: {ic['short_ce_strike']}", "INIT")
    log(f"  Entry premium: ₹{ic['entry_premium']:,.0f}", "INIT")
    log(f"  NIFTY barriers: {ic['nifty_lower_barrier']}–{ic['nifty_upper_barrier']}", "INIT")
    log(f"  Expiry: {state['expiry']}", "INIT")

    # ── Fetch initial NIFTY + VIX ────────────────────────────────────────────
    nifty, vix = get_nifty_and_vix()
    if vix > 0:
        state["vix_entry"]   = vix
        state["current_vix"] = vix
    if nifty > 0:
        state["nifty_entry"] = nifty

    log(f"Session start: NIFTY={nifty:.1f} | VIX={vix:.2f}", "INIT")
    log(f"Wave schedule: W2@{WAVE2_TIME[0]}:{WAVE2_TIME[1]:02d} | "
        f"W3@{WAVE3_TIME[0]}:{WAVE3_TIME[1]:02d} | "
        f"Hard close@{HARD_CLOSE_TIME[0]}:{HARD_CLOSE_TIME[1]:02d}", "INIT")

    # ── Auto-initialize state flags based on current time + IC structure ─────
    hm_init = ist_hm()
    if hm_init >= WAVE2_TIME:
        state["wave2_done"] = True
        log("Wave 2 window already passed — marking done (skip)", "INIT")
    if hm_init >= WAVE3_TIME:
        state["wave3_done"] = True
        log("Wave 3 window already passed — marking done (skip)", "INIT")

    # If no PE side detected → mark PE as closed/rolled (pure CE spread)
    if ic.get("short_pe_strike", 0) == 0:
        state["pe_closed"] = True
        state["pe_rolled"] = True
        log("No PE shorts detected → marking PE side as closed/rolled", "INIT")

    # If CE short strike > ATM+150 → assume CE was already rolled this session
    if nifty > 0:
        atm_init = round(nifty / 50) * 50
        if ic.get("short_ce_strike", 0) > atm_init + 150:
            state["ce_rolled"] = True
            log(f"CE short at {ic.get('short_ce_strike',0)} > ATM+150 → "
                f"marking ce_rolled=True (already rolled once)", "INIT")

    interval  = 60   # default monitoring interval (seconds)
    iteration = 0

    # ── Notify n8n that monitor is live ───────────────────────────────────────
    notify_n8n("SESSION_START", {
        "expiry": state.get("expiry", ""),
        "nifty_entry": state.get("nifty_entry", 0),
        "vix_entry": state.get("vix_entry", 0),
    })

    while True:
        try:
            hm        = ist_hm()
            now       = ist_now()
            iteration += 1

            # ── Adaptive interval ─────────────────────────────────────────
            interval = 30 if hm >= (14, 0) else 60

            # ── Stop after market close ───────────────────────────────────
            if hm >= (15, 35):
                log("Market closed (15:35). Monitor exiting.", "DONE")
                state["last_exit_reason"] = "MARKET_CLOSED_15:35"
                compute_session_metrics(mtm)   # v3
                break

            # ── HARD CLOSE at 3:10 PM ─────────────────────────────────────
            if hm >= HARD_CLOSE_TIME and not state["closed"]:
                positions = get_positions()
                enrich_ltps_from_quotes(positions)
                mtm_final = total_mtm_all(positions)
                state["last_exit_reason"] = "HARD_CLOSE_3:10PM"
                if safe_close_all(positions, "HARD_CLOSE_3:10PM", allow_continue_until=(15, 35)):
                    compute_session_metrics(mtm_final)
                    break

            # ── PRE-CLOSE at 3:00 PM if MTM positive ─────────────────────
            if hm >= PRE_CLOSE_TIME and not state["closed"]:
                positions = get_positions()
                enrich_ltps_from_quotes(positions)
                nifty, vix = get_nifty_and_vix()
                mtm = total_mtm_all(positions)
                if mtm > 0:
                    log(f"3:00 PM pre-close: MTM={mtm:+,.0f} > 0 — closing all", "TRADE")
                    state["last_exit_reason"] = "PRE_CLOSE_3PM"
                    if safe_close_all(positions, "PRE_CLOSE_3PM", allow_continue_until=(15, 10)):
                        compute_session_metrics(mtm)
                        break
                else:
                    alert_once("preclose_wait",
                               f"3:00 PM: MTM={mtm:+,.0f}, holding until 3:10 hard close")

            # ── Fetch live data ───────────────────────────────────────────
            positions  = get_positions()

            # ── Consecutive failure guard ─────────────────────────────
            if not positions:
                state["consec_failures"] += 1
                log(f"OpenAlgo returned no positions "
                    f"(consecutive failures: {state['consec_failures']}/{INFRA_FAIL_LIMIT})",
                    "WARN")
                if state["consec_failures"] >= INFRA_FAIL_LIMIT:
                    state["infra_retry_count"] += 1
                    notify_n8n("INFRA_DOWN", {
                        "detail": f"OpenAlgo failed {INFRA_FAIL_LIMIT}× — "
                                  f"sleeping 120s (retry {state['infra_retry_count']}/3)"
                    })
                    log(f"INFRA PAUSE: retry {state['infra_retry_count']}/3. Sleeping 120s.", "ERROR")
                    if state["infra_retry_count"] >= 3:
                        log("ABORTING: 15 total failures. Genuine outage. Restart manually.", "ERROR")
                        break
                    # G6: Time-aware — don't sleep past hard close; attempt emergency close instead
                    _hm_now = ist_hm()
                    if _hm_now >= HARD_CLOSE_TIME:
                        log("INFRA OUTAGE at hard close time — attempting emergency close.", "ERROR")
                        try:
                            _raw = api_post("positionbook", {})
                            _pos = {p["symbol"]: {"qty": int(p.get("quantity", 0)),
                                                  "sym": p["symbol"], "mtm": 0.0, "ltp": 0.0}
                                    for p in (_raw.get("data") or []) if p.get("symbol")}
                            if any(v["qty"] != 0 for v in _pos.values()):
                                close_all_ic(_pos, "INFRA_HARD_CLOSE")
                        except Exception as _ex:
                            log(f"Emergency close attempt failed: {_ex}", "ERROR")
                            notify_n8n("EMERGENCY_CLOSE_FAIL", {"reason": str(_ex)})
                        break
                    time.sleep(120)
                    state["consec_failures"] = 0
                time.sleep(interval)
                continue
            else:
                state["consec_failures"] = 0   # reset on success

            enrich_ltps_from_quotes(positions)   # fix: positionbook LTP always 0
            nifty, vix = get_nifty_and_vix()
            mtm        = total_mtm_all(positions)

            if vix > 0:
                state["current_vix"] = vix
            if mtm > state["peak_mtm"]:
                state["peak_mtm"] = mtm
            if mtm < state["mae"]:              # v3: track most adverse excursion
                state["mae"] = mtm

            # Update LTPs in IC structure for SL checks
            ic = state["ic"]
            if ic:
                for leg_list in (ic.get("shorts", []), ic.get("longs", [])):
                    for leg in leg_list:
                        for sym, p in positions.items():
                            if normalize_sym(sym) == normalize_sym(leg["sym"]):
                                leg["ltp"] = p["ltp"]
                                break

            # ── Compute pct captured for status log ──────────────────────
            ep = ic.get("entry_premium", 1.0) if ic else 1.0
            state["pct_captured"] = mtm / ep if ep > 0 else 0.0

            # ── Status log ────────────────────────────────────────────────
            short_pe = ic.get("short_pe_strike", 0) if ic else 0
            short_ce = ic.get("short_ce_strike", 0) if ic else 0
            d_pe = f" dPE={nifty - short_pe:.0f}" if short_pe and nifty else ""
            d_ce = f" dCE={short_ce - nifty:.0f}" if short_ce and nifty else ""
            vix_str = f"VIX={vix:.2f}" if vix > 0 else "VIX=?"
            log(
                f"NIFTY={nifty:.1f} {vix_str} | MTM={mtm:+,.0f} | "
                f"Peak={state['peak_mtm']:+,.0f} | Capt={state['pct_captured']:.1%} |"
                f"{d_pe}{d_ce}",
                "MONITOR"
            )
            # ── Update n8n notification cache ─────────────────────────────
            state["last_nifty"] = nifty
            state["last_mtm"]   = mtm
            state["last_dce"]   = int(short_ce - nifty) if short_ce and nifty else 0
            # ── Heartbeat to n8n every 10 iterations (≈10 min) ───────────
            if iteration % 10 == 0:
                notify_n8n("MONITOR")

            # ── DYNAMIC EXIT CHECK ────────────────────────────────────────
            if not state["closed"] and ic:
                do_exit, side, reason = check_dynamic_exit(ic, positions, nifty, mtm, now)
                if do_exit:
                    if side == "ALL":
                        log(f"🔴 EXIT ALL: {reason}", "EXIT")
                        state["last_exit_reason"] = reason
                        notify_n8n("EXIT_ALL", {"reason": reason})
                        if safe_close_all(positions, reason, allow_continue_until=(15, 10)):
                            compute_session_metrics(mtm)
                            break
                    elif side in ("ROLL_CE", "ROLL_PE"):
                        # v3: Roll instead of close — keep IC alive at wider strikes
                        actual = side.replace("ROLL_", "")
                        log(f"🔄 ROLL {actual}: {reason}", "EXIT")
                        notify_n8n(f"ROLL_{actual}", {"reason": reason})
                        roll_side(positions, actual, nifty, reason)
                        state[f"{actual.lower()}_rolled"] = True
                        state["adjustments"] += 1
                        save_wave_state()   # persist — G7
                        # Re-detect IC with new rolled positions
                        time.sleep(2)
                        positions = get_positions()
                        new_ic = detect_ic_from_positions(positions)
                        if new_ic:
                            state["ic"]            = new_ic
                            state["entry_premium"] = new_ic["entry_premium"]
                            ic                     = new_ic
                            log(f"IC refreshed after roll: premium=₹{new_ic['entry_premium']:,.0f}",
                                "ROLL")
                        # Do NOT break — continue monitoring with new IC structure
                    elif side == "CE" and not state["ce_closed"]:
                        log(f"🟡 EXIT CE: {reason}", "EXIT")
                        notify_n8n("EXIT_CE", {"reason": reason})
                        close_side(positions, "CE", reason)
                    elif side == "PE" and not state["pe_closed"]:
                        log(f"🟡 EXIT PE: {reason}", "EXIT")
                        notify_n8n("EXIT_PE", {"reason": reason})
                        close_side(positions, "PE", reason)

            # ── AFTERNOON CE CLOSE at 2:30 PM (gamma risk) ───────────────
            if (hm >= AFTERNOON_CE_CLOSE and not state["ce_closed"]
                    and not state["closed"] and mtm > 10_000):
                alert_once("aft_ce_close",
                           f"2:30 PM CE gamma close: MTM={mtm:+,.0f} > ₹10K")
                close_side(positions, "CE", "THETA_DECAY_2:30PM")

            # ── WAVE 2 at 11:30 AM ────────────────────────────────────────
            if hm >= WAVE2_TIME and not state["wave2_done"] and not state["closed"]:
                atm_now  = round(nifty / 50) * 50 if nifty > 0 else 0
                in_range = (nifty > 0 and abs(nifty - atm_now) < 150)
                log(f"Wave2 check: MTM={mtm:+,.0f} | "
                    f"NIFTY={nifty:.0f} in_range={in_range}", "WAVE2")
                if mtm >= WAVE2_MIN_MTM and in_range:
                    avail = get_available_margin()
                    ok    = enter_wave(2, nifty, avail, vix if vix > 0 else 14.0, mtm)
                    if ok:
                        # Refresh IC to include Wave 2 positions
                        time.sleep(2)
                        positions = get_positions()
                        new_ic = detect_ic_from_positions(positions)
                        if new_ic:
                            state["ic"]            = new_ic
                            state["entry_premium"] = new_ic["entry_premium"]
                            log(f"IC refreshed after Wave2: premium=₹{new_ic['entry_premium']:,.0f}",
                                "WAVE2")
                else:
                    log("Wave2 skipped: conditions not met", "WAVE2")
                state["wave2_done"] = True   # don't retry regardless
                save_wave_state()   # persist — G7

            # ── WAVE 3 at 2:00 PM ────────────────────────────────────────
            if hm >= WAVE3_TIME and not state["wave3_done"] and not state["closed"]:
                atm_now  = round(nifty / 50) * 50 if nifty > 0 else 0
                in_range = (nifty > 0 and abs(nifty - atm_now) < 150)
                log(f"Wave3 check: MTM={mtm:+,.0f} | "
                    f"NIFTY={nifty:.0f} in_range={in_range}", "WAVE3")
                if mtm >= WAVE3_MIN_MTM and in_range:
                    avail = get_available_margin()
                    ok    = enter_wave(3, nifty, avail, vix if vix > 0 else 14.0, mtm)
                    if ok:
                        time.sleep(2)
                        positions = get_positions()
                        new_ic = detect_ic_from_positions(positions)
                        if new_ic:
                            state["ic"]            = new_ic
                            state["entry_premium"] = new_ic["entry_premium"]
                            log(f"IC refreshed after Wave3: premium=₹{new_ic['entry_premium']:,.0f}",
                                "WAVE3")
                else:
                    log("Wave3 skipped: conditions not met", "WAVE3")
                state["wave3_done"] = True
                save_wave_state()   # persist — G7

        except KeyboardInterrupt:
            log("Monitor stopped by user (Ctrl+C)", "STOP")
            state["last_exit_reason"] = "USER_INTERRUPT"
            compute_session_metrics(mtm if "mtm" in dir() else 0.0)   # v3
            break
        except Exception as e:
            log(f"Monitor iteration error: {e}", "ERROR")
            import traceback
            log(traceback.format_exc()[:500], "ERROR")

        time.sleep(interval)

    # ── Cleanup PID file ─────────────────────────────────────────────────────
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass
    log("IC Monitor v3 exiting.", "DONE")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    monitor_loop()
