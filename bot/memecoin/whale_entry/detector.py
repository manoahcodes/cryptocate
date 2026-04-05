"""
Feature 15 — Whale entry detector for tokens < 24 hours old (Pro only).
Fires when large buy activity is detected in a newly discovered memecoin.
"""

import logging
from datetime import timedelta

import redis
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

WHALE_ENTRY_MIN_USD = 5_000.0


def check_whale_entry_for_token(token) -> int:
    """
    Check whether large whale-sized buys have been made in a token
    that is less than 24 hours old.
    Returns number of alerts sent.
    """
    # Only check tokens discovered in the last 24h
    cutoff = timezone.now() - timedelta(hours=24)
    if token.discovered_at < cutoff:
        return 0

    if not token.pair_address:
        return 0

    try:
        transactions = _get_recent_token_buyers(token)
        whale_entries = _filter_whale_buyers(transactions)

        if not whale_entries:
            return 0

        return _send_whale_entry_alerts(token, whale_entries)

    except Exception as e:
        logger.debug("whale_entry check failed for %s: %s", token.address, e)
        return 0


def _get_recent_token_buyers(token) -> list[dict]:
    """
    Fetch aggregated trade data for a token from DexScreener.

    DexScreener free API does not expose individual wallet addresses,
    so we use the 1h aggregated volume/buys as a whale-entry proxy.
    A genuine implementation would index on-chain Transfer logs via
    Etherscan tokentx or Solscan SPL transfers.
    """
    from bot.memecoin.scanner.dexscreener import get_pair_by_address

    pair_data = get_pair_by_address(token.pair_address, chain=token.chain)
    if not pair_data:
        return []

    txns   = (pair_data.get("txns") or {}).get("h1", {})
    buys   = txns.get("buys") or 0
    volume = (pair_data.get("volume") or {}).get("h1") or 0

    if buys == 0:
        return []

    avg_buy_usd = volume / buys

    if avg_buy_usd >= WHALE_ENTRY_MIN_USD:
        return [{"avg_buy_usd": avg_buy_usd, "buys": buys, "volume": volume}]

    return []


def _filter_whale_buyers(transactions: list[dict]) -> list[dict]:
    """Filter to only entries meeting the whale threshold."""
    return [
        {
            "avg_buy_usd": tx.get("avg_buy_usd", 0),
            "buys":        tx.get("buys", 0),
            "volume":      tx.get("volume", 0),
            "label":       "Unknown Whale",
        }
        for tx in transactions
        if tx.get("avg_buy_usd", 0) >= WHALE_ENTRY_MIN_USD
    ]


def _send_whale_entry_alerts(token, whale_entries: list[dict]) -> int:
    """Alert all Pro users about whale entries in a new token."""
    from bot.core.models import TelegramUser
    from bot.core.tasks import send_alert_message
    from bot.memecoin.models import MemeAlert

    r         = redis.from_url(settings.REDIS_URL, decode_responses=True)
    alert_key = f"whale_entry_alerted:{token.address}"

    # 6-hour cooldown per token to avoid repeated alerts
    if r.get(alert_key):
        return 0

    r.setex(alert_key, 3600 * 6, "1")

    pro_users = TelegramUser.objects.filter(plan="pro")
    if not pro_users.exists():
        return 0

    message = _format_whale_entry_alert(token, whale_entries[0])
    sent    = 0

    for user in pro_users:
        try:
            send_alert_message.delay(user.telegram_id, message, parse_mode="HTML")
            MemeAlert.objects.create(
                telegram_user=user,
                token=token,
                alert_type=MemeAlert.ALERT_WHALE_ENTRY,
                message_sent=message,
            )
            sent += 1
        except Exception as e:
            logger.warning(
                "whale_entry alert failed for user %s: %s", user.telegram_id, e
            )

    return sent


def _format_whale_entry_alert(token, entry: dict) -> str:
    """Format a whale entry alert for Telegram. Uses HTML parse mode."""
    from html import escape as he

    from bot.prices.coingecko import format_usd

    symbol   = he(token.symbol or "?")
    avg_buy  = entry.get("avg_buy_usd", 0)
    buys     = entry.get("buys", 0)
    volume   = entry.get("volume", 0)
    liq      = token.liquidity_usd or 0

    age_minutes = "?"
    if token.discovered_at:
        delta       = timezone.now() - token.discovered_at
        age_minutes = int(delta.total_seconds() // 60)

    # Rug score badge if available
    if token.rugcheck_score is not None:
        score      = token.rugcheck_score
        risk_emoji = "🔴" if score >= 700 else "🟠" if score >= 400 else "🟡" if score >= 100 else "🟢"
        score_line = f"\nRug Score: {risk_emoji} {score:.0f}/1000"
    else:
        score_line = ""

    return (
        f"🐳 <b>Whale Entry Detected!</b>\n\n"
        f"Token: <b>{symbol}</b> (&lt;{age_minutes}m old)\n"
        f"Chain: {token.chain.upper()}\n\n"
        f"Avg Buy: <b>{format_usd(avg_buy)}</b>\n"
        f"Buys (1h): {buys}\n"
        f"Volume (1h): {format_usd(volume)}\n"
        f"Liquidity: {format_usd(liq)}"
        f"{score_line}\n\n"
        f"<code>{he(token.address)}</code>\n"
        f"<i>Use /meme check to assess risk</i>"
    )