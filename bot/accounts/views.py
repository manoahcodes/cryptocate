"""
Registration and dashboard views for WhaleWatch.

Registration flow:
  1. Telegram bot sends /start → generates one-time token in Redis
  2. User taps link → GET /accounts/register/?token=xxx
  3. User chooses auth method (Google / GitHub / email)
  4. Allauth handles OAuth or email+code flow
  5. Redirect to /accounts/dashboard/ (via LOGIN_REDIRECT_URL)
  6. DashboardView processes token: links Django User → TelegramUser
  7. Celery sends Telegram confirmation message

References:
  https://docs.allauth.org/en/latest/
  https://docs.djangoproject.com/en/5.2/topics/http/views/
"""

import logging

import redis
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from bot.core.models import TelegramUser

logger = logging.getLogger(__name__)

SESSION_KEY = "pending_reg_token"


def _get_redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _process_registration_token(django_user, token: str) -> tuple[bool, str]:
    """
    Link a Django User to their TelegramUser via a one-time Redis token.

    Returns:
        (True, success_message) on success
        (False, error_message) on failure
    """
    r = _get_redis()
    redis_key = f"reg_link:{token}"

    # Step 1: retrieve telegram_id from Redis
    telegram_id_str = r.get(redis_key)
    if not telegram_id_str:
        return False, "⚠️ Registration link expired. Please run /start in Telegram to get a new link."

    try:
        telegram_id = int(telegram_id_str)
    except ValueError:
        return False, "Invalid registration token."

    # Step 2: get TelegramUser
    try:
        tg_user = TelegramUser.objects.get(telegram_id=telegram_id)
    except TelegramUser.DoesNotExist:
        return False, "Telegram session not found. Please run /start again."

    # Step 3: guard — Telegram account already linked to a different email
    if tg_user.user_id and tg_user.user_id != django_user.pk:
        return False, "This Telegram account is already linked to a different email address."

    # Step 4: guard — this email already linked to a different Telegram account
    if (
        TelegramUser.objects.filter(user=django_user)
        .exclude(pk=tg_user.pk)
        .exists()
    ):
        return False, "This email is already linked to a different Telegram account."

    # Step 5: link accounts
    tg_user.user = django_user
    tg_user.save(update_fields=["user", "updated_at"])

    # Step 6: consume token (one-use only)
    r.delete(redis_key)

    # Step 7: queue Telegram confirmation message
    try:
        from bot.core.tasks import send_message

        # Plain text — no parse_mode needed, avoids MarkdownV2 escape issues.
        # send_message defaults to parse_mode=None (plain text).
        confirmation_text = (
            "✅ Registration complete!\n\n"
            "Your account is ready. You can now use all bot features.\n"
            "Run /start to see your dashboard."
        )
        send_message.delay(telegram_id, confirmation_text)
    except Exception as e:
        logger.warning("Failed to queue Telegram confirmation: %s", e)

    return True, "✅ Account linked! Check Telegram for confirmation."


class RegisterView(View):
    """
    GET /accounts/register/?token=UUID

    Entry point from the Telegram bot's "Register to start" button.
    Shows the registration options page with social login buttons.
    """

    def get(self, request):
        token = request.GET.get("token", "").strip()

        # Step 1: token is required
        if not token:
            return render(request, "accounts/register_expired.html", status=400)

        # Step 2: validate token exists in Redis
        r = _get_redis()
        telegram_id_str = r.get(f"reg_link:{token}")
        if not telegram_id_str:
            return render(request, "accounts/register_expired.html", status=410)

        # Step 3: if already authenticated, redirect to dashboard
        if request.user.is_authenticated:
            return redirect(f"/accounts/dashboard/?token={token}")

        # Step 4: store token in session for post-login retrieval
        request.session[SESSION_KEY] = token

        # Step 5: get TelegramUser for display
        telegram_username = ""
        try:
            tg_user = TelegramUser.objects.get(telegram_id=int(telegram_id_str))
            telegram_username = tg_user.username or tg_user.first_name or ""
        except (TelegramUser.DoesNotExist, ValueError):
            pass

        # Step 6: render registration options page
        return render(
            request,
            "accounts/register.html",
            {"telegram_username": telegram_username, "token": token},
        )


@method_decorator(login_required, name="dispatch")
class DashboardView(View):
    """
    GET /accounts/dashboard/

    Post-login status page. Processes pending registration token
    to link Django User to TelegramUser.
    """

    def get(self, request):
        # Step 1: get token from query string or session
        token = request.GET.get("token") or request.session.get(SESSION_KEY, "")

        link_success = None
        link_message = ""

        # Step 2: process registration token if present
        if token:
            link_success, link_message = _process_registration_token(
                request.user, token
            )
            # Pop token from session (consumed)
            request.session.pop(SESSION_KEY, None)

        # Step 3: load TelegramUser if linked
        tg_user = None
        try:
            tg_user = request.user.telegram_user
        except Exception:
            pass

        # Step 4: render dashboard
        context = {
            "tg_user": tg_user,
            "link_success": link_success,
            "link_message": link_message,
            "user": request.user,
        }
        return render(request, "accounts/dashboard.html", context)