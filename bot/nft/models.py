"""
Feature 17 — NFT Whale Tracking models.

WatchedCollection  — a collection being monitored for floor/volume alerts
NFTAlert           — record of an NFT alert sent to a user
"""

from django.db import models

from bot.core.models import TelegramUser


class WatchedCollection(models.Model):
    """
    An NFT collection being monitored by a user.

    Free plan: 1 collection, floor-price drop/rise alerts only.
    Pro plan:  unlimited collections + volume spikes + sweep detection
               + whale wallet NFT activity.
    """

    CHAIN_ETH  = "eth"
    CHAIN_SOL  = "sol"
    CHAIN_BASE = "base"
    CHAIN_ARB  = "arb"
    CHAIN_CHOICES = [
        (CHAIN_ETH,  "Ethereum"),
        (CHAIN_SOL,  "Solana"),
        (CHAIN_BASE, "Base"),
        (CHAIN_ARB,  "Arbitrum"),
    ]

    telegram_user    = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="nft_collections",
    )
    # OpenSea slug (e.g. "boredapeyachtclub") or Solana collection symbol
    slug             = models.CharField(max_length=120)
    chain            = models.CharField(max_length=10, choices=CHAIN_CHOICES, default=CHAIN_ETH)
    name             = models.CharField(max_length=200, blank=True)
    contract_address = models.CharField(max_length=100, blank=True)

    # Alert thresholds
    floor_drop_pct   = models.FloatField(default=10.0,  help_text="Alert when floor drops by this %")
    floor_rise_pct   = models.FloatField(default=20.0,  help_text="Alert when floor rises by this %")
    volume_spike_x   = models.FloatField(default=3.0,   help_text="Alert when 1h volume is Nx baseline (Pro)")
    sweep_min_wallets= models.IntegerField(default=5,   help_text="Alert when N wallets buy in 1h (Pro)")

    # Cached market data
    floor_price_eth  = models.FloatField(null=True, blank=True)
    floor_price_usd  = models.FloatField(null=True, blank=True)
    volume_1h        = models.FloatField(null=True, blank=True)
    volume_24h       = models.FloatField(null=True, blank=True)
    num_owners       = models.IntegerField(null=True, blank=True)
    total_supply     = models.IntegerField(null=True, blank=True)

    # Baseline for spike detection (rolling average)
    volume_baseline  = models.FloatField(null=True, blank=True)

    # Alert state — avoid re-alerting on same event
    last_floor_alerted  = models.FloatField(null=True, blank=True)
    last_checked_at     = models.DateTimeField(null=True, blank=True)
    added_at            = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("telegram_user", "slug", "chain")]
        indexes = [
            models.Index(fields=["telegram_user"]),
            models.Index(fields=["chain"]),
        ]
        verbose_name = "Watched NFT Collection"
        verbose_name_plural = "Watched NFT Collections"
        app_label = "nft"

    def __str__(self):
        return f"{self.name or self.slug} ({self.chain.upper()}) — {self.telegram_user}"


class NFTAlert(models.Model):
    """Record of an NFT alert sent to a user."""

    TYPE_FLOOR_DROP   = "floor_drop"
    TYPE_FLOOR_RISE   = "floor_rise"
    TYPE_VOLUME_SPIKE = "volume_spike"
    TYPE_SWEEP        = "sweep"
    TYPE_WHALE_BUY    = "whale_buy"
    TYPE_WHALE_SELL   = "whale_sell"
    TYPE_WHALE_MINT   = "whale_mint"
    ALERT_TYPE_CHOICES = [
        (TYPE_FLOOR_DROP,   "Floor Price Drop"),
        (TYPE_FLOOR_RISE,   "Floor Price Rise"),
        (TYPE_VOLUME_SPIKE, "Volume Spike"),
        (TYPE_SWEEP,        "Collection Sweep"),
        (TYPE_WHALE_BUY,    "Whale Buy"),
        (TYPE_WHALE_SELL,   "Whale Sell"),
        (TYPE_WHALE_MINT,   "Whale Mint"),
    ]

    telegram_user  = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="nft_alerts",
    )
    collection     = models.ForeignKey(
        WatchedCollection,
        on_delete=models.CASCADE,
        related_name="alerts",
        null=True, blank=True,
    )
    alert_type     = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    tx_hash        = models.CharField(max_length=100, blank=True)
    wallet_address = models.CharField(max_length=100, blank=True)
    wallet_label   = models.CharField(max_length=120, blank=True)
    token_id       = models.CharField(max_length=50, blank=True)
    price_eth      = models.FloatField(null=True, blank=True)
    price_usd      = models.FloatField(null=True, blank=True)
    message_sent   = models.TextField(blank=True)
    sent_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["telegram_user", "sent_at"]),
        ]
        verbose_name = "NFT Alert"
        verbose_name_plural = "NFT Alerts"
        app_label = "nft"

    def __str__(self):
        return f"{self.alert_type} — {self.collection} @ {self.sent_at:%Y-%m-%d %H:%M}"