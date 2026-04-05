"""
Webhook views for Telegram and Paddle.

References:
  https://core.telegram.org/bots/api#setwebhook
  https://developer.paddle.com/webhooks/signature-verification
  https://developer.paddle.com/webhooks/event-types
"""

import json
import logging

from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class TelegramWebhookView(View):
    """
    Receives updates from Telegram and dispatches to PTB handlers.
    Reference: https://core.telegram.org/bots/api#update
    """

    _ptb_app = None

    def _get_app(self):
        if TelegramWebhookView._ptb_app is None:
            from bot.core.telegram_bot import build_application
            TelegramWebhookView._ptb_app = build_application()
        return TelegramWebhookView._ptb_app

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponse(status=400)

        import asyncio
        from telegram import Update

        app = self._get_app()

        async def process():
            async with app:
                update = Update.de_json(data, app.bot)
                await app.process_update(update)

        try:
            asyncio.run(process())
        except Exception as e:
            logger.error("Error processing Telegram update: %s", e, exc_info=True)

        return HttpResponse(status=200)

    def get(self, request):
        return JsonResponse({"status": "telegram webhook active"})


@method_decorator(csrf_exempt, name="dispatch")
class PaddleWebhookView(View):
    """
    Receives and verifies Paddle webhook events.

    Verification uses the official paddle_billing SDK:
      from paddle_billing.Notifications import Secret, Verifier
      Verifier().verify(request, Secret('WEBHOOK_SECRET_KEY'))

    Reference: https://developer.paddle.com/webhooks/signature-verification
    """

    def post(self, request):
        # Verify signature using paddle_billing SDK
        if not self._verify_signature(request):
            logger.warning("Paddle webhook: invalid or unverifiable signature")
            return HttpResponse(status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            logger.warning("Paddle webhook: invalid JSON body")
            return HttpResponse(status=400)

        event_type = data.get("event_type", "")
        logger.info("Paddle webhook received: %s", event_type)

        try:
            from bot.payments.paddle import handle_paddle_event
            handle_paddle_event(event_type, data)
        except Exception as e:
            logger.error("Paddle webhook handler error: %s", e, exc_info=True)
            # Return 200 anyway — Paddle will retry on 5xx, not 4xx
            return HttpResponse(status=200)

        return HttpResponse(status=200)

    def _verify_signature(self, request) -> bool:
        """
        Verify using the paddle_billing SDK Verifier.
        Falls back to True (skip) if PADDLE_WEBHOOK_SECRET is not set.

        Reference: https://developer.paddle.com/webhooks/signature-verification
        """
        from bot.payments.paddle import verify_paddle_webhook
        return verify_paddle_webhook(request)