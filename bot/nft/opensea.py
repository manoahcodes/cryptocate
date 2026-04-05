"""
OpenSea API client — collection stats and events.

Uses OpenSea API v2 for stats (requires API key — free tier available).
Falls back to v1 for collection stats if no key is set (no key required).

Get a free API key: https://docs.opensea.io/reference/api-overview
Set OPENSEA_API_KEY in .env

Endpoints used:
  v2: GET /api/v2/collections/{slug}/stats    → floor price, volume, sales
  v1: GET /api/v1/collection/{slug}/stats     → fallback, no key needed
  v2: GET /api/v2/events/collection/{slug}    → buy/sell events (key required)
"""

import logging
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

BASE_V2  = "https://api.opensea.io/api/v2"
BASE_V1  = "https://api.opensea.io/api/v1"
TIMEOUT  = 10


def _headers() -> dict:
    h = {"accept": "application/json", "User-Agent": "WhaleWatchBot/1.0"}
    key = getattr(settings, "OPENSEA_API_KEY", "") or ""
    if key:
        h["x-api-key"] = key
    return h


def _get_v2(endpoint: str, params: dict = None) -> Optional[dict]:
    try:
        resp = requests.get(
            f"{BASE_V2}{endpoint}",
            params=params or {},
            headers=_headers(),
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response else 0
        if code == 401:
            logger.warning(
                "OpenSea 401 — set OPENSEA_API_KEY in .env. "
                "Free key: https://docs.opensea.io/reference/api-overview"
            )
        elif code == 429:
            logger.warning("OpenSea rate limit hit (429)")
        else:
            logger.error("OpenSea v2 error (%s): %s", endpoint, e)
        return None
    except requests.RequestException as e:
        logger.error("OpenSea request error (%s): %s", endpoint, e)
        return None


def _get_v1(endpoint: str, params: dict = None) -> Optional[dict]:
    """v1 fallback — no API key required for collection stats."""
    try:
        resp = requests.get(
            f"{BASE_V1}{endpoint}",
            params=params or {},
            headers={"accept": "application/json", "User-Agent": "WhaleWatchBot/1.0"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error("OpenSea v1 error (%s): %s", endpoint, e)
        return None


def get_collection_stats(slug: str) -> Optional[dict]:
    """
    Fetch floor price, volume, and sales stats for a collection.

    Tries v2 first (requires API key), falls back to v1 (no key needed).
    Returns normalised dict:
      floor_price   — current floor in ETH
      volume_24h    — 24h volume in ETH
      volume_7d     — 7d volume in ETH
      num_owners    — unique owner count
      total_supply  — total supply
      sales_24h     — number of sales in 24h
    """
    # Try v2 first
    data = _get_v2(f"/collections/{slug}/stats")
    if data:
        total = data.get("total", {})
        return {
            "floor_price":  data.get("floor_price") or 0.0,
            "volume_24h":   total.get("volume") or 0.0,
            "volume_7d":    0.0,
            "num_owners":   total.get("num_owners") or 0,
            "total_supply": total.get("count") or 0,
            "sales_24h":    total.get("sales") or 0,
        }

    # Fall back to v1 (no key needed)
    data = _get_v1(f"/collection/{slug}/stats")
    if data:
        stats = data.get("stats", {})
        return {
            "floor_price":  stats.get("floor_price") or 0.0,
            "volume_24h":   stats.get("one_day_volume") or 0.0,
            "volume_7d":    stats.get("seven_day_volume") or 0.0,
            "num_owners":   stats.get("num_owners") or 0,
            "total_supply": stats.get("total_supply") or 0,
            "sales_24h":    stats.get("one_day_sales") or 0,
        }

    return None


def get_collection_info(slug: str) -> Optional[dict]:
    """
    Fetch basic collection metadata (name, description, contract address).
    Falls back to v1 if v2 fails.
    """
    data = _get_v2(f"/collections/{slug}")
    if data:
        contracts = data.get("contracts", [])
        contract  = contracts[0].get("address", "") if contracts else ""
        return {
            "name":             data.get("name", slug),
            "description":      data.get("description", ""),
            "contract_address": contract,
            "image_url":        data.get("image_url", ""),
        }

    data = _get_v1(f"/collection/{slug}")
    if data:
        col  = data.get("collection", {})
        addr = ""
        pcs  = col.get("primary_asset_contracts", [])
        if pcs:
            addr = pcs[0].get("address", "")
        return {
            "name":             col.get("name", slug),
            "description":      col.get("description", ""),
            "contract_address": addr,
            "image_url":        col.get("image_url", ""),
        }

    return None


def get_recent_sales(slug: str, limit: int = 20) -> list[dict]:
    """
    Fetch recent sale events for a collection.
    Requires OPENSEA_API_KEY.

    Returns list of dicts with:
      tx_hash, buyer, seller, token_id, price_eth, timestamp
    """
    if not getattr(settings, "OPENSEA_API_KEY", ""):
        return []

    data = _get_v2(
        f"/events/collection/{slug}",
        params={"event_type": "sale", "limit": min(limit, 50)},
    )
    if not data or "asset_events" not in data:
        return []

    events = []
    for ev in data["asset_events"]:
        try:
            payment     = ev.get("payment", {})
            quantity    = int(payment.get("quantity", 0))
            decimals    = int(payment.get("decimals", 18))
            price_eth   = quantity / (10 ** decimals)
            nft         = ev.get("nft", {})

            events.append({
                "tx_hash":   ev.get("transaction", ""),
                "buyer":     ev.get("buyer", ""),
                "seller":    ev.get("seller", ""),
                "token_id":  nft.get("identifier", ""),
                "price_eth": price_eth,
                "timestamp": ev.get("event_timestamp", 0),
            })
        except (ValueError, TypeError):
            continue

    return events