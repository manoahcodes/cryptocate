"""
Feature 2 — Daily digest Celery task.
Runs hourly; sends digests to users whose digest_hour matches the current UTC hour.
"""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def send_daily_digests():
    """
    Hourly task — check which Pro users have their digest_hour set to the
    current UTC hour and send them their daily digest.
    Reference: https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
    """
    from bot.core.models import TelegramUser
    from bot.core.tasks import send_alert_message
    from bot.digest.builder import build_digest

    current_hour = timezone.now().hour
    users = TelegramUser.objects.filter(
        plan="pro",
        digest_enabled=True,
        digest_hour=current_hour,
    ).select_related("user")

    sent = 0
    for user in users:
        try:
            message = build_digest(user)
            if message:
                send_alert_message.delay(user.telegram_id, message)
                sent += 1
        except Exception as e:
            logger.error(
                "Failed to build/send digest for TelegramUser %s: %s",
                user.telegram_id,
                e,
            )

    logger.info("send_daily_digests: hour=%d sent=%d", current_hour, sent)
    return {"hour": current_hour, "sent": sent}
