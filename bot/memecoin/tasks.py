"""
Memecoin top-level Celery tasks.
Runs every 120 seconds — updates market data, runs rugcheck on new tokens,
checks pump.fun milestones, and fires momentum/whale-entry alerts.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def check_meme_tokens():
    """
    Every 120s — for all WATCHING tokens:
      1. Refresh market data from DexScreener
      2. Run rug check if not yet scored (new tokens)
      3. Check Pump.fun bonding curve milestones
      4. Fire momentum alerts
      5. Fire whale-entry alerts
    """
    from bot.memecoin.models import MemeToken

    tokens  = MemeToken.objects.filter(status=MemeToken.STATUS_WATCHING)
    checked = 0
    alerted = 0

    for token in tokens:
        try:
            # Step 1 — refresh market data (price, liquidity, volume, buys)
            _refresh_market_data(token)

            # Step 2 — run rug check if score not yet fetched
            _maybe_run_rugcheck(token)

            # Step 3 — check Pump.fun bonding curve milestones
            if token.is_pump_fun:
                _check_pumpfun(token)

            # Step 4 & 5 — momentum + whale entry alerts
            from bot.memecoin.momentum.alerts import check_momentum_for_token
            from bot.memecoin.whale_entry.detector import check_whale_entry_for_token
            alerted += check_momentum_for_token(token)
            alerted += check_whale_entry_for_token(token)

            checked += 1

        except Exception as e:
            logger.warning(
                "check_meme_tokens: error for %s (%s): %s",
                token.address[:12], token.chain, e,
            )

    logger.info("check_meme_tokens: checked=%d alerted=%d", checked, alerted)
    return {"checked": checked, "alerted": alerted}


def _refresh_market_data(token) -> None:
    """
    Pull fresh price/liquidity/volume data from DexScreener and
    write it back to the MemeToken record.

    Pump.fun tokens use the pumpfun library for market data instead —
    that's handled inside check_pumpfun_milestones() which calls
    _sync_token_data() directly.
    """
    if token.is_pump_fun:
        return  # Pump.fun data is refreshed by _check_pumpfun() below

    if not token.pair_address:
        return

    try:
        from bot.memecoin.scanner.dexscreener import get_pair_by_address

        pair = get_pair_by_address(token.pair_address, chain=token.chain)
        if not pair:
            return

        from bot.memecoin.models import MemeToken

        update_fields = {}

        price = pair.get("priceUsd")
        if price is not None:
            try:
                update_fields["price_usd"] = float(price)
            except (ValueError, TypeError):
                pass

        liq = (pair.get("liquidity") or {}).get("usd")
        if liq is not None:
            update_fields["liquidity_usd"] = float(liq)

        mcap = pair.get("marketCap") or pair.get("fdv")
        if mcap is not None:
            update_fields["market_cap_usd"] = float(mcap)

        vol = (pair.get("volume") or {}).get("h1")
        if vol is not None:
            update_fields["volume_1h"] = float(vol)

        txns_h1 = (pair.get("txns") or {}).get("h1", {})
        buys = txns_h1.get("buys")
        sells = txns_h1.get("sells")
        if buys is not None:
            update_fields["buys_1h"] = int(buys)
        if sells is not None:
            update_fields["sells_1h"] = int(sells)

        if update_fields:
            MemeToken.objects.filter(pk=token.pk).update(**update_fields)
            # Refresh local object so momentum checker sees fresh data
            for field, value in update_fields.items():
                setattr(token, field, value)

    except Exception as e:
        logger.debug(
            "_refresh_market_data failed for %s: %s", token.address[:12], e
        )


def _maybe_run_rugcheck(token) -> None:
    """
    Run a rug check and cache the score if:
      - rugcheck_score is still None (never been checked), OR
      - last check was more than 24 hours ago

    This ensures every new token gets scored, and scores are
    periodically refreshed for tokens we keep watching.
    """
    from django.utils import timezone
    from datetime import timedelta

    needs_check = (
        token.rugcheck_score is None
        or (
            token.rugcheck_checked_at is not None
            and token.rugcheck_checked_at < timezone.now() - timedelta(hours=24)
        )
    )

    if not needs_check:
        return

    try:
        from bot.memecoin.rugcheck.checker import cache_token_rugcheck
        cache_token_rugcheck(token.address, token.chain)
        logger.debug("RugCheck scored: %s (%s)", token.address[:12], token.chain)
    except Exception as e:
        logger.debug(
            "_maybe_run_rugcheck failed for %s: %s", token.address[:12], e
        )


def _check_pumpfun(token) -> None:
    """
    Check Pump.fun bonding curve milestones and update the token record.
    Uses the pumpfun library to fetch live bonding_curve_progress.

    This both:
      - Updates bonding_curve_pct, market_cap_usd, status in the DB
      - Fires milestone alerts to Pro users when thresholds are crossed
    """
    try:
        from bot.core.models import TelegramUser
        from bot.memecoin.pumpfun.monitor import (
            alert_pumpfun_milestones_for_all,
            check_pumpfun_milestones,
        )

        milestones = check_pumpfun_milestones(token)

        if milestones:
            pro_users = TelegramUser.objects.filter(plan="pro")
            # alert_pumpfun_milestones_for_all re-checks all tokens,
            # so we call it directly only if milestones were found
            _send_pumpfun_alerts(token, milestones, pro_users)

    except Exception as e:
        logger.debug(
            "_check_pumpfun failed for %s: %s", token.address[:12], e
        )


def _send_pumpfun_alerts(token, milestones: list, pro_users) -> None:
    """Send Pump.fun milestone alerts to all Pro users."""
    from bot.core.tasks import send_alert_message
    from bot.memecoin.models import MemeAlert
    from bot.memecoin.pumpfun.monitor import format_pumpfun_alert

    for milestone_data in milestones:
        message = format_pumpfun_alert(token, milestone_data)

        for user in pro_users:
            try:
                send_alert_message.delay(user.telegram_id, message)
                MemeAlert.objects.create(
                    telegram_user=user,
                    token=token,
                    alert_type=MemeAlert.ALERT_PUMP_GRADUATION,
                    message_sent=message,
                )
            except Exception as e:
                logger.warning(
                    "Pump.fun alert failed for user %s: %s",
                    user.telegram_id, e,
                )