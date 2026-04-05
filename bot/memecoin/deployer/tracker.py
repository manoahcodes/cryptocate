"""
Feature 13 — Deployer wallet tracker (Pro only).
Monitors known token deployer wallets for new contract deployments.
"""

import logging

from bot.core.models import TelegramUser
from bot.memecoin.models import TrackedDeployer

logger = logging.getLogger(__name__)


def add_deployer_wallet(tg_user: TelegramUser, address: str, chain: str = "eth") -> TrackedDeployer:
    """
    Add a deployer wallet to the tracked list for a Pro user.
    Raises ValueError if wallet already tracked or limit exceeded.
    """
    address = address.lower().strip()

    deployer, created = TrackedDeployer.objects.get_or_create(
        telegram_user=tg_user,
        address=address,
        chain=chain,
        defaults={"label": ""},
    )

    if not created:
        raise ValueError(f"Deployer {address[:12]}… is already being tracked.")

    logger.info(
        "Added deployer wallet %s (%s) for TelegramUser %s",
        address[:12],
        chain,
        tg_user.telegram_id,
    )
    return deployer


def check_deployer_for_new_tokens(deployer: TrackedDeployer) -> list[dict]:
    """
    Check a deployer wallet for newly created token contracts.
    Returns a list of new deployment dicts not seen before.
    """
    from bot.blockchain.etherscan import _get

    # Fetch internal transactions — contract creations have `to` == ""
    data = _get(
        deployer.chain,
        {
            "module": "account",
            "action": "txlistinternal",
            "address": deployer.address,
            "sort": "desc",
            "page": 1,
            "offset": 10,
        },
    )

    if not data or not isinstance(data.get("result"), list):
        return []

    new_deployments = []
    last_seen = deployer.last_seen_contract

    for tx in data["result"]:
        contract_addr = tx.get("contractAddress", "")
        if not contract_addr:
            continue

        if contract_addr.lower() == last_seen.lower():
            break

        new_deployments.append({
            "contract_address": contract_addr,
            "tx_hash": tx.get("hash", ""),
            "block_number": tx.get("blockNumber", ""),
        })

    # Update last seen
    if new_deployments:
        first = new_deployments[0]["contract_address"]
        TrackedDeployer.objects.filter(pk=deployer.pk).update(
            last_seen_contract=first
        )

    return new_deployments


def format_deployer_alert(deployer: TrackedDeployer, deployment: dict) -> str:
    """Format a new deployer token alert for Telegram."""
    label = deployer.label or f"{deployer.address[:10]}…"
    contract = deployment["contract_address"]
    tx_hash = deployment.get("tx_hash", "")
    chain = deployer.chain.upper()

    explorer_base = {
        "eth": "https://etherscan.io",
        "arb": "https://arbiscan.io",
        "base": "https://basescan.org",
        "bsc": "https://bscscan.com",
    }.get(deployer.chain, "https://etherscan.io")

    tx_link = f"[View TX]({explorer_base}/tx/{tx_hash})" if tx_hash else ""
    contract_link = f"[Token Contract]({explorer_base}/address/{contract})"

    return (
        f"🚀 *New Token Deployed\\!*\n\n"
        f"Deployer: *{label}*\n"
        f"Chain: {chain}\n"
        f"Contract: `{contract[:16]}…`\n\n"
        f"{contract_link}"
        + (f" · {tx_link}" if tx_link else "")
        + "\n\nRun `/meme check` on the contract to assess risk"
    )
