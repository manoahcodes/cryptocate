"""
Feature 6 — Dormant wallet alerts (Pro only).
Fires when a wallet that has been inactive for >= 90 days moves funds.
"""

import logging
from datetime import datetime, timedelta

from django.utils import timezone

from bot.blockchain.etherscan import get_transactions
from bot.core.models import WatchedWallet
from bot.prices.coingecko import eth_to_usd, format_usd

logger = logging.getLogger(__name__)

DORMANCY_DAYS = 90


def is_wallet_dormant(wallet: WatchedWallet) -> bool:
    """
    Returns True if last_checked_at is older than DORMANCY_DAYS.
    Used only for display/reporting — NOT for alert triggering.
    For alert triggering use check_dormant_reactivation().
    """
    if wallet.last_checked_at is None:
        return False
    cutoff = timezone.now() - timedelta(days=DORMANCY_DAYS)
    return wallet.last_checked_at < cutoff


def check_dormant_reactivation(wallet: WatchedWallet) -> dict | None:
    """
    Detect if a previously dormant wallet has just moved funds.

    Logic:
      1. Skip if already alerted this cycle (dormant_alerted=True)
      2. Fetch the two most recent transactions
      3. If the newest tx is already known (last_seen_tx), no new movement
      4. Check the PREVIOUS tx timestamp — if it was >90 days before the
         newest tx, the wallet was dormant and has just reactivated
      5. Return alert data dict, or None if no reactivation

    Returns dict with tx_hash, amount_eth, amount_usd, dormancy_days
    or None if no reactivation detected.
    """
    if wallet.dormant_alerted:
        return None

    # Fetch 2 most recent txs so we can compare gap between them
    txs = get_transactions(wallet.address, wallet.chain, offset=2)
    if not txs:
        return None

    latest_tx = txs[0]
    latest_hash = latest_tx.get("hash", "")

    # No new movement since last poll
    if latest_hash == wallet.last_seen_tx:
        return None

    # Parse latest tx timestamp
    try:
        latest_time = datetime.fromtimestamp(
            int(latest_tx.get("timeStamp", 0)), tz=timezone.utc
        )
    except (ValueError, TypeError):
        return None

    # Determine whether the wallet was dormant before this new tx.
    # If there's a previous tx, compare timestamps.
    # If there's no previous tx, fall back to last_checked_at.
    was_dormant = False
    dormant_days = 0

    if len(txs) >= 2:
        prev_tx = txs[1]
        try:
            prev_time = datetime.fromtimestamp(
                int(prev_tx.get("timeStamp", 0)), tz=timezone.utc
            )
            gap_days = (latest_time - prev_time).days
            if gap_days >= DORMANCY_DAYS:
                was_dormant = True
                dormant_days = gap_days
        except (ValueError, TypeError):
            pass
    elif wallet.last_checked_at:
        # Only one tx on record — use last_checked_at as proxy
        gap_days = (latest_time - wallet.last_checked_at).days
        if gap_days >= DORMANCY_DAYS:
            was_dormant = True
            dormant_days = gap_days

    if not was_dormant:
        return None

    # Parse amount
    try:
        amount_eth = int(latest_tx.get("value", 0)) / 1e18
    except (ValueError, TypeError):
        amount_eth = 0.0

    amount_usd = eth_to_usd(amount_eth, wallet.chain)

    return {
        "tx_hash":       latest_hash,
        "amount_eth":    amount_eth,
        "amount_usd":    amount_usd,
        "tx_time":       latest_time,
        "dormancy_days": dormant_days or DORMANCY_DAYS,
    }


def format_dormant_alert(wallet: WatchedWallet, alert_data: dict) -> str:
    """Format a dormant wallet reactivation alert. Uses HTML parse mode."""
    from html import escape as he

    label      = he(wallet.label or f"{wallet.address[:10]}…")
    amount_eth = alert_data["amount_eth"]
    amount_usd = alert_data.get("amount_usd")
    days       = alert_data.get("dormancy_days", DORMANCY_DAYS)
    tx_hash    = alert_data.get("tx_hash", "")

    coin = {
        "eth": "ETH", "arb": "ETH", "base": "ETH",
        "bsc": "BNB", "sol": "SOL",
    }.get(wallet.chain, "ETH")

    usd_str = f" ({format_usd(amount_usd)})" if amount_usd else ""

    explorer = {
        "eth":  "https://etherscan.io/tx",
        "arb":  "https://arbiscan.io/tx",
        "base": "https://basescan.org/tx",
        "bsc":  "https://bscscan.com/tx",
        "sol":  "https://solscan.io/tx",
    }.get(wallet.chain, "https://etherscan.io/tx")

    tx_link = f'\n<a href="{explorer}/{tx_hash}">View Transaction</a>' if tx_hash else ""

    return (
        f"😴 <b>Dormant Wallet Reactivated!</b>\n\n"
        f"Wallet: <b>{label}</b>\n"
        f"Inactive for: <b>{days}+ days</b>\n"
        f"Moved: <b>{amount_eth:.4f} {coin}</b>{usd_str}\n"
        f"Chain: {wallet.chain.upper()}"
        f"{tx_link}"
    )