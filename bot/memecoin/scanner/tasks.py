"""
Feature 11 — DexScreener new pair scanner Celery task.
Runs every 300 seconds.
"""

import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)

SCAN_CHAINS = {
    "eth":  "ethereum",
    "arb":  "arbitrum",
    "base": "base",
    "bsc":  "bsc",
    "sol":  "solana",
}


@shared_task
def scan_new_meme_pairs():
    """
    Every 300s — scan DexScreener for new token pairs meeting criteria.

    For each new token found:
      1. Create the MemeToken record
      2. Run rug check immediately and store the score
      3. Mark as Pump.fun if it's a Solana token with bonding curve data
      4. Alert all Pro users
    """
    if not settings.MEME_SCAN_ENABLED:
        return {"skipped": True, "reason": "MEME_SCAN_ENABLED=False"}

    from bot.memecoin.models import MemeToken
    from bot.memecoin.scanner.dexscreener import get_new_pairs

    new_count     = 0
    alerted_count = 0

    for chain_key, dex_chain_id in SCAN_CHAINS.items():
        try:
            pairs = get_new_pairs(
                chain_id=dex_chain_id,
                limit=10,
                min_liquidity_usd=settings.MEME_MIN_LIQUIDITY_USD,
                min_buys_1h=settings.MEME_MIN_BUYS_1H,
            )

            for pair in pairs:
                token_addr = (pair.get("baseToken") or {}).get("address", "")
                if not token_addr:
                    continue

                token, created = MemeToken.objects.get_or_create(
                    address=token_addr.lower(),
                    chain=chain_key,
                    defaults={
                        "symbol":        (pair.get("baseToken") or {}).get("symbol", ""),
                        "name":          (pair.get("baseToken") or {}).get("name", ""),
                        "pair_address":  pair.get("pairAddress", ""),
                        "dex":           pair.get("dexId", ""),
                        "status":        MemeToken.STATUS_WATCHING,
                        "price_usd":     _safe_float(pair.get("priceUsd")),
                        "liquidity_usd": (pair.get("liquidity") or {}).get("usd"),
                        "market_cap_usd": pair.get("marketCap"),
                        "volume_1h":     (pair.get("volume") or {}).get("h1"),
                        "buys_1h":       (pair.get("txns") or {}).get("h1", {}).get("buys"),
                        "sells_1h":      (pair.get("txns") or {}).get("h1", {}).get("sells"),
                    },
                )

                if not created:
                    # Token already known — market data will be refreshed
                    # by check_meme_tokens which runs every 120s
                    continue

                new_count += 1

                # Run rug check immediately on new tokens so the score
                # is available before any alerts go out
                _run_rugcheck_for_new_token(token)

                # Alert Pro users
                alerted_count += _alert_pro_users_new_pair(token, pair)

        except Exception as e:
            logger.error("scan_new_meme_pairs: chain %s error: %s", chain_key, e)

    # Discover fresh Pump.fun launches on Solana
    try:
        from bot.memecoin.pumpfun.monitor import discover_new_pumpfun_tokens
        pf_tokens = discover_new_pumpfun_tokens(limit=20)
        for token in pf_tokens:
            new_count += 1
            # Pump.fun tokens on Solana — run rugcheck via RugCheck API
            _run_rugcheck_for_new_token(token)
            alerted_count += _alert_pro_users_new_pair(token, {})
    except Exception as e:
        logger.error("scan_new_meme_pairs: pumpfun discovery error: %s", e)

    logger.info("scan_new_meme_pairs: new=%d alerted=%d", new_count, alerted_count)
    return {"new": new_count, "alerted": alerted_count}


def _run_rugcheck_for_new_token(token) -> None:
    """
    Run rug check immediately when a new token is discovered.
    Stores the result in token.rugcheck_score, rugcheck_summary,
    and rugcheck_checked_at.

    This is called synchronously inside the scanner task so the score
    is available in the alert message sent to users.
    """
    try:
        from bot.memecoin.rugcheck.checker import cache_token_rugcheck
        cache_token_rugcheck(token.address, token.chain)
        # Refresh the local object so the alert can show the score
        token.refresh_from_db()
        logger.debug(
            "RugCheck completed for new token %s (%s): score=%s",
            token.address[:12], token.chain, token.rugcheck_score,
        )
    except Exception as e:
        logger.warning(
            "_run_rugcheck_for_new_token failed for %s: %s",
            token.address[:12], e,
        )


def _safe_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def _alert_pro_users_new_pair(token, pair: dict) -> int:
    """Send a new pair alert to all active Pro users."""
    from bot.core.models import TelegramUser
    from bot.core.tasks import send_alert_message
    from bot.memecoin.models import MemeAlert

    pro_users = TelegramUser.objects.filter(plan="pro")
    if not pro_users.exists():
        return 0

    symbol = token.symbol or "?"
    liq    = token.liquidity_usd or 0
    buys   = token.buys_1h or 0
    chain  = token.chain.upper()

    # Build rug score line if available
    if token.rugcheck_score is not None:
        score      = token.rugcheck_score
        risk_emoji = "🔴" if score >= 700 else "🟠" if score >= 400 else "🟡" if score >= 100 else "🟢"
        score_line = f"\nRug Score: {risk_emoji} {score:.0f}/1000"
    else:
        score_line = ""

    # Pump.fun progress line
    if token.is_pump_fun and token.bonding_curve_pct is not None:
        filled    = int(token.bonding_curve_pct / 10)
        bar       = "█" * filled + "░" * (10 - filled)
        pump_line = f"\nBonding Curve: {bar} {token.bonding_curve_pct:.1f}%"
    else:
        pump_line = ""

    message = (
        f"🔭 <b>New Meme Pair Detected</b>\n\n"
        f"Token: <b>{symbol}</b>\n"
        f"Chain: {chain}\n"
        f"Liquidity: ${liq:,.0f}\n"
        f"Buys (1h): {buys}\n"
        f"DEX: {token.dex or 'unknown'}"
        f"{score_line}"
        f"{pump_line}\n\n"
        f"<code>{token.address}</code>"
    )

    sent = 0
    for user in pro_users:
        try:
            # HTML parse mode — message uses HTML formatting
            send_alert_message.delay(user.telegram_id, message, parse_mode="HTML")
            MemeAlert.objects.create(
                telegram_user=user,
                token=token,
                alert_type=MemeAlert.ALERT_NEW_PAIR,
                message_sent=message,
            )
            sent += 1
        except Exception as e:
            logger.warning(
                "Failed to alert user %s for new pair: %s", user.telegram_id, e
            )

    return sent