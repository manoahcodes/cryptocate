"""
Feature 8 — Per-wallet custom threshold resolution (Pro only).
Determines the effective alert threshold for a given wallet.
"""

from bot.core.models import WatchedWallet


def resolve_threshold(wallet: WatchedWallet) -> float:
    """
    Return the effective alert threshold (in ETH) for a wallet.

    Priority:
      1. wallet.custom_threshold_eth  — set by user via /threshold (Pro only)
      2. telegram_user.alert_threshold_eth() — plan default (1.0 Pro / 5.0 Free)
    """
    # Custom threshold (Pro only, already validated at set time)
    if (
        wallet.telegram_user.is_pro()
        and wallet.custom_threshold_eth is not None
        and wallet.custom_threshold_eth > 0
    ):
        return wallet.custom_threshold_eth

    # Plan default
    return wallet.telegram_user.alert_threshold_eth()


def meets_threshold(amount_eth: float, wallet: WatchedWallet) -> bool:
    """
    Returns True if the given ETH amount meets the wallet's alert threshold.
    """
    threshold = resolve_threshold(wallet)
    return amount_eth >= threshold
