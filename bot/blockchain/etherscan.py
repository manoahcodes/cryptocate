"""
Etherscan / Arbiscan / Basescan API client.

References:
  https://docs.etherscan.io/
  https://docs.arbiscan.io/
  https://docs.basescan.org/
"""

import logging
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Base URLs per chain
CHAIN_URLS = {
    "eth": "https://api.etherscan.io/api",
    "arb": "https://api.arbiscan.io/api",
    "base": "https://api.basescan.org/api",
    "bsc": "https://api.bscscan.com/api",
}

# API keys per chain
CHAIN_KEYS = {
    "eth": settings.ETHERSCAN_API_KEY,
    "arb": settings.ARBISCAN_API_KEY,
    "base": settings.BASESCAN_API_KEY,
    "bsc": settings.ETHERSCAN_API_KEY,  # Fallback
}

TIMEOUT = 10  # seconds


def _api_key(chain: str) -> str:
    key = CHAIN_KEYS.get(chain, settings.ETHERSCAN_API_KEY)
    return key or settings.ETHERSCAN_API_KEY


def _base_url(chain: str) -> str:
    return CHAIN_URLS.get(chain, CHAIN_URLS["eth"])


def _get(chain: str, params: dict) -> Optional[dict]:
    """Make a GET request to the appropriate chain explorer API."""
    params["apikey"] = _api_key(chain)
    url = _base_url(chain)
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "1" or data.get("message") == "OK":
            return data
        # status 0 can mean no results — return data so caller can check result
        return data
    except requests.RequestException as e:
        logger.error("Etherscan API error (chain=%s): %s", chain, e)
        return None


async def get_eth_balance(address: str, chain: str = "eth") -> float:
    """
    Get the native coin balance for an address.
    Returns balance in ETH (or equivalent native coin).
    """
    import asyncio

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _get(
            chain,
            {
                "module": "account",
                "action": "balance",
                "address": address,
                "tag": "latest",
            },
        ),
    )
    if result and result.get("result"):
        try:
            wei = int(result["result"])
            return wei / 1e18
        except (ValueError, TypeError):
            pass
    return 0.0


def get_transactions(
    address: str,
    chain: str = "eth",
    start_block: int = 0,
    page: int = 1,
    offset: int = 20,
) -> list[dict]:
    """
    Get normal (ETH) transactions for an address.
    Returns list of transaction dicts.
    Reference: https://docs.etherscan.io/api-endpoints/accounts#get-a-list-of-normal-transactions-by-address
    """
    data = _get(
        chain,
        {
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": start_block,
            "endblock": 99999999,
            "page": page,
            "offset": offset,
            "sort": "desc",
        },
    )
    if data and isinstance(data.get("result"), list):
        return data["result"]
    return []


def get_token_transfers(
    address: str,
    chain: str = "eth",
    page: int = 1,
    offset: int = 20,
) -> list[dict]:
    """
    Get ERC-20 token transfer events for an address.
    Reference: https://docs.etherscan.io/api-endpoints/accounts#get-a-list-of-erc20-token-transfer-events-by-address
    """
    data = _get(
        chain,
        {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "page": page,
            "offset": offset,
            "sort": "desc",
        },
    )
    if data and isinstance(data.get("result"), list):
        return data["result"]
    return []


def get_latest_block(chain: str = "eth") -> int:
    """Return the current block number for a chain."""
    data = _get(
        chain,
        {
            "module": "proxy",
            "action": "eth_blockNumber",
        },
    )
    if data and data.get("result"):
        try:
            return int(data["result"], 16)
        except (ValueError, TypeError):
            pass
    return 0
