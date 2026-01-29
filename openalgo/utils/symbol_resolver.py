import logging
import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import func
from openalgo.database.symbol import SymToken, db_session

logger = logging.getLogger(__name__)

class SymbolResolver:
    """
    Central Symbol Resolver for OpenAlgo.
    Resolves human-friendly strategy configs into broker-valid instrument tokens/symbols.
    """

    @staticmethod
    def parse_expiry(expiry_str: str) -> Optional[datetime.date]:
        """Parses DD-MMM-YY expiry string to date object."""
        try:
            return datetime.datetime.strptime(expiry_str, "%d-%b-%y").date()
        except ValueError:
            try:
                return datetime.datetime.strptime(expiry_str, "%d-%b-%Y").date()
            except ValueError:
                return None

    @classmethod
    def get_valid_expiries(cls, underlying: str, exchange: str = "NFO") -> List[datetime.date]:
        """Fetches and returns sorted valid future expiries for the underlying."""
        try:
            results = db_session.query(SymToken.expiry).filter(
                SymToken.name == underlying,
                SymToken.exchange == exchange,
                SymToken.expiry != '',
                SymToken.expiry != None
            ).distinct().all()

            expiries = []
            today = datetime.date.today()

            for (exp_str,) in results:
                exp_date = cls.parse_expiry(exp_str)
                if exp_date and exp_date >= today:
                    expiries.append(exp_date)

            return sorted(expiries)
        except Exception as e:
            logger.error(f"Error fetching expiries for {underlying}: {e}")
            return []

    @classmethod
    def resolve_option_symbol(cls, underlying: str, expiry_pref: str = "weekly",
                              strike_rule: str = "ATM", option_type: str = "CE",
                              spot_price: float = None) -> Optional[Dict[str, Any]]:
        """
        Resolves an Option symbol.

        Args:
            underlying: e.g., "NIFTY", "BANKNIFTY"
            expiry_pref: "weekly" (nearest), "monthly" (current month end), "next_weekly"
            strike_rule: "ATM", "ITM+1", "OTM-2", or specific strike price (float/int)
            option_type: "CE" or "PE"
            spot_price: Required for ATM/ITM/OTM calculation if strike_rule is dynamic

        Returns:
            Dict containing 'symbol', 'token', 'strike', 'expiry', etc.
        """
        try:
            expiries = cls.get_valid_expiries(underlying, "NFO")
            if not expiries:
                logger.error(f"No expiries found for {underlying}")
                return None

            # Expiry Selection
            selected_expiry = None
            if expiry_pref == "weekly" or expiry_pref == "nearest":
                selected_expiry = expiries[0]
            elif expiry_pref == "next_weekly":
                selected_expiry = expiries[1] if len(expiries) > 1 else expiries[0]
            elif expiry_pref == "monthly":
                # Find last expiry of the current month
                current_month = expiries[0].month
                monthly_expiry = None
                for exp in expiries:
                    if exp.month == current_month:
                        monthly_expiry = exp
                    else:
                        break # Moved to next month
                selected_expiry = monthly_expiry or expiries[0]
            else:
                selected_expiry = expiries[0] # Default

            expiry_str = selected_expiry.strftime("%d-%b-%y").upper()

            # Strike Selection
            target_strike = None

            # Fetch all strikes for this expiry
            strikes_query = db_session.query(SymToken.strike).filter(
                SymToken.name == underlying,
                SymToken.exchange == "NFO",
                SymToken.expiry == expiry_str,
                SymToken.instrumenttype == option_type
            ).distinct().all()

            available_strikes = sorted([s[0] for s in strikes_query])

            if not available_strikes:
                logger.error(f"No strikes found for {underlying} {expiry_str}")
                return None

            if isinstance(strike_rule, (int, float)):
                # Exact strike requested
                target_strike = float(strike_rule)
                # Verify existence (approx match)
                closest = min(available_strikes, key=lambda x: abs(x - target_strike))
                if abs(closest - target_strike) > 5: # Tolerance
                    logger.warning(f"Exact strike {target_strike} not found, using closest {closest}")
                target_strike = closest

            elif spot_price is not None:
                # Dynamic Strike
                # First find ATM
                atm_strike = min(available_strikes, key=lambda x: abs(x - spot_price))
                atm_index = available_strikes.index(atm_strike)

                offset = 0
                if "ITM" in strike_rule:
                    # ITM for CE is lower strike, for PE is higher strike
                    try:
                        val = int(strike_rule.replace("ITM", "").strip() or 0)
                        offset = -val if option_type == "CE" else val
                    except: offset = 0
                elif "OTM" in strike_rule:
                    try:
                        val = int(strike_rule.replace("OTM", "").strip() or 0)
                        offset = val if option_type == "CE" else -val
                    except: offset = 0

                target_index = atm_index + offset
                target_index = max(0, min(target_index, len(available_strikes) - 1))
                target_strike = available_strikes[target_index]
            else:
                logger.error("Spot price required for dynamic strike calculation")
                return None

            # Fetch final instrument
            token_obj = db_session.query(SymToken).filter(
                SymToken.name == underlying,
                SymToken.exchange == "NFO",
                SymToken.expiry == expiry_str,
                SymToken.instrumenttype == option_type,
                SymToken.strike == target_strike
            ).first()

            if token_obj:
                return {
                    "symbol": token_obj.symbol,
                    "token": token_obj.token,
                    "exchange": token_obj.exchange,
                    "expiry": token_obj.expiry,
                    "strike": token_obj.strike,
                    "lotsize": token_obj.lotsize
                }
            return None

        except Exception as e:
            logger.error(f"Error resolving option symbol: {e}")
            return None

    @classmethod
    def resolve_mcx_symbol(cls, underlying: str, prefer_mini: bool = True) -> Optional[Dict[str, Any]]:
        """
        Resolves MCX Future symbol, preferring MINI contracts if requested.
        Fallback to smallest lot size if MINI not found.
        """
        try:
            # Get valid expiries for this commodity
            # MCX symbols in SymToken might be stored with name 'CRUDEOIL' or 'CRUDEOILM'
            # We search by name starting with underlying

            query = db_session.query(SymToken).filter(
                SymToken.exchange == "MCX",
                SymToken.instrumenttype == "FUT",
                SymToken.name.like(f"{underlying}%")
            )

            results = query.all()
            if not results:
                logger.error(f"No MCX instruments found for {underlying}")
                return None

            # Filter for valid expiries (future only)
            valid_instruments = []
            today = datetime.date.today()

            for res in results:
                exp_date = cls.parse_expiry(res.expiry)
                if exp_date and exp_date >= today:
                    valid_instruments.append({
                        "obj": res,
                        "date": exp_date,
                        "is_mini": "MINI" in res.symbol or res.symbol.endswith("M")
                    })

            if not valid_instruments:
                return None

            # Sort by date
            valid_instruments.sort(key=lambda x: x["date"])
            nearest_expiry_date = valid_instruments[0]["date"]

            # Filter for nearest expiry only (usually we trade nearest)
            # Or should we look for *any* mini? Usually nearest mini.

            # Let's group by expiry date
            expiry_groups = {}
            for item in valid_instruments:
                d = item["date"]
                if d not in expiry_groups: expiry_groups[d] = []
                expiry_groups[d].append(item)

            # Look at nearest expiry first
            nearest_items = expiry_groups[min(expiry_groups.keys())]

            selected = None
            if prefer_mini:
                # Try to find MINI in nearest expiry
                minis = [x for x in nearest_items if x["is_mini"]]
                if minis:
                    selected = minis[0]["obj"]
                else:
                    logger.info(f"MCX MINI not found for {underlying} nearest expiry, checking lot sizes.")
                    # Fallback to smallest lot size
                    nearest_items.sort(key=lambda x: x["obj"].lotsize)
                    selected = nearest_items[0]["obj"]
            else:
                # Prefer standard (largest lot size? or just standard name?)
                # Usually standard doesn't have 'M' suffix
                standards = [x for x in nearest_items if not x["is_mini"]]
                if standards:
                    selected = standards[0]["obj"]
                else:
                    selected = nearest_items[0]["obj"]

            if selected:
                return {
                    "symbol": selected.symbol,
                    "token": selected.token,
                    "exchange": selected.exchange,
                    "expiry": selected.expiry,
                    "lotsize": selected.lotsize
                }
            return None

        except Exception as e:
            logger.error(f"Error resolving MCX symbol: {e}")
            return None

    @classmethod
    def validate_symbol(cls, symbol: str, exchange: str) -> bool:
        """Checks if a specific symbol exists in DB."""
        exists = db_session.query(SymToken).filter(
            SymToken.symbol == symbol,
            SymToken.exchange == exchange
        ).first()
        return exists is not None
