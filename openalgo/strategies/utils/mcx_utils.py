import re
from datetime import date

def format_mcx_symbol(underlying, expiry_date, mini=False):
    """
    Format MCX Futures Symbol strictly according to canonical rules.
    Underlying + (M if mini) + DD + MMM + YY + FUT
    DD is zero-padded.
    MMM is uppercase.
    YY is 2-digit year.
    """
    symbol = underlying.upper()
    if mini:
        symbol += "M"

    day_str = f"{expiry_date.day:02d}"
    month_str = expiry_date.strftime("%b").upper()
    year_str = expiry_date.strftime("%y")

    return f"{symbol}{day_str}{month_str}{year_str}FUT"

def normalize_mcx_string(symbol_str):
    """
    Normalize an existing MCX symbol string.
    e.g. GOLDM 5 FEB 26 FUT -> GOLDM05FEB26FUT
    """
    match = re.match(r'^([A-Z]+)(\d{1,2})([A-Z]{3})(\d{2})FUT$', symbol_str, re.IGNORECASE)
    if not match:
        return symbol_str

    sym = match.group(1).upper()
    day = int(match.group(2))
    month = match.group(3).upper()
    year = match.group(4)

    return f"{sym}{day:02d}{month}{year}FUT"
