"""
Feature 10 — Copy-trade signals (Pro only).
Fires a structured signal when a wallet with a score >= 7.0 makes a move.
"""

import logging

from bot.core.models import Alert, WatchedWallet
from bot.prices.coingecko import format_usd

logger = logging.getLogger(__name__)

COPY_TRADE_SCORE_THRESHOLD = 7.0


def check_and_send_copy_trade_signal(
    wallet: WatchedWallet,
    tx: dict,
    amount_eth: float,
    direction: str,
) -> bool:
    """
    Evaluate whether a wallet transaction warrants a copy-trade signal.
    Returns True if a signal was sent.

    Criteria:
      - User is Pro
      - Wallet has a score >= 7.0
      - Transaction is an outflow (buy signal from smart money perspective)
        OR a significant inflow
    """
    user = wallet.telegram_user
    if not user.is_pro():
        return False

    # Get wallet score
    try:
        score = wallet.score.score
    except Exception:
        return False

    if score < COPY_TRADE_SCORE_THRESHOLD:
        return False

    tx_hash = tx.get("hash", "")

    # Avoid duplicate signals for the same tx
    if Alert.objects.filter(
        wallet=wallet,
        alert_type="copy_trade",
        tx_hash=tx_hash,
    ).exists():
        return False

    # Build signal message
    message = _format_copy_trade_signal(wallet, tx, amount_eth, direction, score)

    Alert.objects.create(
        telegram_user=user,
        wallet=wallet,
        alert_type="copy_trade",
        tx_hash=tx_hash,
        amount_eth=amount_eth,
        direction=direction,
        message_sent=message,
    )

    try:
        from bot.core.tasks import send_alert_message
        send_alert_message.delay(user.telegram_id, message)
    except Exception as e:
        logger.error("Failed to send copy-trade signal for %s: %s", wallet.address, e)
        return False

    logger.info(
        "Copy-trade signal sent for wallet %s (score=%.1f)",
        wallet.address[:12],
        score,
    )
    return True


def _format_copy_trade_signal(
    wallet: WatchedWallet,
    tx: dict,
    amount_eth: float,
    direction: str,
    score: float,
) -> str:
    """Format a copy-trade signal for display in Telegram."""
    label = wallet.label or f"{wallet.address[:10]}…"
    tx_hash = tx.get("hash", "")
    direction_label = "BUY" if direction == "in" else "SELL"
    direction_emoji = "🟢" if direction == "in" else "🔴"

    coin = {
        "eth": "ETH", "arb": "ETH", "base": "ETH", "bsc": "BNB", "sol": "SOL"
    }.get(wallet.chain, "ETH")

    chain_explorer = {
        "eth": "https://etherscan.io/tx",
        "arb": "https://arbiscan.io/tx",
        "base": "https://basescan.org/tx",
        "bsc": "https://bscscan.com/tx",
    }.get(wallet.chain, "https://etherscan.io/tx")

    from bot.prices.coingecko import eth_to_usd
    amount_usd = eth_to_usd(amount_eth, wallet.chain)
    usd_str = f" \\({format_usd(amount_usd)}\\)" if amount_usd else ""

    return (
        f"🎯 <b>Copy\\-Trade Signal</b>\n\n"
        f"{direction_emoji} *{direction_label}* — {label}\n"
        f"Score: <b>{score:.1f}/10</b> ⭐\n\n"
        f"Amount: <b>{amount_eth:.4f} {coin}</b>{usd_str}\n"
        f"Chain: {wallet.chain.upper()}\n\n"
        f"This wallet has a {score:.0f}/10 profitability score\n"
        f"[View TX]({chain_explorer}/{tx_hash})"
    )
