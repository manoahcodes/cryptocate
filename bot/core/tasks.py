"""
Core Celery tasks — wallet polling and Telegram message dispatch.

References:
  https://docs.celeryq.dev/en/stable/userguide/tasks.html
  https://docs.celeryq.dev/en/stable/userguide/tasks.html#retrying
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def poll_all_wallets(self):
    """
    Main polling task — checks all watched wallets for new transactions.
    Runs every 120 seconds via Celery beat.
    """
    try:
        from bot.core.models import WatchedWallet
        from bot.multichain.router import check_wallet_for_alerts

        wallets = WatchedWallet.objects.select_related(
            "telegram_user", "telegram_user__user"
        ).all()

        checked = 0
        alerted = 0

        for wallet in wallets:
            try:
                alerts_sent = check_wallet_for_alerts(wallet)
                alerted += alerts_sent
                checked += 1
            except Exception as e:
                logger.warning(
                    "Failed to check wallet %s (%s): %s",
                    wallet.address,
                    wallet.chain,
                    e,
                )

        logger.info("poll_all_wallets: checked=%d alerted=%d", checked, alerted)
        return {"checked": checked, "alerted": alerted}

    except Exception as exc:
        logger.error("poll_all_wallets failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=10)
def send_message(self, telegram_id: int, text: str, parse_mode: str = None) -> bool:
    """
    Send a Telegram message asynchronously via Celery.

    parse_mode: None (default — plain text, safest for dynamic content)
                "MarkdownV2" — only use when text is fully pre-escaped
                "HTML"       — alternative to MarkdownV2

    The default is plain text (parse_mode=None) to avoid
    BadRequest errors from unescaped special characters.
    Use escape_md() from bot.core.utils when you need MarkdownV2.
    """
    import asyncio
    import telegram

    async def _send():
        bot = telegram.Bot(token=_get_token())
        async with bot:
            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode=parse_mode,
            )

    try:
        asyncio.run(_send())
        return True
    except telegram.error.BadRequest as exc:
        # Log the exact text that caused the parse error for debugging
        logger.error(
            "send_message BadRequest for %s (parse_mode=%s): %s\nText: %r",
            telegram_id, parse_mode, exc, text[:200],
        )
        # Don't retry parse errors — they won't fix themselves
        return False
    except telegram.error.TelegramError as exc:
        logger.error("send_message TelegramError for %s: %s", telegram_id, exc)
        raise self.retry(exc=exc)


@shared_task
def send_alert_message(telegram_id: int, text: str, parse_mode: str = "MarkdownV2") -> bool:
    """
    Send an alert message to a Telegram user.
    Defaults to MarkdownV2 since alert messages are pre-formatted in
    the router/detector modules with escaped content.

    Non-retrying — if an alert fails, move on.
    """
    import asyncio
    import telegram

    async def _send():
        bot = telegram.Bot(token=_get_token())
        async with bot:
            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode=parse_mode,
            )

    try:
        asyncio.run(_send())
        return True
    except telegram.error.BadRequest as exc:
        logger.error(
            "send_alert_message BadRequest for %s (parse_mode=%s): %s\nText: %r",
            telegram_id, parse_mode, exc, text[:200],
        )
        return False
    except Exception as e:
        logger.error("send_alert_message failed for %s: %s", telegram_id, e)
        return False


def _get_token() -> str:
    from backend import settings
    return settings.TELEGRAM_BOT_TOKEN