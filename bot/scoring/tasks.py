"""
Feature 7 — Wallet scoring Celery task.
Runs weekly (Sunday 00:00 UTC).
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def score_all_wallets():
    """
    Weekly task — recalculate profitability scores for all Pro wallets.
    Reference: https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
    """
    from bot.core.models import WatchedWallet
    from bot.scoring.calculator import calculate_wallet_score

    # Only score wallets belonging to Pro users
    wallets = WatchedWallet.objects.filter(
        telegram_user__plan="pro"
    ).select_related("telegram_user")

    scored = 0
    failed = 0

    for wallet in wallets:
        try:
            result = calculate_wallet_score(wallet)
            if result:
                scored += 1
        except Exception as e:
            logger.error(
                "score_all_wallets: failed for wallet %s: %s",
                wallet.address,
                e,
            )
            failed += 1

    logger.info("score_all_wallets: scored=%d failed=%d", scored, failed)
    return {"scored": scored, "failed": failed}
