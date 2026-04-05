"""
Feature 16 — Volume spike and momentum alerts (Pro only).
Fires when a tracked token shows a significant increase in buy volume
or price momentum within a short window.
"""

import logging

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

# Minimum volume spike multiplier (e.g. 3x = 300% increase)
VOLUME_SPIKE_MULTIPLIER = 3.0
# Minimum absolute volume to avoid noise on low-liquidity tokens
MIN_VOLUME_USD = 10_000.0
# Price increase threshold (e.g. 0.30 = 30% increase in 1h)
PRICE_SPIKE_PCT = 30.0


def _get_redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def check_momentum_for_token(token) -> int:
    """
    Compare current volume/price against cached baseline.
    Returns number of alerts sent (0 or positive int).
    """
    if not token.pair_address:
        return 0

    try:
        from bot.memecoin.scanner.dexscreener import get_pair_by_address

        pair_data = get_pair_by_address(token.pair_address, chain=token.chain)
        if not pair_data:
            return 0

        current_volume_1h = pair_data.get("volume", {}).get("h1", 0) or 0
        current_price = float(pair_data.get("priceUsd") or 0)
        price_change_pct = float(pair_data.get("priceChange", {}).get("h1") or 0)

        # Update token market data
        from bot.memecoin.models import MemeToken
        MemeToken.objects.filter(pk=token.pk).update(
            volume_1h=current_volume_1h,
            price_usd=current_price,
            buys_1h=pair_data.get("txns", {}).get("h1", {}).get("buys"),
            sells_1h=pair_data.get("txns", {}).get("h1", {}).get("sells"),
        )

        # Check for momentum signals
        signals = []

        r = _get_redis()
        baseline_key = f"momentum_baseline:{token.address}"
        cached = r.get(baseline_key)

        if cached:
            try:
                prev_volume = float(cached)
                if (
                    prev_volume > 0
                    and current_volume_1h >= MIN_VOLUME_USD
                    and current_volume_1h >= prev_volume * VOLUME_SPIKE_MULTIPLIER
                ):
                    signals.append({
                        "type": "volume_spike",
                        "current_volume": current_volume_1h,
                        "prev_volume": prev_volume,
                        "multiplier": current_volume_1h / prev_volume,
                    })
            except (ValueError, TypeError):
                pass

        # Check price spike
        if price_change_pct >= PRICE_SPIKE_PCT and current_volume_1h >= MIN_VOLUME_USD:
            # Check cooldown
            spike_key = f"price_spike_alerted:{token.address}"
            if not r.get(spike_key):
                signals.append({
                    "type": "price_spike",
                    "price_change_pct": price_change_pct,
                    "current_volume": current_volume_1h,
                    "current_price": current_price,
                })
                r.setex(spike_key, 3600, "1")  # 1h cooldown

        # Update baseline
        r.setex(baseline_key, 300, str(current_volume_1h))  # 5min TTL

        if not signals:
            return 0

        return _send_momentum_alerts(token, signals)

    except Exception as e:
        logger.debug("momentum check failed for %s: %s", token.address, e)
        return 0


def _send_momentum_alerts(token, signals: list[dict]) -> int:
    """Send momentum alerts to all Pro users."""
    from bot.core.models import TelegramUser
    from bot.core.tasks import send_alert_message
    from bot.memecoin.models import MemeAlert

    pro_users = TelegramUser.objects.filter(plan="pro")
    total_sent = 0

    for signal in signals:
        message = _format_momentum_alert(token, signal)

        for user in pro_users:
            try:
                send_alert_message.delay(user.telegram_id, message)
                MemeAlert.objects.create(
                    telegram_user=user,
                    token=token,
                    alert_type=MemeAlert.ALERT_MOMENTUM,
                    message_sent=message,
                )
                total_sent += 1
            except Exception as e:
                logger.warning(
                    "momentum alert failed for user %s: %s",
                    user.telegram_id, e
                )

    return total_sent


def _format_momentum_alert(token, signal: dict) -> str:
    """Format a momentum alert for Telegram."""
    from bot.prices.coingecko import format_usd

    symbol = token.symbol or "?"
    signal_type = signal["type"]

    if signal_type == "volume_spike":
        mult = signal.get("multiplier", 0)
        vol = signal.get("current_volume", 0)
        prev_vol = signal.get("prev_volume", 0)
        return (
            f"🚀 *Volume Spike — {symbol}*\n\n"
            f"Chain: {token.chain.upper()}\n"
            f"Volume spike: *{mult:.1f}x*\n"
            f"Current \\(1h\\): {format_usd(vol)}\n"
            f"Previous \\(1h\\): {format_usd(prev_vol)}\n\n"
            f"Address: `{token.address[:16]}…`\n"
            f"Run `/meme check {token.address[:12]}…` to assess risk"
        )

    elif signal_type == "price_spike":
        change = signal.get("price_change_pct", 0)
        price = signal.get("current_price", 0)
        vol = signal.get("current_volume", 0)
        return (
            f"📈 *Price Spike — {symbol}*\n\n"
            f"Chain: {token.chain.upper()}\n"
            f"Price change \\(1h\\): *\\+{change:.1f}%*\n"
            f"Current price: \\${price:.8f}\n"
            f"Volume \\(1h\\): {format_usd(vol)}\n\n"
            f"Address: `{token.address[:16]}…`"
        )

    return f"📊 *Momentum Alert — {symbol}*\n\nUnexpected momentum detected\\."


def get_trending_tokens(limit: int = 10) -> list[dict]:
    """
    Return a list of trending tokens based on recent volume and momentum.
    Used by the /meme trending command.
    """
    from bot.memecoin.models import MemeToken

    tokens = (
        MemeToken.objects.filter(
            status=MemeToken.STATUS_WATCHING,
            volume_1h__isnull=False,
        )
        .order_by("-volume_1h")[:limit]
    )

    result = []
    for t in tokens:
        result.append({
            "symbol": t.symbol or "?",
            "address": t.address,
            "chain": t.chain,
            "volume_1h": t.volume_1h or 0,
            "mcap": t.market_cap_usd or 0,
            "price": t.price_usd or 0,
        })
    return result