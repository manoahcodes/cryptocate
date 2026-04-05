"""
Allauth adapters for WhaleWatch.

References:
  https://docs.allauth.org/en/latest/account/advanced.html#adapter
  https://docs.allauth.org/en/latest/socialaccount/advanced.html
"""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings


class WhaleWatchAccountAdapter(DefaultAccountAdapter):
    """
    Custom account adapter.
    Reference: https://docs.allauth.org/en/latest/account/advanced.html#adapter
    """

    def get_login_redirect_url(self, request) -> str:
        """Redirect to dashboard after email/password login."""
        return "/accounts/dashboard/"

    def get_email_verification_redirect_url(self, request) -> str:
        """Redirect to dashboard after email verification."""
        return "/accounts/dashboard/"

    def send_mail(self, template_prefix: str, email: str, context: dict):
        """
        Inject SITE_NAME and domain into allauth email context before sending.
        Reference: https://docs.djangoproject.com/en/5.2/topics/email/
        """
        context.setdefault("SITE_NAME", getattr(settings, "SITE_NAME", "WhaleWatch"))
        # Derive domain from WEBHOOK_URL
        webhook_url = getattr(settings, "WEBHOOK_URL", "http://localhost:8000")
        domain = webhook_url.replace("https://", "").replace("http://", "").split("/")[0]
        context.setdefault("domain", domain)
        super().send_mail(template_prefix, email, context)


class WhaleWatchSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom social account adapter.
    Reference: https://docs.allauth.org/en/latest/socialaccount/advanced.html
    """

    def is_open_for_signup(self, request, sociallogin) -> bool:
        """Social signup is always open."""
        return True

    def populate_user(self, request, sociallogin, data):
        """
        Ensure email is set from social provider data.
        Reference: https://docs.allauth.org/en/latest/socialaccount/advanced.html
        """
        user = super().populate_user(request, sociallogin, data)
        # Ensure email is set — required for billing
        if not user.email and data.get("email"):
            user.email = data["email"]
        return user
