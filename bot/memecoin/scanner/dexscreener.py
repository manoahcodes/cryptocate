"""
Feature 11 — DexScreener new token pair scanner.
Reference: https://docs.dexscreener.com/api/reference

No API key required. Endpoint format (updated):
  GET /latest/dex/pairs/{chainId}/{pairAddress}   ← chain required in path
  GET /latest/dex/tokens/{tokenAddress}
  GET /latest/dex/search?q={query}
"""

import logging
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

DEXSCREENER_BASE = "https://api.dexscreener.com/latest/dex"
TIMEOUT = 10

# Map our internal chain keys to DexScreener chainId strings
CHAIN_IDS = {
    "eth":  "ethereum",
    "arb":  "arbitrum",
    "base": "base",
    "bsc":  "bsc",
    "sol":  "solana",
}


def _get(endpoint: str, params: dict = None) -> Optional[dict]:
    """GET from DexScreener API. Returns parsed JSON or None on error."""
    try:
        resp = requests.get(
            f"{DEXSCREENER_BASE}{endpoint}",
            params=params or {},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error("DexScreener API error (%s): %s", endpoint, e)
        return None


def get_pair_by_address(pair_address: str, chain: str = "sol") -> Optional[dict]:
    """
    Fetch a specific DEX pair by its pool/pair address.

    IMPORTANT: DexScreener requires the chainId in the path:
      /latest/dex/pairs/{chainId}/{pairAddress}
    Passing just the address (old format) returns 404.

    Args:
        pair_address: The DEX pool/pair contract address
        chain: Our internal chain key (eth, arb, base, bsc, sol)
    """
    chain_id = CHAIN_IDS.get(chain.lower(), chain.lower())
    data = _get(f"/pairs/{chain_id}/{pair_address}")
    if data and "pairs" in data and data["pairs"]:
        return data["pairs"][0]
    return None


def get_token_pairs(token_address: str) -> list[dict]:
    """
    Fetch all DEX pairs for a token contract address.
    Works across all chains — DexScreener resolves the chain automatically.
    """
    data = _get(f"/tokens/{token_address}")
    if data and "pairs" in data:
        return data["pairs"]
    return []


def search_pairs(query: str) -> list[dict]:
    """Search for pairs by token name, symbol, or address."""
    data = _get("/search", params={"q": query})
    if data and "pairs" in data:
        return data["pairs"]
    return []


def get_new_pairs(
    chain_id: str = "ethereum",
    limit: int = 20,
    min_liquidity_usd: float = None,
    min_buys_1h: int = None,
) -> list[dict]:
    """
    Fetch recently active token pairs from DexScreener filtered by
    minimum liquidity and buy count.

    DexScreener doesn't have a dedicated "new pairs" endpoint on the
    free tier, so we search broadly and filter by our criteria.
    """
    if min_liquidity_usd is None:
        min_liquidity_usd = settings.MEME_MIN_LIQUIDITY_USD
    if min_buys_1h is None:
        min_buys_1h = settings.MEME_MIN_BUYS_1H

    # Search for active pairs on the target chain
    data = _get("/search", params={"q": chain_id})
    if not data or "pairs" not in data:
        return []

    filtered = []
    for pair in data["pairs"]:
        # Filter by chain
        if pair.get("chainId", "").lower() != chain_id.lower():
            continue

        # Liquidity filter
        liq = (pair.get("liquidity") or {}).get("usd") or 0
        if liq < min_liquidity_usd:
            continue

        # Buy count filter
        buys = (pair.get("txns") or {}).get("h1", {}).get("buys") or 0
        if buys < min_buys_1h:
            continue

        filtered.append(pair)
        if len(filtered) >= limit:
            break

    return filtered


def enrich_token(token_address: str, chain: str = "eth") -> Optional[dict]:
    """
    Return the best (highest liquidity) pair for a token address.
    Used to enrich MemeToken records with current market data.
    """
    pairs = get_token_pairs(token_address)
    if not pairs:
        return None

    # Filter to the correct chain if possible
    chain_id = CHAIN_IDS.get(chain.lower(), chain.lower())
    chain_pairs = [p for p in pairs if p.get("chainId", "").lower() == chain_id]
    pool = chain_pairs if chain_pairs else pairs

    # Return the pair with highest liquidity
    return max(pool, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)