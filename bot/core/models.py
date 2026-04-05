"""
Core models for Cryptocate Bot.
Reference: https://docs.djangoproject.com/en/5.2/topics/db/models/
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class TelegramUser(models.Model):
    """
    Represents a Telegram user interacting with the bot.

    The `user` FK is nullable — existing bot users continue to work
    without changes until they complete web registration. Once linked,
    the user's verified Django email is used for billing and
    `registration_complete` gates all bot features.

    References:
      https://docs.djangoproject.com/en/5.2/topics/db/models/
      https://docs.djangoproject.com/en/5.2/ref/models/querysets/#get-or-create
    """

    PLAN_FREE = "free"
    PLAN_PRO = "pro"
    PLAN_CHOICES = [
        (PLAN_FREE, "Free"),
        (PLAN_PRO, "Pro"),
    ]

    # Linked after registration via allauth.
    # null=True — existing bot users unaffected until they register.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="telegram_user",
    )

    telegram_id = models.BigIntegerField(unique=True, db_index=True)
    username = models.CharField(max_length=120, blank=True)
    first_name = models.CharField(max_length=120, blank=True)
    plan = models.CharField(max_length=10, choices=PLAN_CHOICES, default=PLAN_FREE)
    paddle_customer_id = models.CharField(max_length=100, blank=True, db_index=True)
    paddle_subscription_id = models.CharField(max_length=100, blank=True, db_index=True)
    subscription_ends_at = models.DateTimeField(null=True, blank=True)
    digest_enabled = models.BooleanField(default=True)
    digest_hour = models.IntegerField(default=8)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["plan"]),
        ]
        verbose_name = "Telegram User"
        verbose_name_plural = "Telegram Users"

    def __str__(self):
        return f"@{self.username or self.first_name} ({self.telegram_id})"

    # ── Properties ──────────────────────────────────────────────────────────────

    @property
    def verified_email(self) -> str | None:
        """Returns the Django user's email if the user FK is linked."""
        if self.user_id:
            return self.user.email or None
        return None

    @property
    def has_verified_email(self) -> bool:
        """True if there is a verified email linked."""
        return bool(self.verified_email)

    @property
    def registration_complete(self) -> bool:
        """
        True when a Django User is linked and has a verified email.
        This gates all bot features beyond /start.
        """
        if not self.user_id:
            return False
        # Check allauth email verification status
        try:
            from allauth.account.models import EmailAddress

            return EmailAddress.objects.filter(
                user_id=self.user_id,
                verified=True,
            ).exists()
        except Exception:
            # Fallback: if allauth table isn't ready yet, check email presence
            return bool(self.user and self.user.email)

    # ── Helper methods ──────────────────────────────────────────────────────────

    def is_pro(self) -> bool:
        """Returns True if the user is on the Pro plan and subscription is active."""
        if self.plan != self.PLAN_PRO:
            return False
        if self.subscription_ends_at and self.subscription_ends_at < timezone.now():
            return False
        return True

    def wallet_limit(self) -> int:
        """10 wallets for Pro, 2 for Free."""
        return 10 if self.is_pro() else 2

    def alert_threshold_eth(self) -> float:
        """1.0 ETH threshold for Pro, 5.0 ETH for Free."""
        return 1.0 if self.is_pro() else 5.0


class WatchedWallet(models.Model):
    """
    A blockchain wallet address being monitored for a TelegramUser.
    """

    CHAIN_ETH = "eth"
    CHAIN_ARB = "arb"
    CHAIN_BASE = "base"
    CHAIN_BSC = "bsc"
    CHAIN_SOL = "sol"
    CHAIN_CHOICES = [
        (CHAIN_ETH, "Ethereum"),
        (CHAIN_ARB, "Arbitrum"),
        (CHAIN_BASE, "Base"),
        (CHAIN_BSC, "BSC"),
        (CHAIN_SOL, "Solana"),
    ]

    telegram_user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="wallets",
    )
    address = models.CharField(max_length=100)
    chain = models.CharField(max_length=10, choices=CHAIN_CHOICES, default=CHAIN_ETH)
    label = models.CharField(max_length=100, blank=True)
    custom_threshold_eth = models.FloatField(null=True, blank=True)
    last_seen_tx = models.CharField(max_length=100, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    dormant_alerted = models.BooleanField(default=False)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("telegram_user", "address", "chain")]
        indexes = [
            models.Index(fields=["telegram_user", "chain"]),
            models.Index(fields=["chain"]),
        ]
        verbose_name = "Watched Wallet"
        verbose_name_plural = "Watched Wallets"

    def __str__(self):
        label = f" ({self.label})" if self.label else ""
        return f"{self.chain.upper()}:{self.address[:10]}…{label}"

    def effective_threshold(self) -> float:
        """Returns the custom threshold if set, otherwise the user's plan threshold."""
        if self.custom_threshold_eth is not None:
            return self.custom_threshold_eth
        return self.telegram_user.alert_threshold_eth()


class Alert(models.Model):
    """
    Records an alert that was sent to a user for a wallet movement.
    """

    ALERT_TRANSFER = "transfer"
    ALERT_TOKEN = "token"
    ALERT_DORMANT = "dormant"
    ALERT_MEME = "meme"
    ALERT_COPY_TRADE = "copy_trade"
    ALERT_TYPE_CHOICES = [
        (ALERT_TRANSFER, "ETH Transfer"),
        (ALERT_TOKEN, "Token Transfer"),
        (ALERT_DORMANT, "Dormant Wallet"),
        (ALERT_MEME, "Memecoin"),
        (ALERT_COPY_TRADE, "Copy Trade Signal"),
    ]

    telegram_user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    wallet = models.ForeignKey(
        WatchedWallet,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alerts",
    )
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    tx_hash = models.CharField(max_length=100, blank=True)
    amount_eth = models.FloatField(null=True, blank=True)
    amount_usd = models.FloatField(null=True, blank=True)
    token_symbol = models.CharField(max_length=30, blank=True)
    direction = models.CharField(max_length=10, blank=True)  # "in" | "out"
    exchange_label = models.CharField(max_length=50, blank=True)
    message_sent = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["telegram_user", "sent_at"]),
            models.Index(fields=["tx_hash"]),
        ]
        verbose_name = "Alert"
        verbose_name_plural = "Alerts"

    def __str__(self):
        return f"{self.alert_type} — {self.tx_hash[:16] if self.tx_hash else 'n/a'}"


class WalletScore(models.Model):
    """
    Cached profitability score (0–10) for a watched wallet.
    Recalculated weekly by the scoring Celery task.
    """

    wallet = models.OneToOneField(
        WatchedWallet,
        on_delete=models.CASCADE,
        related_name="score",
    )
    score = models.FloatField(default=0.0)
    win_rate = models.FloatField(default=0.0)
    avg_return_pct = models.FloatField(default=0.0)
    total_trades = models.IntegerField(default=0)
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Wallet Score"
        verbose_name_plural = "Wallet Scores"

    def __str__(self):
        return f"{self.wallet} → {self.score:.1f}/10"
