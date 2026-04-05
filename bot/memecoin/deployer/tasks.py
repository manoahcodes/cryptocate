"""
Feature 13 — Deployer wallet monitor Celery task.
Runs every 180 seconds.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def check_deployer_wallets():
    """
    Every 180s — check all tracked deployer wallets for new token deployments.
    Alerts the owning Pro user when a new contract is found.
    Reference: https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
    """
    from bot.core.tasks import send_alert_message
    from bot.memecoin.deployer.tracker import (
        check_deployer_for_new_tokens,
        format_deployer_alert,
    )
    from bot.memecoin.models import MemeAlert, MemeToken, TrackedDeployer

    deployers = TrackedDeployer.objects.select_related("telegram_user").all()

    checked = 0
    alerted = 0

    for deployer in deployers:
        # Only alert Pro users
        if not deployer.telegram_user.is_pro():
            continue

        try:
            new_deployments = check_deployer_for_new_tokens(deployer)

            for deployment in new_deployments:
                contract_addr = deployment["contract_address"]

                # Create a MemeToken entry for the new contract
                token, _ = MemeToken.objects.get_or_create(
                    address=contract_addr.lower(),
                    chain=deployer.chain,
                    defaults={
                        "status": MemeToken.STATUS_NEW,
                    },
                )

                message = format_deployer_alert(deployer, deployment)

                MemeAlert.objects.create(
                    telegram_user=deployer.telegram_user,
                    token=token,
                    alert_type=MemeAlert.ALERT_DEPLOYER_LAUNCH,
                    message_sent=message,
                )

                send_alert_message.delay(
                    deployer.telegram_user.telegram_id,
                    message,
                )
                alerted += 1

            checked += 1

        except Exception as e:
            logger.error(
                "check_deployer_wallets: error for deployer %s: %s",
                deployer.address[:12],
                e,
            )

    logger.info("check_deployer_wallets: checked=%d alerted=%d", checked, alerted)
    return {"checked": checked, "alerted": alerted}
