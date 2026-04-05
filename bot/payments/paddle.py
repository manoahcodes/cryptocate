"""
Paddle Billing integration for WhaleWatch.

Package: paddle-python-sdk==1.13.0
Installs as: paddle_billing  (NOT `paddle` — that is an unrelated package)

Correct imports:
  from paddle_billing import Client, Environment, Options
  from paddle_billing.Notifications import Secret, Verifier

References:
  https://github.com/PaddleHQ/paddle-python-sdk
  https://developer.paddle.com/api-reference/overview
  https://developer.paddle.com/webhooks/signature-verification
"""

import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class NeedsRegistration(Exception):
    """
    Raised when a TelegramUser has not completed registration.
    The /subscribe command catches this and sends the registration link.
    """


# ── SDK client ─────────────────────────────────────────────────────────────────

def _get_paddle_client():
    """
    Return an initialised paddle_billing Client.

    Correct import path: paddle_billing (NOT paddle)
    Reference: https://github.com/PaddleHQ/paddle-python-sdk
    """
    from paddle_billing import Client, Environment, Options

    env = Environment.SANDBOX if settings.PADDLE_SANDBOX else Environment.PRODUCTION
    return Client(
        settings.PADDLE_API_KEY,
        options=Options(Environment.SANDBOX if settings.PADDLE_SANDBOX else Environment.PRODUCTION),
    )


# ── Customer management ────────────────────────────────────────────────────────

def get_or_create_paddle_customer(tg_user) -> str:
    """
    Get or create a Paddle customer for a TelegramUser.
    Returns the Paddle customer ID string.

    Always requires a real verified email — never a placeholder.
    Raises NeedsRegistration if no verified email is linked.
    """
    email = tg_user.verified_email
    if not email:
        raise NeedsRegistration(
            f"TelegramUser {tg_user.telegram_id} has no verified email. "
            "Registration must be completed before creating a Paddle customer."
        )

    if tg_user.paddle_customer_id:
        return tg_user.paddle_customer_id

    paddle = _get_paddle_client()

    try:
        from paddle_billing.Resources.Customers.Operations import CreateCustomer

        customer = paddle.customers.create(
            CreateCustomer(
                email=email,
                name=tg_user.first_name or tg_user.username or "WhaleWatch User",
            )
        )
        customer_id = customer.id

        tg_user.paddle_customer_id = customer_id
        tg_user.save(update_fields=["paddle_customer_id", "updated_at"])

        logger.info(
            "Created Paddle customer %s for TelegramUser %s",
            customer_id,
            tg_user.telegram_id,
        )
        return customer_id

    except Exception as e:
        logger.error(
            "Failed to create Paddle customer for TelegramUser %s: %s",
            tg_user.telegram_id,
            e,
        )
        raise


def create_checkout_url(tg_user) -> str:
    """
    Create a Paddle checkout URL for the Pro subscription.
    Raises NeedsRegistration if user has no verified email.
    """
    customer_id = get_or_create_paddle_customer(tg_user)
    paddle      = _get_paddle_client()

    try:
        from paddle_billing.Resources.Transactions.Operations import CreateTransaction
        from paddle_billing.Resources.Transactions.Operations.Create.TransactionCreateItem import TransactionCreateItem
        from paddle_billing.Entities.Shared import (
            CollectionMode
        )

        transaction = paddle.transactions.create(
            CreateTransaction(
                items=[
                    TransactionCreateItem(
                        price_id=settings.PADDLE_PRICE_ID,
                        quantity=1,
                    )
                ],
                customer_id=customer_id,
                collection_mode=CollectionMode.Automatic,
            )
        )

        checkout_url = transaction.checkout.url
        logger.info(
            "Created checkout URL for TelegramUser %s",
            tg_user.telegram_id,
        )
        return checkout_url

    except Exception as e:
        logger.error(
            "Failed to create checkout URL for TelegramUser %s: %s",
            tg_user.telegram_id,
            e,
        )
        raise


# ── Webhook verification ───────────────────────────────────────────────────────

def verify_paddle_webhook(request) -> bool:
    """
    Verify a Paddle webhook request signature using the official SDK verifier.

    Reference: https://developer.paddle.com/webhooks/signature-verification
    Usage:
      from paddle_billing.Notifications import Secret, Verifier
      integrity_check = Verifier().verify(request, Secret('WEBHOOK_SECRET_KEY'))
    """
    secret = settings.PADDLE_WEBHOOK_SECRET
    if not secret:
        logger.warning("PADDLE_WEBHOOK_SECRET not set — skipping webhook verification")
        return True

    try:
        from paddle_billing.Notifications import Secret, Verifier
        return Verifier().verify(request, Secret(secret))
    except Exception as e:
        logger.error("Paddle webhook verification error: %s", e)
        return False


# ── Webhook event handler ──────────────────────────────────────────────────────

def handle_paddle_event(event_type: str, data: dict) -> None:
    """
    Route and handle incoming Paddle webhook events.

    Supported events:
      subscription.activated  — upgrade user to Pro
      subscription.canceled   — downgrade to Free
      subscription.paused     — downgrade to Free
      subscription.updated    — update renewal date
      transaction.completed   — log successful payment

    Reference: https://developer.paddle.com/webhooks/event-types
    """
    from bot.core.models import TelegramUser

    event_data  = data.get("data", {})
    customer_id = event_data.get("customer_id", "")

    if not customer_id:
        logger.warning("Paddle event %s has no customer_id — ignoring", event_type)
        return

    try:
        tg_user = TelegramUser.objects.get(paddle_customer_id=customer_id)
    except TelegramUser.DoesNotExist:
        logger.warning(
            "No TelegramUser found for Paddle customer %s (event: %s)",
            customer_id,
            event_type,
        )
        return

    logger.info(
        "Paddle event %s for TelegramUser %s",
        event_type,
        tg_user.telegram_id,
    )

    if event_type == "subscription.activated":
        _handle_subscription_activated(tg_user, event_data)
    elif event_type in ("subscription.canceled", "subscription.paused"):
        _handle_subscription_ended(tg_user, event_data)
    elif event_type == "subscription.updated":
        _handle_subscription_updated(tg_user, event_data)
    elif event_type == "transaction.completed":
        logger.info("Transaction completed for TelegramUser %s", tg_user.telegram_id)
    else:
        logger.debug("Unhandled Paddle event type: %s", event_type)


# ── Event handlers ─────────────────────────────────────────────────────────────

def _handle_subscription_activated(tg_user, event_data: dict) -> None:
    subscription_id = event_data.get("id", "")
    ends_at_str     = (event_data.get("current_billing_period") or {}).get("ends_at")

    tg_user.plan                  = "pro"
    tg_user.paddle_subscription_id = subscription_id

    if ends_at_str:
        try:
            from datetime import datetime
            tg_user.subscription_ends_at = datetime.fromisoformat(
                ends_at_str.replace("Z", "+00:00")
            )
        except ValueError:
            pass

    tg_user.save(update_fields=[
        "plan", "paddle_subscription_id", "subscription_ends_at", "updated_at"
    ])

    logger.info(
        "TelegramUser %s upgraded to Pro (subscription %s)",
        tg_user.telegram_id,
        subscription_id,
    )

    try:
        from bot.core.tasks import send_message
        send_message.delay(
            tg_user.telegram_id,
            "⭐ WhaleWatch Pro activated!\n\n"
            "You now have access to all Pro features:\n"
            "• 10 wallets · 5 chains\n"
            "• 1 ETH threshold\n"
            "• Daily digest · Copy-trade signals\n"
            "• Full memecoin suite\n\n"
            "Run /start to see your updated dashboard\\.",
        )
    except Exception as e:
        logger.warning("Failed to send Pro activation message: %s", e)


def _handle_subscription_ended(tg_user, event_data: dict) -> None:
    tg_user.plan                  = "free"
    tg_user.subscription_ends_at  = timezone.now()
    tg_user.save(update_fields=["plan", "subscription_ends_at", "updated_at"])

    logger.info("TelegramUser %s downgraded to Free", tg_user.telegram_id)

    try:
        from bot.core.tasks import send_message
        send_message.delay(
            tg_user.telegram_id,
            "ℹ️ Your WhaleWatch Pro subscription has ended.\n\n"
            "You've been moved to the Free plan.\n"
            "Use /subscribe to reactivate Pro at any time.",
        )
    except Exception as e:
        logger.warning("Failed to send subscription ended message: %s", e)


def _handle_subscription_updated(tg_user, event_data: dict) -> None:
    ends_at_str = (event_data.get("current_billing_period") or {}).get("ends_at")
    if ends_at_str:
        try:
            from datetime import datetime
            tg_user.subscription_ends_at = datetime.fromisoformat(
                ends_at_str.replace("Z", "+00:00")
            )
            tg_user.save(update_fields=["subscription_ends_at", "updated_at"])
            logger.info(
                "Updated subscription end date for TelegramUser %s",
                tg_user.telegram_id,
            )
        except ValueError as e:
            logger.warning("Could not parse subscription ends_at '%s': %s", ends_at_str, e)