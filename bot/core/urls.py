"""
Core URL patterns — Telegram webhook and Paddle webhook.
"""

from django.urls import path

from .views import PaddleWebhookView, TelegramWebhookView

urlpatterns = [
    path("webhook/", TelegramWebhookView.as_view(), name="telegram_webhook"),
    path("paddle/webhook/", PaddleWebhookView.as_view(), name="paddle_webhook"),
]
