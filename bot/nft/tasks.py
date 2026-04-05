"""
Feature 17 — NFT monitoring Celery task.
Runs every 300 seconds (5 minutes).
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def check_nft_collections():
    """
    Every 300s — check all watched NFT collections:
      1. Floor price drop/rise alerts (Free + Pro)
      2. Volume spike detection (Pro)
      3. Sweep detection (Pro)
      4. Whale wallet NFT activity (Pro)
    """
    from bot.core.models import TelegramUser
    from bot.core.tasks import send_alert_message
    from bot.nft.models import NFTAlert, WatchedCollection
    from bot.nft.monitor import (
        check_floor_price,
        check_sweep,
        check_volume_spike,
        check_whale_nft_activity,
        format_floor_alert,
        format_sweep_alert,
        format_volume_spike_alert,
        format_whale_nft_alert,
    )

    collections  = WatchedCollection.objects.select_related("telegram_user").all()
    checked      = 0
    alerted      = 0

    for col in collections:
        user = col.telegram_user
        try:
            # ── Floor price (Free + Pro) ───────────────────────────────────
            for alert_data in check_floor_price(col):
                message = format_floor_alert(col, alert_data)
                send_alert_message.delay(user.telegram_id, message, parse_mode="HTML")
                NFTAlert.objects.create(
                    telegram_user = user,
                    collection    = col,
                    alert_type    = alert_data["type"],
                    message_sent  = message,
                )
                alerted += 1

            if user.is_pro():
                # ── Volume spike (Pro) ─────────────────────────────────────
                for alert_data in check_volume_spike(col):
                    message = format_volume_spike_alert(col, alert_data)
                    send_alert_message.delay(user.telegram_id, message, parse_mode="HTML")
                    NFTAlert.objects.create(
                        telegram_user = user,
                        collection    = col,
                        alert_type    = NFTAlert.TYPE_VOLUME_SPIKE,
                        message_sent  = message,
                    )
                    alerted += 1

                # ── Sweep detection (Pro) ──────────────────────────────────
                for alert_data in check_sweep(col):
                    message = format_sweep_alert(col, alert_data)
                    send_alert_message.delay(user.telegram_id, message, parse_mode="HTML")
                    NFTAlert.objects.create(
                        telegram_user = user,
                        collection    = col,
                        alert_type    = NFTAlert.TYPE_SWEEP,
                        message_sent  = message,
                    )
                    alerted += 1

            checked += 1

        except Exception as e:
            logger.error(
                "check_nft_collections: error for %s: %s", col.slug, e
            )

    # ── Whale NFT activity (Pro only, once per user not per collection) ────
    pro_users = TelegramUser.objects.filter(plan="pro")
    for user in pro_users:
        try:
            activities = check_whale_nft_activity(user)
            for activity in activities:
                message = format_whale_nft_alert(activity)
                send_alert_message.delay(user.telegram_id, message, parse_mode="HTML")
                NFTAlert.objects.create(
                    telegram_user  = user,
                    alert_type     = (
                        NFTAlert.TYPE_WHALE_BUY
                        if activity["direction"] == "buy"
                        else NFTAlert.TYPE_WHALE_SELL
                    ),
                    tx_hash        = activity["tx_hash"],
                    wallet_address = activity["wallet"].address,
                    wallet_label   = activity["wallet"].label,
                    token_id       = activity["token_id"],
                    message_sent   = message,
                )
                alerted += 1
        except Exception as e:
            logger.error(
                "check_nft_collections: whale activity error for %s: %s",
                user.telegram_id, e,
            )

    logger.info("check_nft_collections: checked=%d alerted=%d", checked, alerted)
    return {"checked": checked, "alerted": alerted}