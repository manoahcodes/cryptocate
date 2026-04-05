"""
Solscan Public API client for Solana transaction data.

Uses the free public API — no API key or account required.
Base URL: https://public-api.solscan.io

Rate limits: ~100 requests/min unauthenticated — sufficient for
wallet monitoring at our 120s polling interval.

Reference: https://public-api.solscan.io/docs/
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://public-api.solscan.io"
TIMEOUT  = 10
HEADERS  = {
    "accept":     "application/json",
    "User-Agent": "CrytocateBot/1.0",
}


def _get(endpoint: str, params: dict = None) -> Optional[dict | list]:
    """Make a GET request to the Solscan public API."""
    try:
        resp = requests.get(
            f"{BASE_URL}{endpoint}",
            params=params or {},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            logger.warning(
                "Solscan rate limit hit (429) for %s — "
                "polling too fast or free tier limit reached.",
                endpoint,
            )
        else:
            logger.error("Solscan HTTP error (%s): %s", endpoint, e)
        return None
    except requests.RequestException as e:
        logger.error("Solscan request error (%s): %s", endpoint, e)
        return None


def get_sol_balance(address: str) -> float:
    """
    Get SOL balance for a wallet address.
    Returns balance in SOL (converted from lamports).

    Endpoint: GET /account?address={address}
    Response field: lamports
    """
    data = _get("/account", params={"address": address})
    if isinstance(data, dict):
        lamports = data.get("lamports", 0)
        try:
            return int(lamports) / 1e9
        except (ValueError, TypeError):
            pass
    return 0.0


def get_sol_transactions(
    address: str,
    limit: int = 10,
    before_hash: str = "",
) -> list[dict]:
    """
    Get recent transactions for a Solana wallet address.

    Endpoint: GET /account/transactions
    Response: list of transaction dicts with fields:
      txHash      — transaction signature
      blockTime   — unix timestamp
      status      — "Success" | "Fail"
      fee         — fee in lamports
      lamport     — SOL change in lamports (positive = received, negative = sent)
      signer      — list of signing addresses

    Reference: https://public-api.solscan.io/docs/#/Account/get_account_transactions
    """
    params: dict = {
        "account": address,
        "limit":   min(limit, 50),  # API max is 50
    }
    if before_hash:
        params["beforeHash"] = before_hash

    data = _get("/account/transactions", params=params)
    if isinstance(data, list):
        return data
    return []


def get_spl_transfers(
    address: str,
    limit: int = 10,
    offset: int = 0,
) -> list[dict]:
    """
    Get SPL token transfers for a Solana wallet.

    Endpoint: GET /account/splTransfers
    Response: list of transfer dicts with fields:
      signature   — transaction signature
      blockTime   — unix timestamp
      changeType  — "inc" (received) | "dec" (sent)
      changeAmount — token amount changed (with decimals applied)
      tokenAddress — SPL token mint address
      symbol      — token symbol
      decimals    — token decimals

    Reference: https://public-api.solscan.io/docs/#/Account/get_account_splTransfers
    """
    data = _get(
        "/account/splTransfers",
        params={
            "account": address,
            "limit":   min(limit, 50),
            "offset":  offset,
        },
    )
    # Response is {"data": [...], "total": N}
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]
    if isinstance(data, list):
        return data
    return []


def get_account_tokens(address: str) -> list[dict]:
    """
    Get all SPL token balances for a Solana wallet.

    Endpoint: GET /account/tokens
    Response: list of token account dicts with fields:
      tokenAddress — SPL token mint
      tokenAmount  — {amount, decimals, uiAmount, uiAmountString}
      tokenSymbol  — symbol if known
      tokenName    — name if known
    """
    data = _get("/account/tokens", params={"account": address})
    if isinstance(data, list):
        return data
    return []