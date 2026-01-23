"""NSE Holiday Provider"""
import json
import os
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Set, Any
import requests
import structlog

from packages.core.config import settings

logger = structlog.get_logger(__name__)

NSE_HOLIDAY_URL = "https://www.nseindia.com/api/holiday-master?type=trading"
NSE_HOMEPAGE_URL = "https://www.nseindia.com"

# Headers to mimic a browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
}


def extract_segment_dates(payload: Dict[str, Any], segment: str = "FO") -> Set[str]:
    """
    Extract holiday dates for a specific segment from NSE API payload.

    Args:
        payload: The JSON payload from NSE API
        segment: The segment key (default: FO)

    Returns:
        Set of dates in YYYY-MM-DD format
    """
    if not payload or segment not in payload:
        logger.warning("Segment not found in payload", segment=segment)
        return set()

    holidays = set()
    for item in payload[segment]:
        if "tradingDate" in item:
            try:
                # Parse DD-Mmm-YYYY (e.g., 26-Jan-2026)
                dt = datetime.strptime(item["tradingDate"], "%d-%b-%Y")
                holidays.add(dt.date().isoformat())
            except ValueError as e:
                logger.error("Failed to parse date", date=item.get("tradingDate"), error=str(e))

    return holidays


def fetch_nse_holidays(timeout: int = 5, retries: int = 2) -> Optional[Dict[str, Any]]:
    """
    Fetch holidays from NSE API with retries and session warm-up.

    Args:
        timeout: Request timeout in seconds
        retries: Number of retries

    Returns:
        JSON payload or None if failed
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    for attempt in range(retries + 1):
        try:
            # Warm-up request to homepage to get cookies
            logger.debug("Warming up session", url=NSE_HOMEPAGE_URL)
            session.get(NSE_HOMEPAGE_URL, timeout=timeout)

            # Fetch holidays
            logger.info("Fetching NSE holidays", url=NSE_HOLIDAY_URL, attempt=attempt+1)
            response = session.get(NSE_HOLIDAY_URL, timeout=timeout)
            response.raise_for_status()

            return response.json()
        except Exception as e:
            logger.warning("Fetch failed", error=str(e), attempt=attempt+1)
            if attempt < retries:
                time.sleep(1)

    return None


def save_cache(payload: Dict[str, Any], filepath: str) -> None:
    """Save payload to cache file"""
    try:
        dirname = os.path.dirname(filepath)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2)
        logger.info("Cache saved", filepath=filepath)
    except Exception as e:
        logger.error("Failed to save cache", error=str(e), filepath=filepath)


def load_cache(filepath: str) -> Optional[Dict[str, Any]]:
    """Load payload from cache file"""
    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load cache", error=str(e), filepath=filepath)
        return None


def get_trading_holidays(
    segment: str = None,
    cache_path: str = None,
    refresh_days: int = None,
    allow_network: bool = None
) -> Set[str]:
    """
    Get trading holidays with fallback strategy:
    1. Fresh Cache -> Use
    2. Stale Cache (if refresh fails) -> Use
    3. Seed File -> Use

    Args:
        segment: Market segment (default: settings.NSE_HOLIDAY_SEGMENT)
        cache_path: Path to cache file (default: settings.NSE_HOLIDAY_CACHE_PATH)
        refresh_days: Cache validity in days (default: settings.NSE_HOLIDAY_REFRESH_DAYS)
        allow_network: whether to allow network calls (default: settings.NSE_HOLIDAY_ALLOW_NETWORK)

    Returns:
        Set of holiday dates in YYYY-MM-DD format
    """
    segment = segment or settings.nse_holiday_segment
    cache_path = cache_path or settings.nse_holiday_cache_path
    refresh_days = refresh_days or settings.nse_holiday_refresh_days
    if allow_network is None:
        allow_network = settings.nse_holiday_allow_network

    # Determine seed file path (assumed to be the same as default cache path if not overridden,
    # or we can look for it in a standard location if cache path is somewhere mutable like /var/tmp)
    # For now, we assume the committed seed file IS the default cache path.
    # But if the user provides a custom cache path (e.g. /tmp/cache.json), we still want to fallback to the seed file.
    # The seed file created in the plan is `packages/core/data/nse_holidays_trading.json`.

    seed_path = "packages/core/data/nse_holidays_trading.json"

    # 1. Check cache
    cached_data = load_cache(cache_path)
    cache_age_days = float('inf')

    if cached_data and os.path.exists(cache_path):
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
        cache_age_days = (datetime.now() - mtime).days

    # Use fresh cache if available
    if cached_data and cache_age_days < refresh_days:
        logger.info("Using fresh cache", age_days=cache_age_days)
        return extract_segment_dates(cached_data, segment)

    # 2. Try to refresh if allowed
    new_data = None
    if allow_network:
        try:
            new_data = fetch_nse_holidays()
            if new_data:
                save_cache(new_data, cache_path)
                return extract_segment_dates(new_data, segment)
        except Exception as e:
            logger.warning("Failed to refresh holidays", error=str(e))

    # 3. Fallback to stale cache
    if cached_data:
        logger.warning("Using stale cache", age_days=cache_age_days)
        return extract_segment_dates(cached_data, segment)

    # 4. Fallback to seed file (if cache_path was different from seed_path)
    if cache_path != seed_path:
        seed_data = load_cache(seed_path)
        if seed_data:
            logger.warning("Using seed file fallback")
            # Attempt to copy seed to cache location so we have something there
            save_cache(seed_data, cache_path)
            return extract_segment_dates(seed_data, segment)

    logger.critical("No holiday data available")
    return set()
