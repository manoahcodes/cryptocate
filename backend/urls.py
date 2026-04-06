"""
WhaleWatch URL configuration.
Reference: https://docs.djangoproject.com/en/5.2/topics/http/views/
"""

from django.contrib import admin
from django.urls import include, path
from health_check.views import HealthCheckView
from backend.views import telegram_redirect_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("allauth.urls")),
    # Our accounts app: /accounts/register/ and /accounts/dashboard/
    path("accounts/", include("bot.accounts.urls")),
    # Telegram + Paddle webhooks
    path("bot/", include("bot.core.urls")),
    # Health check
    path("health/", HealthCheckView.as_view()),
    path("", telegram_redirect_view)
]
