"""
Memecoin feature models.
TrackedDeployer, MemeToken, MemeAlert.
"""

from django.db import models

from bot.core.models import TelegramUser


class TrackedDeployer(models.Model):
    """
    Feature 13 — A token deployer wallet being watched.
    Pro users can track deployer wallets to get alerts when they launch new tokens.
    """

    telegram_user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="tracked_deployers",
    )
    address = models.CharField(max_length=100, db_index=True)
    chain = models.CharField(max_length=10, default="eth")
    label = models.CharField(max_length=100, blank=True)
    last_seen_contract = models.CharField(max_length=100, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("telegram_user", "address", "chain")]
        verbose_name = "Tracked Deployer"
        verbose_name_plural = "Tracked Deployers"
        app_label = "memecoin"

    def __str__(self):
        return f"{self.label or self.address[:12]}… ({self.chain})"


class MemeToken(models.Model):
    """
    A discovered memecoin token tracked by the scanner.
    """

    STATUS_NEW = "new"
    STATUS_WATCHING = "watching"
    STATUS_GRADUATED = "graduated"
    STATUS_DEAD = "dead"
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_WATCHING, "Watching"),
        (STATUS_GRADUATED, "Graduated"),
        (STATUS_DEAD, "Dead"),
    ]

    address = models.CharField(max_length=100, db_index=True)
    chain = models.CharField(max_length=10, default="eth")
    symbol = models.CharField(max_length=30, blank=True)
    name = models.CharField(max_length=100, blank=True)
    pair_address = models.CharField(max_length=100, blank=True)
    dex = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)

    # Market data (cached)
    price_usd = models.FloatField(null=True, blank=True)
    liquidity_usd = models.FloatField(null=True, blank=True)
    market_cap_usd = models.FloatField(null=True, blank=True)
    volume_1h = models.FloatField(null=True, blank=True)
    buys_1h = models.IntegerField(null=True, blank=True)
    sells_1h = models.IntegerField(null=True, blank=True)

    # Rug check cache
    rugcheck_score = models.FloatField(null=True, blank=True)
    rugcheck_summary = models.TextField(blank=True)
    rugcheck_checked_at = models.DateTimeField(null=True, blank=True)

    # Pump.fun data
    is_pump_fun = models.BooleanField(default=False)
    bonding_curve_pct = models.FloatField(null=True, blank=True)
    graduated_at = models.DateTimeField(null=True, blank=True)

    discovered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("address", "chain")]
        indexes = [
            models.Index(fields=["chain", "status"]),
            models.Index(fields=["discovered_at"]),
        ]
        verbose_name = "Meme Token"
        verbose_name_plural = "Meme Tokens"
        app_label = "memecoin"

    def __str__(self):
        return f"{self.symbol or self.address[:10]}… ({self.chain})"


class MemeAlert(models.Model):
    """
    An alert sent to a user about a memecoin event.
    """

    ALERT_NEW_PAIR = "new_pair"
    ALERT_WHALE_ENTRY = "whale_entry"
    ALERT_MOMENTUM = "momentum"
    ALERT_PUMP_GRADUATION = "pump_graduation"
    ALERT_DEPLOYER_LAUNCH = "deployer_launch"
    ALERT_RUG_RISK = "rug_risk"
    ALERT_TYPE_CHOICES = [
        (ALERT_NEW_PAIR, "New Pair"),
        (ALERT_WHALE_ENTRY, "Whale Entry"),
        (ALERT_MOMENTUM, "Momentum"),
        (ALERT_PUMP_GRADUATION, "Pump.fun Graduation"),
        (ALERT_DEPLOYER_LAUNCH, "Deployer Launch"),
        (ALERT_RUG_RISK, "Rug Risk"),
    ]

    telegram_user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="meme_alerts",
    )
    token = models.ForeignKey(
        MemeToken,
        on_delete=models.CASCADE,
        related_name="alerts",
        null=True,
        blank=True,
    )
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPE_CHOICES)
    message_sent = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["telegram_user", "sent_at"]),
        ]
        verbose_name = "Meme Alert"
        verbose_name_plural = "Meme Alerts"
        app_label = "memecoin"

    def __str__(self):
        return f"{self.alert_type} — {self.token}"
