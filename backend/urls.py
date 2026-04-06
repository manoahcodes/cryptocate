"""
WhaleWatch URL configuration.
Reference: https://docs.djangoproject.com/en/5.2/topics/http/views/
"""

from django.contrib import admin
from django.urls import include, path
from backend.views import health_check, telegram_redirect_view

urlpatterns = [
    path("admin/", admin.site.urls),

    # Our accounts app: /accounts/register/ and /accounts/dashboard/
    path("accounts/", include("allauth.urls")),
    path("accounts/", include("bot.accounts.urls")),

    # Telegram + Paddle webhooks
    path("bot/", include("bot.core.urls")),
    
    # Health check
    path("health/", health_check),
    path("", telegram_redirect_view)
]
