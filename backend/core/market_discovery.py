"""Auto-discover active Polymarket 5m/15m crypto prediction markets."""

import re
import time
from typing import Dict, List, Optional

import aiohttp

from backend.config import POLYMARKET_GAMMA_API
from backend.core.redis_manager import redis_manager
from backend.models.market import (
    Asset,
    ClobTokenIds,
    Duration,
    MarketInfo,
    MarketStatus,
)
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Regex to extract the strike (price to beat) from a market question
# Matches patterns like "$84,250.00" or "$2,150.00"
_STRIKE_RE = re.compile(r"\$([0-9,]+(?:\.[0-9]+)?)")

ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL]
DURATIONS = [Duration.FIVE_MIN, Duration.FIFTEEN_MIN]

# Keywords for fallback filtering
_KEYWORDS_ASSET = {"BTC", "ETH", "SOL", "Bitcoin", "Ethereum", "Solana"}
_KEYWORDS_TIME = {"5-minute", "15-minute", "5 minute", "15 minute", "5min", "15min"}
_KEYWORDS_DIR = {"above", "below", "up", "down"}


def compute_current_slugs(now: Optional[int] = None) -> List[Dict]:
    """Compute market slugs for the current interval of each asset+duration."""
    now = now or int(time.time())
    slugs = []
    for asset in ASSETS:
        for dur in DURATIONS:
            interval_label = "5m" if dur == Duration.FIVE_MIN else "15m"
            ts_rounded = (now // dur.value) * dur.value
            slug = f"{asset.value.lower()}-updown-{interval_label}-{ts_rounded}"
            slugs.append(
                {
                    "asset": asset,
                    "duration": dur,
                    "slug": slug,
                    "start_time": ts_rounded,
                    "end_time": ts_rounded + dur.value,
                }
            )
    return slugs


def compute_next_slugs(now: Optional[int] = None) -> List[Dict]:
    """Compute market slugs for the NEXT interval (pre-fetching)."""
    now = now or int(time.time())
    slugs = []
    for asset in ASSETS:
        for dur in DURATIONS:
            interval_label = "5m" if dur == Duration.FIVE_MIN else "15m"
            ts_rounded = (now // dur.value) * dur.value + dur.value
            slug = f"{asset.value.lower()}-updown-{interval_label}-{ts_rounded}"
            slugs.append(
                {
                    "asset": asset,
                    "duration": dur,
                    "slug": slug,
                    "start_time": ts_rounded,
                    "end_time": ts_rounded + dur.value,
                }
            )
    return slugs


def _extract_strike_price(question: str) -> Optional[float]:
    """Extract the numeric strike price from a market question string."""
    match = _STRIKE_RE.search(question)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def _market_matches_slug(market: Dict, slug_info: Dict) -> bool:
    """Check if a Gamma API market record matches a computed slug."""
    m_slug = market.get("slug", "")
    return m_slug == slug_info["slug"]


def _market_matches_keywords(market: Dict) -> bool:
    """Fallback: check if a market matches crypto-prediction keywords."""
    text = (market.get("question", "") + " " + market.get("slug", "")).upper()
    has_asset = any(kw.upper() in text for kw in _KEYWORDS_ASSET)
    has_time = any(kw.upper() in text for kw in _KEYWORDS_TIME)
    has_dir = any(kw.upper() in text for kw in _KEYWORDS_DIR)
    return has_asset and (has_time or has_dir)


def _parse_market(market: Dict, slug_info: Dict) -> Optional[MarketInfo]:
    """Parse a raw Gamma API market dict into a MarketInfo model."""
    question = market.get("question", "")
    strike = _extract_strike_price(question)
    if strike is None:
        logger.warning("Could not extract strike price from: %s", question)
        return None

    # Extract CLOB token IDs (YES / NO)
    clob_ids_raw = market.get("clobTokenIds", "")
    if isinstance(clob_ids_raw, str):
        parts = [p.strip().strip('"') for p in clob_ids_raw.strip("[]").split(",") if p.strip()]
    elif isinstance(clob_ids_raw, list):
        parts = clob_ids_raw
    else:
        parts = []

    yes_id = parts[0] if len(parts) > 0 else ""
    no_id = parts[1] if len(parts) > 1 else ""

    if not yes_id or not no_id:
        logger.warning("Missing CLOB token IDs for market %s", market.get("slug", ""))
        return None

    condition_id = market.get("conditionId", market.get("condition_id", ""))

    # Determine outcome prices
    outcome_prices = market.get("outcomePrices", "")
    if isinstance(outcome_prices, str):
        try:
            prices = [float(p.strip().strip('"')) for p in outcome_prices.strip("[]").split(",") if p.strip()]
        except ValueError:
            prices = [0.5, 0.5]
    elif isinstance(outcome_prices, list):
        prices = [float(p) for p in outcome_prices]
    else:
        prices = [0.5, 0.5]

    return MarketInfo(
        slug=slug_info["slug"],
        asset=slug_info["asset"],
        duration=slug_info["duration"],
        condition_id=condition_id,
        clob_token_ids=ClobTokenIds(yes_id=yes_id, no_id=no_id),
        question=question,
        price_to_beat=strike,
        start_time=slug_info["start_time"],
        end_time=slug_info["end_time"],
        status=MarketStatus.ACTIVE,
    )


class MarketDiscovery:
    """Discovers active Polymarket crypto prediction markets."""

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._discovered: Dict[str, MarketInfo] = {}

    async def start(self) -> None:
        """Initialize the HTTP session."""
        self._session = aiohttp.ClientSession()
        logger.info("MarketDiscovery started")

    async def stop(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
        logger.info("MarketDiscovery stopped")

    @property
    def discovered_markets(self) -> Dict[str, MarketInfo]:
        return dict(self._discovered)

    async def discover(self) -> List[MarketInfo]:
        """Run one discovery cycle: compute slugs, fetch from API, parse."""
        # Rate-limit Gamma API calls
        allowed = await redis_manager.check_rate_limit("gamma_api", max_calls=6, window_secs=60)
        if not allowed:
            logger.debug("Rate-limited, returning cached markets")
            return list(self._discovered.values())

        current = compute_current_slugs()
        next_slugs = compute_next_slugs()
        all_slugs = current + next_slugs

        markets_raw = await self._fetch_active_markets()
        found: List[MarketInfo] = []

        for slug_info in all_slugs:
            # Check Redis cache first
            cached = await redis_manager.get_cached_market(slug_info["slug"])
            if cached:
                try:
                    mi = MarketInfo(**cached)
                    found.append(mi)
                    self._discovered[mi.slug] = mi
                    continue
                except Exception:
                    pass

            # Try slug match
            matched = None
            for m in markets_raw:
                if _market_matches_slug(m, slug_info):
                    matched = m
                    break

            # Fallback: keyword match
            if matched is None:
                for m in markets_raw:
                    if _market_matches_keywords(m):
                        # Additional check: does the timing make sense?
                        matched = m
                        break

            if matched:
                mi = _parse_market(matched, slug_info)
                if mi:
                    found.append(mi)
                    self._discovered[mi.slug] = mi
                    await redis_manager.cache_market(mi.slug, mi.model_dump())
                    logger.info("Discovered market: %s (strike=%.2f)", mi.slug, mi.price_to_beat)

        return found

    async def _fetch_active_markets(self) -> List[Dict]:
        """Fetch active markets from the Gamma API."""
        if not self._session:
            return []
        url = f"{POLYMARKET_GAMMA_API}/markets"
        params = {"active": "true", "closed": "false", "limit": "100"}
        try:
            async with self._session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data if isinstance(data, list) else data.get("data", data.get("markets", []))
                logger.warning("Gamma API returned status %d", resp.status)
                return []
        except Exception:
            logger.exception("Error fetching markets from Gamma API")
            return []

    async def get_market(self, slug: str) -> Optional[MarketInfo]:
        """Get a specific discovered market by slug."""
        return self._discovered.get(slug)

    def get_markets_ending_soon(self, within_secs: int = 15) -> List[MarketInfo]:
        """Return markets that are ending within *within_secs* seconds."""
        now = int(time.time())
        return [
            m for m in self._discovered.values()
            if 0 < (m.end_time - now) <= within_secs
        ]

    def remove_expired(self) -> List[str]:
        """Remove markets whose end_time has passed. Returns removed slugs."""
        now = int(time.time())
        expired = [slug for slug, m in self._discovered.items() if m.end_time < now]
        for slug in expired:
            del self._discovered[slug]
        return expired


# Module-level singleton
market_discovery = MarketDiscovery()
