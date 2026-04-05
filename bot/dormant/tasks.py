"""
Feature 6 — Dormant wallet Celery tasks.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def reset_dormant_flags():
    """
    Weekly task (Sunday 01:00 UTC) — reset dormant_alerted flags so
    wallets that remain dormant can be re-alerted the next time they move.
    Reference: https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
    """
    from bot.core.models import WatchedWallet

    count = WatchedWallet.objects.filter(dormant_alerted=True).update(
        dormant_alerted=False
    )
    logger.info("reset_dormant_flags: reset %d wallets", count)
    return {"reset": count}
