"""
Management command: set_webhook
Registers the bot's webhook URL with the Telegram Bot API.

Usage:
    python manage.py set_webhook

Reference:
  https://core.telegram.org/bots/api#setwebhook
  https://docs.djangoproject.com/en/5.2/howto/custom-management-commands/
"""

import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from telegram import Bot


class Command(BaseCommand):
    help = "Register the Telegram webhook URL with the Bot API."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete the current webhook instead of setting one.",
        )

    def handle(self, *args, **options):
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            raise CommandError(
                "TELEGRAM_BOT_TOKEN is not set. "
                "Add it to your .env file before running set_webhook."
            )

        webhook_url = settings.WEBHOOK_URL
        if not webhook_url and not options["delete"]:
            raise CommandError(
                "WEBHOOK_URL is not set. "
                "Add it to your .env file (e.g. https://your-app.railway.app)."
            )

        asyncio.run(self._run(token, webhook_url, options["delete"]))

    async def _run(self, token: str, webhook_url: str, delete: bool):
        bot = Bot(token=token)
        async with bot:
            if delete:
                result = await bot.delete_webhook(drop_pending_updates=True)
                if result:
                    self.stdout.write(
                        self.style.SUCCESS("✅ Webhook deleted successfully.")
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR("❌ Failed to delete webhook.")
                    )
                return

            full_url = f"{webhook_url.rstrip('/')}/bot/webhook/"
            self.stdout.write(f"Setting webhook to: {full_url}")

            result = await bot.set_webhook(
                url=full_url,
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True,
            )

            if result:
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Webhook set to: {full_url}")
                )
                # Print current webhook info
                info = await bot.get_webhook_info()
                self.stdout.write(f"   URL:             {info.url}")
                self.stdout.write(f"   Pending updates: {info.pending_update_count}")
                self.stdout.write(f"   Last error:      {info.last_error_message or 'none'}")
            else:
                self.stdout.write(
                    self.style.ERROR("❌ Failed to set webhook. Check your TELEGRAM_BOT_TOKEN.")
                )
