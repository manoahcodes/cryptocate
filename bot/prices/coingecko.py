"""
Feature 1 — USD price values via CoinGecko Demo API v3 with Redis caching.

Authentication:
  Header: x-cg-demo-api-key
  Docs:   https://docs.coingecko.com/v3.0.1/reference/authentication

Rate limit budget (Demo plan — 10,000 calls/month):
  warm_price_cache runs every 600s (10min) = ~4,320 calls/month
  Cache TTL is 720s (12min) so it NEVER expires between scheduled warms.
  All price lookups hit Redis — the API is only called by the Celery task.

  Breakdown:
    warm_price_cache  600s interval  →  4,320 calls/month
    Safety headroom                  →  5,680 calls/month remaining
    Total                            →  10,000 calls/month cap ✓
"""

import logging
from typing import Optional

import redis
import requests
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)

COINGECKO_BASE  = "https://api.coingecko.com/api/v3"

# Cache TTL must be LONGER than the warm interval so the cache
# never expires between Celery runs. warm=600s, TTL=720s.
PRICE_CACHE_TTL  = 720   # 12 minutes
WARM_INTERVAL_S  = 600   # 10 minutes — matches celery.py beat_schedule
TIMEOUT          = 10

COIN_IDS = {
    "ethereum": "ethereum",
    "eth":      "ethereum",
    "arb":      "ethereum",
    "base":     "ethereum",
    "bnb":      "binancecoin",
    "bsc":      "binancecoin",
    "sol":      "solana",
    "solana":   "solana",
}

# All coins fetched in one bulk API call per warm cycle
WARM_COINS = ["ethereum", "binancecoin", "solana"]


def _get_redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _get_headers() -> dict:
    headers = {"accept": "application/json"}
    api_key = getattr(settings, "COINGECKO_API_KEY", "") or ""
    if api_key:
        headers["x-cg-demo-api-key"] = api_key
    else:
        logger.warning(
            "COINGECKO_API_KEY not set — using unauthenticated CoinGecko API. "
            "Set it in .env to avoid rate limits."
        )
    return headers


def _get(endpoint: str, params: dict = None) -> Optional[dict]:
    try:
        resp = requests.get(
            f"{COINGECKO_BASE}{endpoint}",
            params=params or {},
            headers=_get_headers(),
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            logger.error(
                "CoinGecko 429 — monthly cap hit or rate limit exceeded. "
                "Cap: 10,000 calls/month. warm_price_cache should be the "
                "only caller. Check nothing else is calling the API directly."
            )
        else:
            logger.error("CoinGecko HTTP error (%s): %s", endpoint, e)
        return None
    except requests.RequestException as e:
        logger.error("CoinGecko request error (%s): %s", endpoint, e)
        return None


# ── Public interface ───────────────────────────────────────────────────────────

def get_price_usd(coin_id: str) -> Optional[float]:
    """
    Return the current USD price for a coin from Redis cache.

    Under normal operation this NEVER hits the CoinGecko API — it reads
    from Redis which is kept warm by the Celery beat task.

    The live API fallback only fires on first boot before the first
    warm_price_cache run, or if Redis is flushed.
    """
    cg_id     = COIN_IDS.get(coin_id.lower(), coin_id.lower())
    r         = _get_redis()
    cache_key = f"price:{cg_id}"

    cached = r.get(cache_key)
    if cached is not None:
        try:
            return float(cached)
        except (ValueError, TypeError):
            pass

    # Cache miss — only happens on first boot or after Redis flush.
    # Log a warning so you know API credits are being used unexpectedly.
    logger.warning(
        "CoinGecko cache miss for %s — fetching live. "
        "This uses API credits. If this happens often, check that "
        "warm_price_cache Celery task is running.",
        cg_id,
    )
    return _fetch_and_cache_single(cg_id)


def _fetch_and_cache_single(coin_id: str) -> Optional[float]:
    """
    Emergency single-coin fetch. Costs 1 API credit.
    Should only ever be called on first boot.
    """
    data = _get("/simple/price", params={
        "ids":           coin_id,
        "vs_currencies": "usd",
    })
    if data:
        price = data.get(coin_id, {}).get("usd")
        if price is not None:
            _get_redis().setex(f"price:{coin_id}", PRICE_CACHE_TTL, str(float(price)))
            return float(price)
    return None


def eth_to_usd(amount: float, chain: str = "eth") -> Optional[float]:
    """Convert a native-coin amount to USD."""
    cg_id = COIN_IDS.get(chain.lower(), "ethereum")
    price = get_price_usd(cg_id)
    return round(amount * price, 2) if price is not None else None


def format_usd(amount: Optional[float]) -> str:
    if amount is None:
        return "~$?"
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.2f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.1f}K"
    return f"${amount:,.2f}"


# ── Celery task ────────────────────────────────────────────────────────────────

@shared_task
def warm_price_cache():
    """
    Runs every 600 seconds (10 minutes) via Celery beat.

    Fetches ALL tracked coin prices in a SINGLE API call (1 credit)
    and writes them to Redis. This is the only place the CoinGecko
    API should be called in normal operation.

    Monthly usage: 1 call per run × 6 runs/hour × 24h × 30d = 4,320 calls
    Budget remaining for other uses: ~5,680 calls/month

    Reference: https://docs.coingecko.com/v3.0.1/reference/simple-price
    """
    ids_str = ",".join(WARM_COINS)

    # Single bulk call — 1 API credit for all coins
    data = _get("/simple/price", params={
        "ids":           ids_str,
        "vs_currencies": "usd",
    })

    if not data:
        logger.warning(
            "warm_price_cache: CoinGecko returned no data. "
            "Existing cached prices remain valid for %ds.",
            PRICE_CACHE_TTL,
        )
        return []

    r      = _get_redis()
    warmed = []

    for coin_id in WARM_COINS:
        price = data.get(coin_id, {}).get("usd")
        if price is not None:
            r.setex(f"price:{coin_id}", PRICE_CACHE_TTL, str(float(price)))
            warmed.append(f"{coin_id}=${price:,.2f}")
        else:
            logger.warning("warm_price_cache: no price returned for %s", coin_id)

    logger.info("warm_price_cache: %s", " | ".join(warmed))
    return warmed